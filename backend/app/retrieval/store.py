import math
import re
import threading
from collections import Counter
from typing import Protocol

from app.retrieval.corpus import Chunk
from app.retrieval.embed import TitanEmbedder

ScoredChunks = list[tuple[Chunk, float]]

STOPWORDS = frozenset(
    "a an and are as at be by did do does for from has have how i in is it its many much of on "
    "or our per show tell that the their there this to was we were what when which who why with "
    "you".split()
)


class ChunkStore(Protocol):
    """Chunks with embeddings, searchable by vector similarity and by keywords."""

    engine: str

    def vector_search(self, embedding: list[float], k: int) -> ScoredChunks: ...

    def keyword_search(self, query: str, k: int) -> ScoredChunks: ...


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(t) for t in tokens if t not in STOPWORDS]


def _stem(token: str) -> str:
    # Enough to match "households"/"household" and "campaigns"/"campaign" locally.
    return (
        token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token
    )


class LocalChunkStore:
    """In-memory store for local development and CI: cosine similarity plus BM25.

    The corpus is embedded on first use (a few seconds through Bedrock).
    """

    engine = "local"

    def __init__(self, chunks: list[Chunk], embedder: TitanEmbedder):
        self.chunks = chunks
        self.embedder = embedder
        self._embeddings: list[list[float]] | None = None
        self._lock = threading.Lock()
        self._docs = [tokenize(c.embedding_text) for c in chunks]
        self._avg_len = sum(map(len, self._docs)) / max(len(self._docs), 1)
        df = Counter(t for doc in self._docs for t in set(doc))
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._tf = [Counter(doc) for doc in self._docs]

    def vector_search(self, embedding: list[float], k: int) -> ScoredChunks:
        # Titan vectors are normalized, so the dot product is the cosine similarity.
        scores = [sum(a * b for a, b in zip(embedding, e, strict=True)) for e in self.embeddings]
        return self._top(scores, k)

    def keyword_search(self, query: str, k: int, k1: float = 1.2, b: float = 0.75) -> ScoredChunks:
        terms = set(tokenize(query))
        scores = []
        for tf, doc in zip(self._tf, self._docs, strict=True):
            norm = k1 * (1 - b + b * len(doc) / self._avg_len)
            scores.append(
                sum(self._idf[t] * tf[t] * (k1 + 1) / (tf[t] + norm) for t in terms if t in tf)
            )
        return [(c, s) for c, s in self._top(scores, k) if s > 0]

    @property
    def embeddings(self) -> list[list[float]]:
        with self._lock:
            if self._embeddings is None:
                self._embeddings = self.embedder.embed_many([c.embedding_text for c in self.chunks])
            return self._embeddings

    def _top(self, scores: list[float], k: int) -> ScoredChunks:
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [(self.chunks[i], scores[i]) for i in ranked]
