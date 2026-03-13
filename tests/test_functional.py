"""
Functional tests for all API endpoints using FastAPI TestClient.
Covers: create, redirect, delete, update, stats, search — happy paths and error cases.
"""
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta


# ══════════════════════════════════════════════════════════════════════════════
# POST /links/shorten
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateLink:
    def test_create_basic(self, client):
        resp = client.post("/links/shorten", json={"original_url": "https://example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_url"] == "https://example.com"
        assert len(data["short_code"]) == 6

    def test_create_with_custom_alias(self, client):
        resp = client.post("/links/shorten", json={
            "original_url": "https://example.com",
            "custom_alias": "mylink"
        })
        assert resp.status_code == 200
        assert resp.json()["short_code"] == "mylink"

    def test_create_with_expiry(self, client):
        expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
        resp = client.post("/links/shorten", json={
            "original_url": "https://example.com",
            "expires_at": expires
        })
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is not None

    def test_create_duplicate_returns_existing(self, client):
        payload = {"original_url": "https://dup-test.com"}
        r1 = client.post("/links/shorten", json=payload)
        r2 = client.post("/links/shorten", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["short_code"] == r2.json()["short_code"]

    def test_create_missing_url_field(self, client):
        resp = client.post("/links/shorten", json={})
        assert resp.status_code == 422

    def test_create_empty_body(self, client):
        resp = client.post("/links/shorten", content=b"")
        assert resp.status_code in (422, 400)

    def test_create_multiple_distinct_links(self, client):
        codes = set()
        for i in range(5):
            r = client.post("/links/shorten", json={"original_url": f"https://example{i}.com"})
            assert r.status_code == 200
            codes.add(r.json()["short_code"])
        assert len(codes) == 5


# ══════════════════════════════════════════════════════════════════════════════
# GET /{short_code}  — redirect
# ══════════════════════════════════════════════════════════════════════════════

class TestRedirect:
    def test_redirect_existing_link(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://redirect-target.com",
            "custom_alias": "redir1"
        })
        resp = client.get("/redir1", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "redirect-target.com" in resp.headers["location"]

    def test_redirect_nonexistent_returns_404(self, client):
        resp = client.get("/nonexistent_code", follow_redirects=False)
        assert resp.status_code == 404

    def test_redirect_expired_link_returns_410(self, client):
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        client.post("/links/shorten", json={
            "original_url": "https://expired.com",
            "custom_alias": "explink",
            "expires_at": past
        })
        resp = client.get("/explink", follow_redirects=False)
        assert resp.status_code == 410

    def test_redirect_increments_clicks(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://clicks-test.com",
            "custom_alias": "clk"
        })
        client.get("/clk", follow_redirects=False)
        client.get("/clk", follow_redirects=False)
        stats = client.get("/links/clk/stats").json()
        assert stats["clicks"] == 2

    def test_redirect_served_from_cache(self, client):
        """When cache returns a value, DB should not be queried."""
        from app import cache as cache_module
        cache_module.redis_client.get.return_value = "https://cached.com"

        with patch("app.main.get_cache", return_value="https://cached.com"):
            resp = client.get("/anything", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "cached.com" in resp.headers["location"]


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /links/{short_code}
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteLink:
    def test_delete_existing(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://to-delete.com",
            "custom_alias": "dodel"
        })
        resp = client.delete("/links/dodel")
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}

    def test_deleted_link_returns_404_on_redirect(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://gone.com",
            "custom_alias": "gone1"
        })
        client.delete("/links/gone1")
        resp = client.get("/gone1", follow_redirects=False)
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_200(self, client):
        # current implementation doesn't raise on missing link
        resp = client.delete("/links/nope")
        assert resp.status_code == 200

    def test_delete_clears_cache(self, client):
        """delete_cache must be called after deleting a link."""
        client.post("/links/shorten", json={
            "original_url": "https://cache-clear.com",
            "custom_alias": "cc1"
        })
        with patch("app.main.delete_cache") as mock_del:
            client.delete("/links/cc1")
            mock_del.assert_called_once_with("cc1")


# ══════════════════════════════════════════════════════════════════════════════
# PUT /links/{short_code}
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateLink:
    def test_update_url(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://before.com",
            "custom_alias": "upd1"
        })
        resp = client.put("/links/upd1", json={"original_url": "https://after.com"})
        assert resp.status_code == 200
        assert resp.json()["original_url"] == "https://after.com"

    def test_update_missing_body(self, client):
        resp = client.put("/links/any", json={})
        assert resp.status_code == 422

    def test_update_clears_cache(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://upd-cache.com",
            "custom_alias": "uc1"
        })
        with patch("app.main.delete_cache") as mock_del:
            client.put("/links/uc1", json={"original_url": "https://new-url.com"})
            mock_del.assert_called_once_with("uc1")

    def test_update_redirect_uses_new_url(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://before2.com",
            "custom_alias": "upd2"
        })
        client.put("/links/upd2", json={"original_url": "https://after2.com"})
        resp = client.get("/upd2", follow_redirects=False)
        assert "after2.com" in resp.headers["location"]


# ══════════════════════════════════════════════════════════════════════════════
# GET /links/{short_code}/stats
# ══════════════════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_initial(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://stats-test.com",
            "custom_alias": "st1"
        })
        resp = client.get("/links/st1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_url"] == "https://stats-test.com"
        assert data["clicks"] == 0
        assert data["last_used"] is None

    def test_stats_updates_after_click(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://stats-clicks.com",
            "custom_alias": "st2"
        })
        client.get("/st2", follow_redirects=False)
        data = client.get("/links/st2/stats").json()
        assert data["clicks"] == 1
        assert data["last_used"] is not None

    def test_stats_nonexistent_returns_404(self, client):
        resp = client.get("/links/ghost123/stats")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# GET /links/search
# ══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    def test_search_existing_url(self, client):
        client.post("/links/shorten", json={
            "original_url": "https://searchable.com",
            "custom_alias": "srch1"
        })
        resp = client.get("/links/search", params={"original_url": "https://searchable.com"})
        assert resp.status_code == 200
        assert resp.json()["short_code"] == "srch1"

    def test_search_nonexistent_returns_404(self, client):
        resp = client.get("/links/search", params={"original_url": "https://nope.com"})
        assert resp.status_code == 404

    def test_search_missing_param_returns_422(self, client):
        resp = client.get("/links/search")
        assert resp.status_code == 422
