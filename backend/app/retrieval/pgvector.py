"""Chunk store on Aurora PostgreSQL with pgvector, reached through the RDS Data API.

The Data API is HTTPS, so the API Lambda needs no VPC. Hybrid search runs as two queries,
cosine distance on an HNSW index and full-text search on a tsvector column, and the
retriever fuses the two rankings.
"""

import json
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.retrieval.corpus import Chunk
from app.retrieval.embed import EMBEDDING_DIMENSIONS
from app.retrieval.store import ScoredChunks

SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"""CREATE TABLE IF NOT EXISTS chunks (
        chunk_id text PRIMARY KEY,
        doc_id text NOT NULL,
        doc_type text NOT NULL,
        title text NOT NULL,
        heading text NOT NULL,
        path text NOT NULL,
        content text NOT NULL,
        metadata jsonb NOT NULL DEFAULT '{{}}',
        content_hash text NOT NULL,
        embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
        tsv tsvector GENERATED ALWAYS AS (
            to_tsvector('english', title || ' ' || heading || ' ' || content)
        ) STORED
    )""",
    "CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv)",
]

_COLUMNS = "chunk_id, doc_id, doc_type, title, heading, path, content, metadata"

# A cluster paused at 0 ACU takes about 15 seconds to resume.
_RESUME_WAIT_S = 45


class PgVectorStore:
    engine = "pgvector"

    def __init__(self, cluster_arn: str, secret_arn: str, database: str, region: str):
        self.cluster_arn = cluster_arn
        self.secret_arn = secret_arn
        self.database = database
        self.client = boto3.client("rds-data", region_name=region)

    def vector_search(self, embedding: list[float], k: int) -> ScoredChunks:
        rows = self.execute(
            f"""SELECT {_COLUMNS}, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM chunks ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :k""",
            {"embedding": _vector_literal(embedding), "k": k},
        )
        return [(_to_chunk(r), float(r["score"])) for r in rows]

    def keyword_search(self, query: str, k: int) -> ScoredChunks:
        # plainto_tsquery ANDs every word, which rarely matches a whole question; OR them instead.
        rows = self.execute(
            f"""WITH q AS (
                  SELECT replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery AS query
                )
                SELECT {_COLUMNS}, ts_rank_cd(tsv, q.query) AS score
                FROM chunks, q WHERE tsv @@ q.query ORDER BY score DESC LIMIT :k""",
            {"query": query, "k": k},
        )
        return [(_to_chunk(r), float(r["score"])) for r in rows]

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        request = {
            "resourceArn": self.cluster_arn,
            "secretArn": self.secret_arn,
            "database": self.database,
            "sql": sql,
            "formatRecordsAs": "JSON",
            "parameters": [_parameter(name, value) for name, value in (params or {}).items()],
        }
        deadline = time.monotonic() + _RESUME_WAIT_S
        while True:
            try:
                response = self.client.execute_statement(**request)
                break
            except ClientError as exc:
                if not _is_resuming(exc) or time.monotonic() > deadline:
                    raise
                time.sleep(2)
        return json.loads(response.get("formattedRecords") or "[]")


def _is_resuming(exc: ClientError) -> bool:
    code = exc.response["Error"]["Code"]
    message = exc.response["Error"].get("Message", "")
    return code == "DatabaseResumingException" or "resuming" in message.lower()


def _parameter(name: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, dict):
        return {"name": name, "value": {"stringValue": json.dumps(value)}, "typeHint": "JSON"}
    return {"name": name, "value": {"stringValue": str(value)}}


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in embedding) + "]"


def _to_chunk(row: dict[str, Any]) -> Chunk:
    metadata = row["metadata"]
    return Chunk(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"],
        doc_type=row["doc_type"],
        title=row["title"],
        heading=row["heading"],
        path=row["path"],
        content=row["content"],
        metadata=json.loads(metadata) if isinstance(metadata, str) else metadata,
    )
