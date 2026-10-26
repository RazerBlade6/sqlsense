from functools import lru_cache

from app.config import Settings, get_settings
from app.retrieval.corpus import chunk_corpus, load_corpus
from app.retrieval.embed import TitanEmbedder
from app.retrieval.retriever import Retriever
from app.retrieval.store import ChunkStore, LocalChunkStore


def build_retriever(settings: Settings) -> Retriever:
    embedder = TitanEmbedder(settings.embedding_model_id, settings.aws_region)
    store: ChunkStore
    if settings.retrieval_store == "pgvector":
        from app.retrieval.pgvector import PgVectorStore

        if not (settings.db_cluster_arn and settings.db_secret_arn):
            raise ValueError("RETRIEVAL_STORE=pgvector needs DB_CLUSTER_ARN and DB_SECRET_ARN")
        store = PgVectorStore(
            settings.db_cluster_arn, settings.db_secret_arn, settings.db_name, settings.aws_region
        )
    else:
        store = LocalChunkStore(chunk_corpus(load_corpus(settings.corpus_path)), embedder)
    return Retriever(store, embedder)


@lru_cache
def get_retriever() -> Retriever:
    return build_retriever(get_settings())
