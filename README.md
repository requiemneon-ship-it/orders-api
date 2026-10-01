# Orders API

[![CI](https://github.com/requiemneon-ship-it/orders-api/actions/workflows/ci.yml/badge.svg)](https://github.com/requiemneon-ship-it/orders-api/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![License](https://img.shields.io/badge/license-MIT-green)

**EN** — A small REST API for managing customer orders, built with FastAPI and SQLite: validation, filtering and pagination, an order status workflow, API-key protection for write operations and automated tests.
**RU** — Небольшой REST API для учёта заказов на FastAPI и SQLite: валидация, фильтры и пагинация, жизненный цикл статусов, защита записи API-ключом и автотесты.

## Endpoints

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | – | Liveness check |
| POST | `/orders` | key | Create an order (`total` is calculated) |
| GET | `/orders` | – | List: `status`, `customer`, `limit` (1–100), `offset` |
| GET | `/orders/{id}` | – | Get one order |
| PATCH | `/orders/{id}/status` | key | Change status (rules below) |
| DELETE | `/orders/{id}` | key | Delete an order |

Interactive docs (Swagger UI): `http://localhost:8000/docs`.

**Status workflow:** `new → in_progress → done`, and `new` / `in_progress → cancelled`. `done` and `cancelled` are final; an invalid move returns `409`.

**Auth:** write endpoints require the `X-API-Key` header matching the `API_KEY` environment variable. If `API_KEY` is not set, writes are refused with `503` rather than silently left open.

## Run

```bash
pip install -r requirements.txt
export API_KEY=change-me          # PowerShell: $env:API_KEY = "change-me"
uvicorn app.main:app --reload
```

```bash
curl -X POST localhost:8000/orders \
  -H 'X-API-Key: change-me' -H 'content-type: application/json' \
  -d '{"customer":"Alex","item":"Landing page","quantity":2,"unit_price":150}'

curl "localhost:8000/orders?status=new&limit=10"
```

The database file is `orders.db` (override with `ORDERS_DB`).

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

16 tests cover validation, auth (including an unconfigured key), the status state machine, filters and pagination, LIKE-wildcard escaping, SQL-injection-looking input and deletion. Every test uses its own temporary database.

## Design notes

- SQL is always parameterized; user input in `LIKE` filters is escaped so `%` and `_` match literally.
- API-key comparison uses `hmac.compare_digest` (constant time).
- A new SQLite connection per request keeps the code thread-safe without shared state.
- Not included on purpose: user accounts, migrations tooling, rate limiting. They are the natural next steps for a production service.

## Structure

```
app/main.py      routes, auth dependency, status transitions
app/schemas.py   Pydantic models and the status state machine
app/db.py        SQLite schema and connection helper
tests/test_api.py
```

## License

MIT
