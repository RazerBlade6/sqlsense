"""Load the markdown corpus and split it into chunks for retrieval."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parents[3] / "corpus"

# About 800 tokens. Documents under this size stay whole; larger ones split at "## " headings.
MAX_CHUNK_CHARS = 3200

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass
class Document:
    doc_id: str
    doc_type: str
    title: str
    path: str
    body: str
    terms: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    doc_type: str
    title: str
    heading: str
    path: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def embedding_text(self) -> str:
        """What gets embedded: the content prefixed with where it comes from."""
        location = self.title if self.heading == self.title else f"{self.title} > {self.heading}"
        return f"{location}\n\n{self.content}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.embedding_text.encode()).hexdigest()


def load_corpus(root: Path = DEFAULT_CORPUS_PATH) -> list[Document]:
    docs = []
    for path in sorted(root.rglob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text()
        match = _FRONT_MATTER.match(text)
        if not match:
            raise ValueError(f"{path} has no front matter")
        meta = yaml.safe_load(match.group(1))
        docs.append(
            Document(
                doc_id=meta.pop("doc_id"),
                doc_type=meta.pop("doc_type"),
                title=meta.pop("title"),
                terms=meta.pop("terms", []),
                path=path.relative_to(root).as_posix(),
                body=text[match.end() :].strip(),
                metadata=meta,
            )
        )
    ids = [d.doc_id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate doc_id in corpus")
    return docs


def chunk_document(doc: Document, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    body = _strip_title(doc.body)
    if len(body) <= max_chars:
        return [_chunk(doc, doc.doc_id, doc.title, body)]

    chunks = []
    for heading, section in _sections(body):
        for i, part in enumerate(_split_paragraphs(section, max_chars)):
            suffix = f"-{i + 1}" if i else ""
            chunk_id = f"{doc.doc_id}#{_slug(heading)}{suffix}"
            chunks.append(_chunk(doc, chunk_id, heading, part))
    return chunks


def chunk_corpus(docs: list[Document]) -> list[Chunk]:
    return [chunk for doc in docs for chunk in chunk_document(doc)]


def glossary(docs: list[Document]) -> str:
    """Business terms the documents define, grouped by document type, for the planner."""
    lines = []
    for doc_type in ("metric", "policy", "campaign"):
        terms = sorted({t for d in docs if d.doc_type == doc_type for t in d.terms})
        if terms:
            lines.append(f"- {doc_type}: {', '.join(terms)}")
    briefs = sorted(int(d.metadata["campaign_id"]) for d in docs if "campaign_id" in d.metadata)
    if briefs:
        lines.append(
            f"- campaign briefs for campaigns {briefs[0]}-{briefs[-1]}: objective, target audience,"
            " offer and redemption target"
        )
    return "\n".join(lines)


def defined_terms(docs: list[Document]) -> list[str]:
    """Metric and policy terms, longest first, for matching in questions."""
    terms = {t.lower() for d in docs if d.doc_type in ("metric", "policy") for t in d.terms}
    return sorted(terms, key=len, reverse=True)


def find_terms(text: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for term in terms:
        if re.search(rf"\b{re.escape(term)}s?\b", lowered) and not any(term in f for f in found):
            found.append(term)
    return found


def _chunk(doc: Document, chunk_id: str, heading: str, content: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc.doc_id,
        doc_type=doc.doc_type,
        title=doc.title,
        heading=heading,
        path=doc.path,
        content=content.strip(),
        metadata=doc.metadata,
    )


def _strip_title(body: str) -> str:
    return re.sub(r"\A# .*\n+", "", body)


def _sections(body: str) -> list[tuple[str, str]]:
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    sections = [("Introduction", parts[0])] if parts[0].strip() else []
    sections += [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]
    return sections


def _split_paragraphs(text: str, max_chars: int) -> list[str]:
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", text.strip()):
        if current and len(current) + len(para) + 2 > max_chars:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    return [*parts, current] if current else parts


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
