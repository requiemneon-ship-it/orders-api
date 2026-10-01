import pytest
from fastapi.testclient import TestClient

from app.main import app

KEY = {"X-API-Key": "test-key"}
ORDER = {"customer": "Alex", "item": "Landing page", "quantity": 2, "unit_price": 150.5}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORDERS_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("API_KEY", "test-key")
    with TestClient(app) as c:  # context manager runs the lifespan (DB init)
        yield c


def create(client, **overrides):
    resp = client.post("/orders", json={**ORDER, **overrides}, headers=KEY)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_order_computes_total(client):
    created = create(client)
    assert created["total"] == 301.0
    assert created["status"] == "new"
    fetched = client.get(f"/orders/{created['id']}").json()
    assert fetched == created


def test_writes_require_api_key(client):
    assert client.post("/orders", json=ORDER).status_code == 401
    assert client.post("/orders", json=ORDER, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/orders").status_code == 200  # reads are public


def test_writes_refused_when_key_not_configured(client, monkeypatch):
    monkeypatch.delenv("API_KEY")
    assert client.post("/orders", json=ORDER, headers=KEY).status_code == 503


@pytest.mark.parametrize(
    "bad",
    [
        {"quantity": 0},
        {"quantity": -1},
        {"unit_price": -5},
        {"customer": "   "},
        {"item": ""},
        {"quantity": "many"},
    ],
)
def test_validation_rejects_bad_input(client, bad):
    resp = client.post("/orders", json={**ORDER, **bad}, headers=KEY)
    assert resp.status_code == 422


def test_missing_order_is_404(client):
    assert client.get("/orders/999").status_code == 404
    assert client.patch("/orders/999/status", json={"status": "done"}, headers=KEY).status_code == 404


def test_status_flow_and_forbidden_transitions(client):
    oid = create(client)["id"]
    assert client.patch(f"/orders/{oid}/status", json={"status": "done"}, headers=KEY).status_code == 409
    ok = client.patch(f"/orders/{oid}/status", json={"status": "in_progress"}, headers=KEY)
    assert ok.status_code == 200 and ok.json()["status"] == "in_progress"
    assert client.patch(f"/orders/{oid}/status", json={"status": "done"}, headers=KEY).status_code == 200
    # finished orders are final
    assert client.patch(f"/orders/{oid}/status", json={"status": "cancelled"}, headers=KEY).status_code == 409
    assert client.patch(f"/orders/{oid}/status", json={"status": "bogus"}, headers=KEY).status_code == 422


def test_list_filters_and_pagination(client):
    for i in range(5):
        create(client, customer=f"Cust{i}")
    first = create(client, customer="Special_Client")
    client.patch(f"/orders/{first['id']}/status", json={"status": "cancelled"}, headers=KEY)

    page = client.get("/orders", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 6 and len(page["items"]) == 2
    assert page["items"][0]["id"] > page["items"][1]["id"]  # newest first

    assert client.get("/orders", params={"status": "cancelled"}).json()["total"] == 1
    assert client.get("/orders", params={"customer": "cust"}).json()["total"] == 5
    assert client.get("/orders", params={"limit": 0}).status_code == 422
    assert client.get("/orders", params={"status": "nope"}).status_code == 422


def test_customer_filter_escapes_like_wildcards(client):
    create(client, customer="Special_Client")
    create(client, customer="SpecialXClient")
    # '_' must be matched literally, not as a single-character wildcard
    assert client.get("/orders", params={"customer": "Special_Client"}).json()["total"] == 1
    assert client.get("/orders", params={"customer": "%"}).json()["total"] == 0


def test_sql_injection_attempt_is_inert(client):
    create(client, customer="x'); DROP TABLE orders;--")
    assert client.get("/orders").json()["total"] == 1


def test_delete(client):
    oid = create(client)["id"]
    assert client.delete(f"/orders/{oid}").status_code == 401
    assert client.delete(f"/orders/{oid}", headers=KEY).status_code == 204
    assert client.get(f"/orders/{oid}").status_code == 404
    assert client.delete(f"/orders/{oid}", headers=KEY).status_code == 404
