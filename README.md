# CNPJ Lookup Service

A small REST service that **consumes a public API** ([BrasilAPI](https://brasilapi.com.br) – CNPJ and CEP endpoints),
**stores the results in SQLite**, and **exposes them through its own endpoints**.
It is a compact example of a real integration: call an external API, survive its failures, cache the data, and serve it again.

**Stack:** Python 3.10+, FastAPI, httpx, SQLite (standard library).

## Features

| Feature | Where |
|---|---|
| Input validation (CNPJ check digits, CEP format) | `app/validators.py` |
| Error handling for 404, timeouts, 429 (rate limit), 5xx | `app/client.py`, `app/main.py` |
| Retry with exponential backoff (+ jitter) for temporary failures | `app/retry.py` |
| Response caching in SQLite with a TTL | `app/service.py`, `app/db.py` |
| Stale-cache fallback when the upstream API is down | `app/service.py` |
| Request logging (method, path, status, duration) | `app/main.py` |
| Unit tests (no network needed) | `tests/test_core.py` |
| Postman collection with test scripts | `postman/` |

## Setup

```bash
git clone <your-repo-url> && cd cnpj-lookup-service
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000 and the interactive docs at http://127.0.0.1:8000/docs.

### Configuration (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `DB_PATH` | `lookups.db` | SQLite file |
| `CACHE_TTL_SECONDS` | `86400` | How long a cached answer is considered fresh |
| `BRASILAPI_BASE_URL` | `https://brasilapi.com.br/api` | Upstream base URL |

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/company/{cnpj}` | Company data (accepts `00.000.000/0001-91` or digits only) |
| GET | `/companies?limit=20&offset=0` | Companies already cached, most recent first |
| GET | `/cep/{cep}` | Address data (accepts `01001-000` or digits only) |

### Example

```bash
curl http://127.0.0.1:8000/company/00000000000191
```

```json
{
  "source": "api",
  "fetched_at": "2026-10-29T16:30:00+00:00",
  "data": { "...": "payload returned by BrasilAPI" }
}
```

`source` tells you where the answer came from:

- `api` – fetched just now from BrasilAPI
- `cache` – served from SQLite (still fresh)
- `cache-stale` – the API failed, so an expired cached copy was served instead

### Error responses

| Situation | Status |
|---|---|
| Invalid CNPJ/CEP | 422 |
| Company/CEP does not exist upstream | 404 |
| Upstream rate limit (429) after all retries | 503 |
| Upstream timeout after all retries | 504 |
| Other upstream failure | 502 |

## Tests

Unit tests cover validation, retry/backoff and the cache logic, and need no network or extra packages:

```bash
python -m unittest discover -s tests -v
```

Manual API tests: import `postman/cnpj-lookup-service.postman_collection.json` into Postman
(variable `baseUrl` = `http://127.0.0.1:8000`) and run the collection with the service running.

## Design notes

- **Retry only what is temporary.** Timeouts, network errors, 429 and 5xx are retried with backoff;
  a 404 or a validation error is not, because trying again cannot help.
- **Stale data beats no data, except for 404.** If BrasilAPI is down and an old copy exists, it is served
  and labeled `cache-stale`. If the API says the resource does not exist, old data is never served.
- **Validate before calling out.** Invalid CNPJs/CEPs are rejected locally, saving upstream calls.
- **Layers are separated** (validators, retry, db, service, client, API) so the core logic is testable without FastAPI or the network.

## Limitations / ideas for next steps

- SQLite and one connection per request are fine for a demo; use a connection pool or PostgreSQL for real traffic.
- No authentication or per-client rate limiting on this service's own endpoints.
- Add async httpx, API tests with FastAPI's `TestClient`, a Dockerfile and a GitHub Actions workflow.


## Demo mode (no dependency on the real API)

`tools/fake_brasilapi.py` is a local stand-in for BrasilAPI that returns **fake sample data**.
It is useful to demo or test retry, caching and fallback when the real API is rate limiting.

```bash
python tools/fake_brasilapi.py                  # terminal 1: fake upstream on :9000
python tools/fake_brasilapi.py --fail-first 2   # simulate two 429s before succeeding
```

```powershell
# terminal 2 (PowerShell): point the service at the fake upstream, use a separate DB
$env:BRASILAPI_BASE_URL="http://127.0.0.1:9000/api"
$env:DB_PATH="demo.db"
uvicorn app.main:app --reload
```

CNPJ `11222333000181` returns 404 in the fake server, to demo the "not found" path.


## Lessons learned

- **Slashes in path parameters:** a formatted CNPJ such as `00.000.000/0001-91` contains a `/`. A Postman test
  returned 404 because the plain `{cnpj}` route does not match it. Declaring the route as `{cnpj:path}` fixed it.
- **Rate limiting is real:** the public API returned 429 during testing. Retry with exponential backoff, a stale-cache
  fallback and a local mock server (`tools/fake_brasilapi.py`) made it possible to validate the behavior anyway.
- **Not found is not a temporary failure:** a 404 from upstream is never retried and never answered from stale cache.
