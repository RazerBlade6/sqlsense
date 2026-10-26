"""Sync the corpus into pgvector: embed new or changed chunks, upsert them, delete removed ones.

Runs as the ingest Lambda (a CloudFormation custom resource in SqlSenseRetrieval, so every
deploy that changes the corpus re-indexes it) or from a shell with admin access:

    uv run python -m app.retrieval.ingest
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import boto3

from app.retrieval.corpus import DEFAULT_CORPUS_PATH, Chunk, chunk_corpus, load_corpus
from app.retrieval.embed import TitanEmbedder
from app.retrieval.pgvector import SCHEMA, PgVectorStore, _vector_literal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

READER_ROLE = "sqlsense_reader"

UPSERT = """
INSERT INTO chunks (chunk_id, doc_id, doc_type, title, heading, path, content, metadata,
                    content_hash, embedding)
VALUES (:chunk_id, :doc_id, :doc_type, :title, :heading, :path, :content, CAST(:metadata AS jsonb),
        :content_hash, CAST(:embedding AS vector))
ON CONFLICT (chunk_id) DO UPDATE SET
  doc_id = EXCLUDED.doc_id, doc_type = EXCLUDED.doc_type, title = EXCLUDED.title,
  heading = EXCLUDED.heading, path = EXCLUDED.path, content = EXCLUDED.content,
  metadata = EXCLUDED.metadata, content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding
"""


def sync(store: PgVectorStore, chunks: list[Chunk], embedder: TitanEmbedder) -> dict[str, int]:
    for statement in SCHEMA:
        store.execute(statement)
    existing = {
        r["chunk_id"]: r["content_hash"]
        for r in store.execute("SELECT chunk_id, content_hash FROM chunks")
    }
    changed = [c for c in chunks if existing.get(c.chunk_id) != c.content_hash]
    embeddings = embedder.embed_many([c.embedding_text for c in changed])
    for chunk, embedding in zip(changed, embeddings, strict=True):
        store.execute(
            UPSERT,
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "doc_type": chunk.doc_type,
                "title": chunk.title,
                "heading": chunk.heading,
                "path": chunk.path,
                "content": chunk.content,
                "metadata": json.dumps(chunk.metadata, default=str),
                "content_hash": chunk.content_hash,
                "embedding": _vector_literal(embedding),
            },
        )
    removed = set(existing) - {c.chunk_id for c in chunks}
    for chunk_id in removed:
        store.execute("DELETE FROM chunks WHERE chunk_id = :chunk_id", {"chunk_id": chunk_id})
    return {"chunks": len(chunks), "upserted": len(changed), "deleted": len(removed)}


def grant_reader(store: PgVectorStore, password: str) -> None:
    """A login role that can only read the chunks table; the API connects as this role."""
    quoted = password.replace("'", "''")
    store.execute(
        f"""DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{READER_ROLE}') THEN
                CREATE ROLE {READER_ROLE} LOGIN;
              END IF;
            END $$"""
    )
    store.execute(f"ALTER ROLE {READER_ROLE} WITH LOGIN PASSWORD '{quoted}'")
    store.execute(f"GRANT CONNECT ON DATABASE {store.database} TO {READER_ROLE}")
    store.execute(f"GRANT USAGE ON SCHEMA public TO {READER_ROLE}")
    store.execute(f"GRANT SELECT ON chunks TO {READER_ROLE}")


def run(chunks: list[Chunk] | None = None) -> dict[str, int]:
    region = os.environ.get("AWS_REGION", "ap-southeast-2")
    store = PgVectorStore(
        cluster_arn=os.environ["DB_CLUSTER_ARN"],
        secret_arn=os.environ["DB_ADMIN_SECRET_ARN"],
        database=os.environ.get("DB_NAME", "sqlsense"),
        region=region,
    )
    embedder = TitanEmbedder(
        os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"), region
    )
    corpus_path = Path(os.environ.get("CORPUS_PATH", DEFAULT_CORPUS_PATH))
    chunks = chunks or chunk_corpus(load_corpus(corpus_path))
    counts = sync(store, chunks, embedder)
    if reader_secret := os.environ.get("DB_READER_SECRET_ARN"):
        secrets = boto3.client("secretsmanager", region_name=region)
        secret = json.loads(secrets.get_secret_value(SecretId=reader_secret)["SecretString"])
        grant_reader(store, secret["password"])
    return counts


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """CloudFormation custom resource (CDK Provider framework) on_event handler."""
    logger.info("request %s", event.get("RequestType"))
    physical_id = event.get("PhysicalResourceId", "corpus-index")
    if event["RequestType"] == "Delete":
        return {"PhysicalResourceId": physical_id}
    counts = run()
    logger.info("synced %s", counts)
    return {"PhysicalResourceId": physical_id, "Data": counts}


if __name__ == "__main__":
    print(run())
