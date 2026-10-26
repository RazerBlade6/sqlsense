# Retrieval and the agent graph

## How a question is answered

```
question ─► planner ─┬─ sql ─────────────────────► SQL agent ─► synthesizer ─► answer
                     ├─ docs ───► retrieval ─────────────────► synthesizer ─► answer + citations
                     ├─ both ───► retrieval ─► SQL agent ────► synthesizer ─► answer + citations
                     └─ clarify / refuse ─────────────────────────────────────► message
```

| Step | Model | Does |
|---|---|---|
| Planner (`agents/planner.py`) | Nova Micro | Picks the route, rewrites follow-ups into standalone questions using the session's last 5 turns, and lists the documented terms the question depends on |
| Retrieval (`retrieval/`) | Titan Embeddings V2 | Hybrid search over the corpus; returns the top 5 chunks |
| SQL agent (`agents/sql_agent.py`) | Nova Pro | Generate → validate → execute, with retries. On the `both` route it receives the retrieved definitions, including their SQL patterns |
| Synthesizer (`agents/synthesizer.py`) | Nova Pro | Writes the answer from the query result and the documents, citing documents as `[n]` |

Every step adds a `TraceStep` (duration, tokens, bytes scanned, and details such as each SQL attempt and its error). The API returns the trace and the UI shows it as a timeline.

**Glossary guard.** The planner prompt lists every term the documents define, but Nova Micro still routed questions such as "What is the average basket value?" to `sql`, and the SQL agent then guessed the definition. After planning, the graph matches the question against the documented metric and policy terms. A match upgrades `sql` to `both` and is recorded in the trace (`upgraded_by_glossary`). This raised routing accuracy from 81% to 97–100%.

## Corpus

[`corpus/`](../corpus/README.md) holds 53 markdown documents: 13 metric definitions, 3 policies (fiscal calendar, sales reporting rules, data privacy), the campaign types and 27 campaign briefs, and one data dictionary page per table. **The documents are synthetic**: facts about the data come from the warehouse, while business rules and targets are invented to be consistent with it. Every SQL pattern in the corpus is executed in a check before it is committed.

Writing the corpus caught one real error. The first promotion lift definition measured dollar sales and came out at **−7%**. Promoted items are discounted, so dollar sales can fall while units rise. Measured in units and within each product-store pair, lift is **+14%**.

## Chunking

Documents of up to about 800 tokens (3,200 characters) stay whole. Longer ones split at `##` headings, and long sections split further at paragraph breaks. Every corpus document is currently under the limit, so retrieval is effectively per document. Each chunk is embedded with its title and heading as a prefix (`Basket value > Calculation`).

## Hybrid search

For each query, the vector ranking (cosine similarity) and the keyword ranking are merged with reciprocal rank fusion (RRF, k = 60). The planner can produce several queries: the question plus each documented term it uses. Their rankings are **interleaved** rather than summed, so that each query keeps its best hit.

Summing failed in practice. For "Did campaign 18 meet its redemption target?", the broad query "redemption target" matched all 27 campaign briefs and pushed the campaign 18 brief out of the top 5.

| Store | Vector search | Keyword search | Used by |
|---|---|---|---|
| `local` | dot product over Titan vectors in memory | BM25 | local development and CI |
| `pgvector` | `<=>` cosine distance on an HNSW index | Postgres full-text search (`tsvector`, words ORed) | deployed API |

Set `RETRIEVAL_STORE` to choose. The two keyword rankings differ in detail: Postgres stems words and BM25 here does only light plural folding.

## pgvector on Aurora Serverless v2

`SqlSenseRetrieval` deploys:
- **Cluster:** Aurora PostgreSQL 17 with a minimum of **0 ACU**. It pauses after 10 idle minutes, and storage is the main cost. The first query after a pause waits about 15 s while it resumes. `PgVectorStore` retries `DatabaseResumingException` for up to 45 s.
- **Network:** a VPC with isolated subnets only, so there is no NAT gateway and no internet route.
- **Access:** the API reaches the database through the **RDS Data API** over HTTPS, so its Lambda needs no VPC.
- **Two database roles:**
  - The ingest function uses the admin secret.
  - The API uses `sqlsense_reader`, which can only `SELECT` from `chunks`. Its IAM policy can read only the reader's secret.
- **Indexing on deploy:** a CloudFormation custom resource runs the ingest Lambda whenever a fingerprint of the corpus and the retrieval code changes. Ingest embeds only new or changed chunks and deletes removed ones. Publishing documents is therefore part of a normal deploy, as publishing data is.
