# LiveDocX — Architecture Review & Forward Roadmap

> **Implementation status (August 11, 2026):** The foundation, JWT/profile
> fixes, and authenticated document-management API described in the early
> phases have now been implemented and covered by tests. The shortcomings list
> below is retained as the original audit snapshot; the ingestion, Celery,
> extraction, embedding, hybrid-search, and summarization phases remain future
> work. See `README.md` for the current API contract.

## Context

LiveDocX is a document intelligence platform: users upload documents (any type), the system deduplicates, parses, chunks, embeds, and indexes them, then serves semantic search with page-level citations and AI-written summaries. Public-vs-private metadata controls cross-user visibility.

The project is currently an **early scaffold**. Auth and document apps exist, a few endpoints are stubbed, dependencies for pgvector and django-ninja are installed, but the ingestion pipeline, search, RAG, auth flow, storage, and background processing are all **not implemented**, and several foundational files have bugs that will block any progress. This document fixes the foundation, then lays out a phased path from scaffold to production-ready.

**Stack decisions (confirmed):**
- API framework: django-ninja (async)
- Vector store: **pgvector** (single Postgres, no extra service)
- Search: pgvector ANN + Postgres full-text (hybrid, fused via RRF)
- Task queue: **Celery + Redis**
- LLM/embeddings: **LiteLLM** (provider-agnostic facade; start with one provider, swap freely)
- Auth: **django-ninja-jwt** (drop django-oauth-toolkit)
- Deployment: **VPS (Hetzner/DO) + Docker Compose**
- Scope: API-only for v1

---

## Part 1 — Shortcomings in the current code

These must be fixed before any feature work. All are in files under `docmanage/` and `configuration/`.

### Correctness bugs (blocking)

1. `docmanage/api.py:9` — `@rounter.post(...)` typo (should be `@router`), and `GlobalAuth()` is undefined/unimported. Endpoint does not compile.
2. `docmanage/models.py:15` — `is_public = models.BooleanField(auto_now_add=True)`. `auto_now_add` is invalid on `BooleanField`; will raise at migration time.
3. `docmanage/models.py:24` — `page_number = models.IntegerField(dimensions=1536)`. Two problems: (a) `IntegerField` doesn't accept `dimensions`, (b) pgvector's `VectorField` was imported but never used. The embedding column is missing.
4. `docmanage/utils.py:5` — `file.chuns()` typo (should be `chunks()`).
5. `docmanage.api.router` is **not registered** in `configuration/api.py` — even if fixed, the upload route is unreachable.

### Configuration issues

6. `configuration/settings.py:28` — hardcoded `SECRET_KEY`. Must come from env.
7. `configuration/settings.py:31` — `DEBUG = True`. Must be env-driven.
8. `configuration/settings.py:33` — `ALLOWED_HOSTS = []`. Must be env-driven.
9. `configuration/settings.py:136` — `CROS_ALLOWED_ORIGINS` typo (should be `CORS_ALLOWED_ORIGINS`); django-cors-headers silently ignores the misspelled name, so CORS is effectively off.
10. No `FILE_UPLOAD_MAX_MEMORY_SIZE` / `DATA_UPLOAD_MAX_MEMORY_SIZE` / streaming handler configured — large PDF uploads will OOM.
11. `django-oauth-toolkit` is installed and listed in `INSTALLED_APPS` but unused; remove it in favor of JWT.
12. No media/storage config (`MEDIA_ROOT`, `MEDIA_URL`, `DEFAULT_FILE_STORAGE`).
13. No `LOGGING` config. Production needs structured JSON logs.

### Deployment / infra issues

14. `Dockerfile` mixes **Poetry and uv** (line declares Poetry env, then `uv add` is called, then `COPY ... poetry.lock*` — but the repo actually ships `uv.lock`). Rebuild it around uv only.
15. Dockerfile runs `manage.py runserver` — the dev server. Production must use gunicorn/uvicorn.
16. No `docker-compose.yml` for db/redis/worker/web. No Nginx reverse proxy / TLS story.
17. No migrations committed for `docmanage/migrations/` (only `__init__.py`).
18. No tests; empty `tests.py` files in every app.
19. No CI (no `.github/workflows/`), no pre-commit, ruff not enforced.

### Architectural gaps

20. Ingestion is synchronous (the stub uses `async def` but runs in the request). Parsing + embedding a 200-page PDF will time out HTTP.
21. No document parser abstraction. "Any file type" requires format detection and per-format extractors (PDF/DOCX/HTML/PPTX/images via OCR/MD/TXT).
22. Chunking strategy undefined. Without page-aware chunking you cannot cite page numbers.
23. No embedding service layer. Calls would be scattered across views.
24. No retrieval layer. Semantic-only search misses exact-term queries (IDs, names, acronyms). Need **hybrid: pgvector ANN + Postgres FTS**, fused with Reciprocal Rank Fusion.
25. Public/private access control declared on the model but not enforced in any queryset.
26. Deduplication: SHA-256 hash is global-unique. This means if User B uploads the same file User A already uploaded, User B's upload fails. Business question: should dedup be per-user (preferred) or global with re-ownership/sharing? Recommendation: **per-user unique** (unique-together on `owner, content_hash`) and let public docs be discoverable via search, not file re-upload.
27. No rate limiting, no request throttling, no upload quotas.
28. No observability (metrics, tracing). At minimum: structured logging + Sentry.

---

## Part 2 — Recommended target architecture

```
         ┌────────────────────────────────────────────────────┐
Client ─▶│ django-ninja API (async) — JWT auth               │
         │  • /auth/*   /users/*   /documents/*   /search/*   │
         └────┬──────────────────────┬────────────────────────┘
              │                      │
              ▼                      ▼
        Postgres 16          Redis (broker + cache)
        + pgvector                  │
        + tsvector FTS              ▼
                               Celery workers
                                    │
                                    ▼
        ┌───────────────────────────────────────┐
        │ Ingestion pipeline (Celery chain)     │
        │ 1. store file (S3-compatible / local) │
        │ 2. hash + dedup check                 │
        │ 3. parse (format-specific extractor)  │
        │ 4. chunk (page-aware)                 │
        │ 5. embed (LiteLLM → provider)         │
        │ 6. index (pgvector + tsvector)        │
        │ 7. mark Document.status = ready       │
        └───────────────────────────────────────┘
```

**Retrieval path (search with citations + AI summary):**
1. Query → embed (LiteLLM)
2. Parallel: pgvector cosine top-k + Postgres FTS top-k
3. Fuse ranks via RRF → top N chunks
4. Filter by access (owner OR is_public)
5. LLM summarization with citations (chunk IDs → page numbers) via LiteLLM
6. Return: answer + `[{document_id, page, snippet, score}]`

---

## Part 3 — Phased delivery plan

Each phase is a shippable milestone. Do not start phase N+1 until N is green (tests + manual smoke).

### Phase 0 — Fix the foundation (1–2 days)
- Delete `docmanage/api.py` and `docmanage/utils.py` bodies; rewrite from scratch.
- Rewrite `docmanage/models.py`:
  - `Document`: `owner`, `name`, `file`, `file_type`, `size_bytes`, `is_public` (BooleanField, `default=False`), `content_hash` (64-char), `status` (enum: `pending|processing|ready|failed`), `created_at`, `updated_at`. Change dedup to `UniqueConstraint(fields=["owner", "content_hash"])`.
  - `DocumentChunk`: `document` FK, `page_number` (IntegerField), `chunk_index`, `content` TextField, `embedding = VectorField(dimensions=<model_dim>)`, `tsv` (SearchVectorField, GIN-indexed).
- Fix `configuration/settings.py`: env-driven `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` (fix typo), logging, media settings.
- Add `.env.example`.
- Remove `django-oauth-toolkit` from dependencies and `INSTALLED_APPS`.
- Register `docmanage.api.router` in `configuration/api.py`.
- Write a smoke test per app so the test runner is green.

### Phase 1 — Auth (2–3 days)
- Add `django-ninja-jwt`; wire `/api/v1/auth/token/pair`, `/refresh`, `/verify`.
- Create an `AuthBearer` class; apply globally as the default `NinjaAPI(auth=...)` and use `auth=None` for public routes.
- Endpoints: register (exists — harden), login, logout (token blacklist), me, update profile, change password, request/confirm email verification, password reset.
- Reuse `CustomUser` in `user/models.py` — do not re-model.
- Tests: happy path + 401/403 matrix.

### Phase 2 — Document upload + dedup + storage (3–5 days)
- Abstract storage behind Django's `DEFAULT_FILE_STORAGE`. Start with `FileSystemStorage` locally; on VPS use `django-storages` with an S3-compatible backend (Hetzner Object Storage / Backblaze B2 / MinIO). Same code path either way.
- Implement streaming SHA-256 during upload (fix `file.chunks()` usage in `docmanage/utils.py`). Reject on per-user duplicate.
- Endpoints: `POST /documents/` (multipart), `GET /documents/` (mine + optional public), `GET /documents/{id}`, `PATCH /documents/{id}` (is_public toggle), `DELETE /documents/{id}`.
- Enforce access: `Document.objects.filter(Q(owner=user) | Q(is_public=True))` in a reusable queryset.
- Return `status=pending` immediately, enqueue Celery task `process_document(document_id)`.
- Tests: upload → duplicate → rejection; public/private visibility matrix.

### Phase 3 — Async pipeline (Celery + Redis) (3–4 days)
- Add `celery`, `redis`, `django-celery-results` to deps. Create `configuration/celery.py`.
- `docker-compose.yml` with services: `web`, `worker`, `beat`, `db` (postgres with pgvector image `pgvector/pgvector:pg16`), `redis`.
- Tasks (chained, idempotent, each its own Celery task):
  1. `detect_format(document_id)` — from magic bytes, not extension.
  2. `extract_text(document_id)` — dispatcher over extractors:
     - PDF → `pypdfium2` (fast, page-aware) or `pdfplumber`
     - DOCX → `python-docx`
     - PPTX → `python-pptx`
     - HTML → `trafilatura`
     - Images / scanned PDFs → `ocrmypdf` or `pytesseract`
     - Fallback → `unstructured` (covers many formats with one dep, at the cost of size)
  3. `chunk_document(document_id)` — page-aware, ~500–800 tokens per chunk, 10–15% overlap; always preserve `page_number`.
  4. `embed_chunks(document_id)` — LiteLLM `embedding()`, batched (e.g., 64/request), retry with exponential backoff.
  5. `index_chunks(document_id)` — bulk insert with `embedding` and `tsv = to_tsvector('english', content)`.
  6. `finalize(document_id)` — set `status=ready` (or `failed` with error message).
- Observability: Flower for local, Sentry for prod. Log every task start/end with document_id.
- Tests: a tiny PDF fixture → assert chunks + embeddings + status transitions.

### Phase 4 — Search with citations + AI summary (3–5 days)
- Service layer in `docmanage/services/search.py`:
  - `semantic_search(query, user, k=20)` — pgvector `<=>` (cosine distance), filtered by access.
  - `lexical_search(query, user, k=20)` — Postgres `plainto_tsquery` against the GIN-indexed `tsv`.
  - `hybrid_search(query, user, k=20)` — RRF fusion (`score = Σ 1/(60+rank)`).
- `summarize(query, chunks)` — LiteLLM `completion()` with a citation-constrained prompt. Return structured JSON: `{answer, citations: [{document_id, page_number, snippet}]}`. Validate with pydantic.
- Endpoint: `POST /search` → `{query}` → returns summary + citations + raw top chunks. Consider SSE streaming for the summary once the endpoint works non-streamed.
- Add DB indexes: HNSW on `embedding` (pgvector ≥0.5), GIN on `tsv`.
- Tests: seeded documents, assert citation page numbers match the source.

### Phase 5 — Production hardening (3–4 days)
- Rate limiting: `django-ratelimit` or a custom ninja middleware; per-user quotas on uploads and searches.
- Security: `django-axes` (brute-force lockout), CSP headers, HSTS, `SECURE_*` settings, content-type sniffing off.
- Logging: structured JSON via `python-json-logger`.
- Error tracking: Sentry SDK (Django + Celery integrations).
- CI: GitHub Actions — lint (ruff), type check (mypy optional), tests, build Docker image.
- Migrations: fail-on-missing-migration CI check (`manage.py makemigrations --check --dry-run`).
- Backups: pg_dump cron on the VPS; object-storage versioning.
- Dockerfile: rebuild around uv only. Production CMD: `uvicorn configuration.asgi:application --workers $N`.
- Deploy: Docker Compose on VPS with Caddy (automatic TLS) or Nginx + certbot.

### Phase 6 — Nice-to-haves (post-launch)
- Streaming answers (SSE) for search.
- Per-document "ask this document" scope.
- Usage dashboard for users.
- Per-tenant embedding model choice (LiteLLM makes this trivial).
- Reranker pass (Cohere Rerank or local bge-reranker) between retrieval and summary.

---

## Part 4 — Critical files to touch (per phase)

| Area | File |
|---|---|
| Fix models | `docmanage/models.py` |
| Fix API | `docmanage/api.py` |
| Fix utils | `docmanage/utils.py` |
| Register router | `configuration/api.py` |
| Settings hardening | `configuration/settings.py` |
| Dockerfile | `Dockerfile` |
| Dependencies | `pyproject.toml` |
| New: Celery app | `configuration/celery.py` |
| New: compose | `docker-compose.yml` |
| New: auth API | `user/api.py` (extend) |
| New: tasks | `docmanage/tasks.py` |
| New: extractors | `docmanage/extractors/` (pdf.py, docx.py, html.py, image.py) |
| New: services | `docmanage/services/{chunking,embedding,search,summary}.py` |
| New: LLM facade | `docmanage/services/llm.py` (LiteLLM wrapper) |

**Reuse, don't rebuild:**
- `CustomUser` in `user/models.py` — already has role/profile fields.
- The `calculate_hash` function in `docmanage/utils.py` — fix the typo (`chunks()`) and keep the streaming approach.
- Existing routers in `core/api.py` and `user/api.py` — follow the same `Router()` pattern for new apps.

---

## Part 5 — Verification

For each phase, "done" means all of:

- `uv run python manage.py check` is clean.
- `uv run python manage.py makemigrations --check --dry-run` passes.
- `uv run python manage.py test` passes (add tests as you go).
- `ruff check .` is clean.
- Manual smoke via `/api/docs` (django-ninja's OpenAPI UI):
  - **Phase 1:** register → login → call `/me` with bearer token.
  - **Phase 2:** upload a PDF → appears in `/documents/`; re-upload same file → 409; upload as User B → allowed (per-user dedup).
  - **Phase 3:** upload a small PDF → poll `/documents/{id}` until `status=ready`; inspect DB for chunks with non-null `embedding` and `tsv`.
  - **Phase 4:** `/search` with a query that appears on a specific page → returned citation's `page_number` matches.
  - **Phase 5:** deploy to staging VPS; hit the API over TLS; force an error and verify it lands in Sentry.

---

## Part 6 — Learning resources (ordered by phase)

- **django-ninja** — read the official docs end-to-end; it's short: https://django-ninja.dev/. Focus on `Router`, `Schema`, authentication classes, async views, file handling.
- **django-ninja-jwt** — https://github.com/eadwinCode/django-ninja-jwt. Covers token pair/refresh/blacklist.
- **Celery with Django** — official "First Steps with Django" + Celery best practices (idempotent tasks, retries, result backend). https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
- **pgvector** — the README is excellent; read the indexing section (IVFFlat vs HNSW) and the Django integration doc. https://github.com/pgvector/pgvector-python
- **Postgres FTS** — Django's `django.contrib.postgres.search` docs; read the `SearchVector`, `SearchQuery`, `SearchRank` examples.
- **Reciprocal Rank Fusion** — original paper (Cormack et al., 2009) is short and readable; Elastic's blog post explains it in 5 minutes.
- **LiteLLM** — https://docs.litellm.ai/. Cover `completion`, `embedding`, `router`, fallbacks, cost tracking.
- **RAG patterns with citations** — Anthropic's prompt-engineering cookbook on citations; LlamaIndex docs on node post-processors (even if you don't use LlamaIndex, the concepts transfer).
- **Production Django** — Adam Johnson's *Boost Your Django DX* and *Speed Up Your Django Tests* are both high-leverage. `django-stubs` for typing.
- **Docker Compose on a VPS with TLS** — Caddy's Docker Compose examples are the shortest path to automatic HTTPS.
- **Observability** — Sentry Django+Celery setup docs; `python-json-logger` for structured logs.

---

## Part 7 — Immediate next step

Start Phase 0 today. Do these in order, each as its own commit:

1. Rewrite `docmanage/models.py` (fix field errors, add `VectorField`, add `status`, switch dedup to per-user unique-together).
2. Rewrite `docmanage/api.py` (fix typos, define JWT-ready auth dependency, stub the real endpoints).
3. Fix `docmanage/utils.py` (`chunks()` typo).
4. Register the router in `configuration/api.py`.
5. Harden `configuration/settings.py` (env-driven core settings, CORS typo, remove oauth-toolkit).
6. Rewrite `Dockerfile` around uv; add `docker-compose.yml` with `web`, `db` (pgvector image), `redis` (stub for now).
7. `manage.py makemigrations && migrate`.
8. Add one smoke test per app so CI has a green baseline.

After that, Phase 1 (auth) is your first real feature.
