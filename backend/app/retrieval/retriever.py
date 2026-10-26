from dataclasses import dataclass

from app.retrieval.corpus import Chunk
from app.retrieval.embed import TitanEmbedder
from app.retrieval.store import ChunkStore

# The usual reciprocal rank fusion constant: dampens the weight of the very top ranks.
RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


class Retriever:
    """Hybrid search. Each query's vector and keyword rankings are merged with RRF; the
    per-query results are then interleaved, so a broad query (a metric name) can't crowd out
    a specific one (a campaign number)."""

    def __init__(self, store: ChunkStore, embedder: TitanEmbedder, candidates: int = 20):
        self.store = store
        self.embedder = embedder
        self.candidates = candidates

    def search(self, queries: list[str], k: int = 5) -> list[RetrievedChunk]:
        queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
        embeddings = self.embedder.embed_many(queries)
        per_query = [self._hybrid(q, e) for q, e in zip(queries, embeddings, strict=True)]

        merged: dict[str, RetrievedChunk] = {}
        for rank in range(self.candidates):
            for ranking in per_query:
                if rank < len(ranking) and len(merged) < k:
                    merged.setdefault(ranking[rank].chunk.chunk_id, ranking[rank])
        return list(merged.values())

    def _hybrid(self, query: str, embedding: list[float]) -> list[RetrievedChunk]:
        fused: dict[str, RetrievedChunk] = {}
        rankings = {
            "vector_rank": self.store.vector_search(embedding, self.candidates),
            "keyword_rank": self.store.keyword_search(query, self.candidates),
        }
        for field, ranking in rankings.items():
            for rank, (chunk, _) in enumerate(ranking, start=1):
                hit = fused.setdefault(chunk.chunk_id, RetrievedChunk(chunk, 0.0))
                hit.score += 1 / (RRF_K + rank)
                setattr(hit, field, rank)
        return sorted(fused.values(), key=lambda h: h.score, reverse=True)
