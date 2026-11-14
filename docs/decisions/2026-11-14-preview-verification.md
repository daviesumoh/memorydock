# Preview features verified; no fallbacks needed

Date: 2026-11-14

## Context

Recall depends on Atlas features that were previews or recent at design time: Automated Embedding, `$vectorSearch` with a text query, `$rankFusion` with an Automated Embedding branch, and fast removal from vector results when a memory is forgotten. Each had a fallback planned in case it failed (client-side Voyage embeddings, fusing in Python, client-side vectors for purge).

## Result

`scripts/verify_preview.py` ran against the cluster (MongoDB 9.0.7, M10) on 2026-11-14. Results are in `docs/verify_preview_results.json`.

- Automated Embedding with `voyage-4` builds and serves. `$vectorSearch` accepts a plain-string `query`; a new document was searchable about 2 s after insert.
- The recall `$rankFusion` pipeline (vector + lexical branches, filters repeated in each branch, live-document `$match` after) returns the expected memory first and excludes other tenants and `proposed` memories.
- Setting `embed_text` to null removed the memory from unfiltered vector results in about 2.5 s, well inside the 60 s limit.
- A transaction across `memories`, `memory_versions`, `audit_log` and `audit_heads` commits as `md_gateway`, so the custom role allows it.

## Decision

- Use the primary design: server-side Automated Embedding and one `$rankFusion` aggregation. No `VOYAGE_API_KEY`, no Python-side fusion.
- Atlas Local has no embedding model, so CI integration tests run without search indexes (`atlas_setup.py --skip-search`). Search behaviour is checked with this script against the live cluster before each phase closes.
- The transaction check runs in the developer database, because the app roles don't cover `memorydock_verify`. We don't widen the roles for a throwaway database.
