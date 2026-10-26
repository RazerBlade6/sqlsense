"""Offline stand-ins for Bedrock embeddings."""

import hashlib
import math

from app.retrieval.store import tokenize


class HashEmbedder:
    """Bag-of-words vectors: texts sharing words are similar. Deterministic and offline."""

    model_id = "fake"
    dims = 256

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in tokenize(text):
            vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
