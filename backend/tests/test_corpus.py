import re
from pathlib import Path

from app.retrieval.corpus import (
    DEFAULT_CORPUS_PATH,
    Document,
    chunk_corpus,
    chunk_document,
    defined_terms,
    find_terms,
    glossary,
    load_corpus,
)
from app.warehouse.catalog import load_catalog

DOCS = load_corpus()


def test_corpus_loads_with_valid_metadata() -> None:
    assert len(DOCS) > 40
    assert {d.doc_type for d in DOCS} == {"metric", "policy", "campaign", "dictionary"}
    for doc in DOCS:
        assert doc.title and doc.body, doc.path


def test_every_campaign_and_table_is_documented() -> None:
    briefs = {d.metadata.get("campaign_id") for d in DOCS if d.doc_type == "campaign"}
    assert set(range(1, 28)) <= briefs
    tables = {d.metadata.get("table") for d in DOCS if d.doc_type == "dictionary"}
    assert tables == {t["name"] for t in load_catalog()["tables"]}


def test_relative_links_resolve() -> None:
    for doc in DOCS:
        for target in re.findall(r"\]\(([^)#]+\.md)\)", doc.body):
            path = (DEFAULT_CORPUS_PATH / doc.path).parent / target
            assert path.resolve().exists(), f"{doc.path} links to missing {target}"


def test_small_documents_stay_whole() -> None:
    chunks = chunk_corpus(DOCS)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    basket = next(c for c in chunks if c.doc_id == "metric-basket-value")
    assert basket.chunk_id == "metric-basket-value"
    assert basket.embedding_text.startswith("Basket value\n")


def test_large_documents_split_at_headings() -> None:
    body = "# Big\n\nIntro.\n\n## First\n" + "word " * 500 + "\n\n## Second\n" + "word " * 500
    doc = Document("big", "policy", "Big", "big.md", body)

    chunks = chunk_document(doc, max_chars=3000)

    assert [c.chunk_id for c in chunks] == ["big#introduction", "big#first", "big#second"]
    assert chunks[1].embedding_text.startswith("Big > First\n")


def test_glossary_leaves_out_generic_terms() -> None:
    """Plain sales questions need no documents, so "sales" mustn't look like a defined term."""
    terms = glossary(DOCS)
    assert "active household" in terms and "fiscal quarter" in terms
    assert not re.search(r"(: |, )sales(,|$)", terms, re.M)
    assert Path(DEFAULT_CORPUS_PATH / "README.md").exists()


def test_defined_terms_match_plurals_and_prefer_longest() -> None:
    terms = defined_terms(DOCS)
    assert find_terms("How many lapsed households are there?", terms) == ["lapsed household"]
    assert find_terms("What is the average basket value?", terms) == ["average basket value"]
    assert find_terms("Which 5 departments had the highest sales?", terms) == []
