from __future__ import annotations

import hmac
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from . import db
from .schemas import TRANSITIONS, Order, OrderCreate, OrderPage, Status, StatusUpdate


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="Orders API",
    version="1.0.0",
    description="Small REST API for managing customer orders.",
    lifespan=lifespan,
)


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Write endpoints need the key from the API_KEY environment variable.

    If API_KEY is not set the server refuses writes instead of silently allowing them.
    """
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY is not configured on the server")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")


def to_order(row: sqlite3.Row) -> Order:
    data = dict(row)
    data["total"] = round(data["quantity"] * data["unit_price"], 2)
    return Order(**data)


def fetch_order(conn: sqlite3.Connection, order_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
    return row


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orders", response_model=Order, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
def create_order(payload: OrderCreate) -> Order:
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO orders (customer, item, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (payload.customer, payload.item, payload.quantity, payload.unit_price),
        )
        return to_order(fetch_order(conn, int(cur.lastrowid)))


@app.get("/orders", response_model=OrderPage)
def list_orders(
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    customer: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderPage:
    where, params = [], []
    if status_filter:
        where.append("status = ?")
        params.append(status_filter.value)
    if customer:
        where.append("customer LIKE ? ESCAPE '\\'")
        escaped = customer.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM orders {clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM orders {clause} ORDER BY id DESC LIMIT ? OFFSET ?", [*params, limit, offset]
        ).fetchall()
    return OrderPage(items=[to_order(r) for r in rows], total=total, limit=limit, offset=offset)


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: int) -> Order:
    with db.connect() as conn:
        return to_order(fetch_order(conn, order_id))


@app.patch("/orders/{order_id}/status", response_model=Order, dependencies=[Depends(require_api_key)])
def update_status(order_id: int, payload: StatusUpdate) -> Order:
    with db.connect() as conn:
        row = fetch_order(conn, order_id)
        current = Status(row["status"])
        if payload.status not in TRANSITIONS[current]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Cannot move order from '{current.value}' to '{payload.status.value}'",
            )
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            (payload.status.value, order_id),
        )
        return to_order(fetch_order(conn, order_id))


@app.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
def delete_order(order_id: int) -> None:
    with db.connect() as conn:
        fetch_order(conn, order_id)
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
