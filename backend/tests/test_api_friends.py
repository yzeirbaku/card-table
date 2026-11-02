"""Friends over HTTP (spec 2026-11-02-friends-and-invites)."""

from tests.test_api_accounts import bearer, client, manager, register  # noqa: F401


def test_friend_flow_over_http(client):
    a, b = register(client, "Sebi"), register(client, "Ana")
    res = client.post("/friends/requests", json={"username": "Ana"}, headers=bearer(a))
    assert res.status_code == 200
    assert res.json()["result"] == "sent"
    assert client.get("/friends", headers=bearer(b)).json()["incoming"] == ["Sebi"]
    res = client.post("/friends/requests/Sebi/accept", headers=bearer(b))
    assert res.status_code == 200
    for token, other in ((a, "Ana"), (b, "Sebi")):
        seen = client.get("/friends", headers=bearer(token)).json()
        assert seen["friends"] == [other]
        assert not seen["incoming"] and not seen["outgoing"]
    res = client.delete("/friends/Ana", headers=bearer(a))
    assert res.status_code == 200
    assert not res.json()["friends"]


def test_decline_and_cancel_over_http(client):
    a, b = register(client, "Sebi"), register(client, "Ana")
    client.post("/friends/requests", json={"username": "Ana"}, headers=bearer(a))
    assert client.delete("/friends/requests/Ana", headers=bearer(a)).json()["outgoing"] == []
    client.post("/friends/requests", json={"username": "Ana"}, headers=bearer(a))
    res = client.post("/friends/requests/Sebi/decline", headers=bearer(b))
    assert res.status_code == 200 and res.json()["incoming"] == []


def test_friends_need_a_session(client):
    calls = [
        client.get("/friends"),
        client.post("/friends/requests", json={"username": "Ana"}),
        client.post("/friends/requests/Ana/accept"),
        client.post("/friends/requests/Ana/decline"),
        client.delete("/friends/requests/Ana"),
        client.delete("/friends/Ana"),
    ]
    for res in calls:
        assert (res.status_code, res.json()["detail"]) == (401, "Signed out")


def test_refusal_detail(client):
    a = register(client)
    res = client.post("/friends/requests", json={"username": "Nobody"}, headers=bearer(a))
    assert (res.status_code, res.json()["detail"]) == (404, "No such player")


def test_username_is_capped(client):
    a = register(client)
    res = client.post("/friends/requests", json={"username": "x" * 21}, headers=bearer(a))
    assert res.status_code == 422


def test_cors_allows_delete(client):
    res = client.options("/friends/Ana", headers={
        "Origin": "http://localhost:5520",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "Authorization",
    })
    assert res.status_code == 200
    assert "DELETE" in res.headers["access-control-allow-methods"]
