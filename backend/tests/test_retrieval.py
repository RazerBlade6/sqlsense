import json

import pytest
from botocore.stub import Stubber

from app.retrieval.corpus import Chunk, chunk_corpus, load_corpus
from app.retrieval.pgvector import PgVectorStore
from app.retrieval.retriever import Retriever
from app.retrieval.store import LocalChunkStore, ScoredChunks
from tests.fakes import HashEmbedder


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    embedder = HashEmbedder()
    return Retriever(LocalChunkStore(chunk_corpus(load_corpus()), embedder), embedder)


def test_keyword_and_vector_agree_on_an_exact_topic(retriever: Retriever) -> None:
    hits = retriever.search(["fiscal quarter weeks"], k=3)
    assert hits[0].chunk.doc_id == "policy-fiscal-calendar"
    assert hits[0].vector_rank and hits[0].keyword_rank


class RankedStore:
    """Returns a fixed ranking per query: a broad query that matches many docs, and a narrow one."""

    engine = "stub"

    def __init__(self) -> None:
        self.chunks = {d: Chunk(d, d, "doc", d, d, f"{d}.md", d) for d in "ABCDEFGHIJ"}
        self.by_query = {"broad": list("BCDEFGHI"), "narrow": ["A", "J"]}

    def vector_search(self, embedding: list[float], k: int) -> ScoredChunks:
        query = "broad" if embedding[0] else "narrow"
        return [(self.chunks[d], 1.0) for d in self.by_query[query][:k]]

    def keyword_search(self, query: str, k: int) -> ScoredChunks:
        return [(self.chunks[d], 1.0) for d in self.by_query[query][:k]]


class FlagEmbedder:
    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[1.0 if t == "broad" else 0.0] for t in texts]


def test_each_query_keeps_its_best_hit() -> None:
    """Interleaving: a broad definition query can't crowd out a specific one."""
    hits = Retriever(RankedStore(), FlagEmbedder()).search(["narrow", "broad"], k=4)
    assert [h.chunk.doc_id for h in hits] == ["A", "B", "J", "C"]


def test_duplicate_queries_are_searched_once(retriever: Retriever) -> None:
    hits = retriever.search(["fiscal quarter", " fiscal quarter "], k=5)
    assert len({h.chunk.chunk_id for h in hits}) == 5


def test_keyword_search_ignores_stopwords(retriever: Retriever) -> None:
    assert retriever.store.keyword_search("what is the of", 5) == []


def test_pgvector_waits_for_a_paused_cluster() -> None:
    store = PgVectorStore(
        "arn:aws:rds:cluster", "arn:aws:secretsmanager:secret", "sqlsense", "ap-southeast-2"
    )
    rows = [
        {
            "chunk_id": "a",
            "doc_id": "a",
            "doc_type": "metric",
            "title": "A",
            "heading": "A",
            "path": "a.md",
            "content": "text",
            "metadata": "{}",
            "score": 0.9,
        }
    ]
    with Stubber(store.client) as stub:
        stub.add_client_error("execute_statement", "DatabaseResumingException", "resuming")
        stub.add_response("execute_statement", {"formattedRecords": json.dumps(rows)})
        hits = store.vector_search([0.5, 0.25], 3)
    assert hits[0][0].chunk_id == "a" and hits[0][1] == pytest.approx(0.9)


def test_pgvector_passes_typed_parameters() -> None:
    store = PgVectorStore(
        "arn:aws:rds:cluster", "arn:aws:secretsmanager:secret", "sqlsense", "ap-southeast-2"
    )
    with Stubber(store.client) as stub:
        stub.add_response(
            "execute_statement",
            {"formattedRecords": "[]"},
            {
                "resourceArn": "arn:aws:rds:cluster",
                "secretArn": "arn:aws:secretsmanager:secret",
                "database": "sqlsense",
                "sql": "SELECT :k, :q",
                "formatRecordsAs": "JSON",
                "parameters": [
                    {"name": "k", "value": {"longValue": 5}},
                    {"name": "q", "value": {"stringValue": "[0.5,0.25]"}},
                ],
            },
        )
        assert store.execute("SELECT :k, :q", {"k": 5, "q": "[0.5,0.25]"}) == []
