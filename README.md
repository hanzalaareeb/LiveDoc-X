# LiveDocX

LiveDocX is a Django Ninja API for authenticated document storage. The current
milestone provides JWT authentication, user profiles, secure uploads,
per-user deduplication, and private/public document access control.

The parsing, embedding, background-processing, and semantic-search system is
the next milestone. Its design is documented in `ARCHITECTURE_REVIEW.md`; it is
not represented by placeholder endpoints in the current API.

## Current API

- `POST /api/v1/user/register/` — register with an email and password.
- `POST /api/v1/token/pair` — obtain access and refresh tokens.
- `POST /api/v1/token/refresh` — rotate a refresh token.
- `POST /api/v1/token/verify` — verify a token.
- `POST /api/v1/token/blacklist` — revoke a refresh token.
- `GET/PATCH /api/v1/user/me/` — read or update the current profile.
- `POST /api/v1/user/me/change_password/` — change the password.
- `POST /api/v1/document/upload` — upload a document as multipart form data.
- `GET /api/v1/document/` — list owned documents; add
  `?include_public=true` to include public documents.
- `GET/PATCH/DELETE /api/v1/document/{id}` — read, change visibility, or delete.
- `GET /api/v1/core/health` — public health check.

Except for registration, token operations, and the health check, endpoints
require `Authorization: Bearer <access-token>`. Interactive OpenAPI docs are at
`/api/v1/docs` while the development server is running.

## Local setup

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), PostgreSQL with
pgvector, and Redis when using the configured cache.

```bash
cp .env.example .env
uv sync --dev
uv run python manage.py migrate
uv run python manage.py runserver
```

Replace the placeholders in `.env` before running the application. The first
migration enables the PostgreSQL `vector` extension, so the database user must
be allowed to create it (or an administrator must enable it once).

For a lightweight local test run, SQLite is supported for the currently tested
auth and document-management paths:

```bash
DATABASE_URL=sqlite:///test.sqlite3 \
SECRET_KEY=0123456789abcdef0123456789abcdef \
uv run python manage.py test
```

## Quality checks

```bash
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run ruff check .
uv run ruff format --check .
```
