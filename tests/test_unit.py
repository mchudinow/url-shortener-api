"""
Unit tests for isolated utility functions and CRUD layer.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta


# ══════════════════════════════════════════════════════════════════════════════
# utils.generate_short_code
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateShortCode:
    def test_default_length(self):
        from app.utils import generate_short_code
        code = generate_short_code()
        assert len(code) == 6

    def test_custom_length(self):
        from app.utils import generate_short_code
        for length in [4, 8, 12]:
            assert len(generate_short_code(length)) == length

    def test_only_alphanumeric(self):
        import string
        from app.utils import generate_short_code
        allowed = set(string.ascii_letters + string.digits)
        for _ in range(50):
            code = generate_short_code()
            assert set(code).issubset(allowed), f"Non-alphanumeric char in: {code}"

    def test_codes_are_random(self):
        from app.utils import generate_short_code
        codes = {generate_short_code() for _ in range(100)}
        # With 62^6 ≈ 56 billion possibilities, collisions in 100 draws are
        # astronomically unlikely.
        assert len(codes) > 90

    def test_returns_string(self):
        from app.utils import generate_short_code
        assert isinstance(generate_short_code(), str)

    def test_zero_length(self):
        from app.utils import generate_short_code
        assert generate_short_code(0) == ""


# ══════════════════════════════════════════════════════════════════════════════
# crud layer (mocked DB session)
# ══════════════════════════════════════════════════════════════════════════════

class TestCrudCreateLink:
    def _make_db(self, link_obj=None):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock(side_effect=lambda obj: None)
        return db

    def test_create_with_custom_alias(self):
        from app.crud import create_link
        db = self._make_db()
        link = create_link(db, "https://example.com", custom_alias="myalias")
        assert link.short_code == "myalias"
        assert link.original_url == "https://example.com"
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_create_generates_code_when_no_alias(self):
        from app.crud import create_link
        db = self._make_db()
        link = create_link(db, "https://example.com")
        assert len(link.short_code) == 6

    def test_create_with_expiry(self):
        from app.crud import create_link
        db = self._make_db()
        expires = datetime.utcnow() + timedelta(days=1)
        link = create_link(db, "https://example.com", expires_at=expires)
        assert link.expires_at == expires


class TestCrudGetLink:
    def test_get_existing(self, db):
        from app.crud import create_link, get_link
        create_link(db, "https://get-test.com", custom_alias="getme")
        found = get_link(db, "getme")
        assert found is not None
        assert found.original_url == "https://get-test.com"

    def test_get_nonexistent_returns_none(self, db):
        from app.crud import get_link
        assert get_link(db, "doesnotexist") is None


class TestCrudDeleteLink:
    def test_delete_existing(self, db):
        from app.crud import create_link, delete_link, get_link
        create_link(db, "https://del-test.com", custom_alias="delme")
        delete_link(db, "delme")
        assert get_link(db, "delme") is None

    def test_delete_nonexistent_does_not_raise(self, db):
        from app.crud import delete_link
        # Should not raise any exception
        delete_link(db, "ghost")


class TestCrudUpdateLink:
    def test_update_url(self, db):
        from app.crud import create_link, update_link
        create_link(db, "https://old-url.com", custom_alias="upd")
        link = update_link(db, "upd", "https://new-url.com")
        assert link.original_url == "https://new-url.com"


class TestCrudSearchByUrl:
    def test_search_existing(self, db):
        from app.crud import create_link, search_by_url
        create_link(db, "https://search-me.com", custom_alias="srch")
        found = search_by_url(db, "https://search-me.com")
        assert found is not None
        assert found.short_code == "srch"

    def test_search_nonexistent_returns_none(self, db):
        from app.crud import search_by_url
        assert search_by_url(db, "https://not-here.com") is None


# ══════════════════════════════════════════════════════════════════════════════
# cache module (unit, fully mocked redis)
# ══════════════════════════════════════════════════════════════════════════════

class TestCacheModule:
    def test_get_cache_calls_redis_get(self):
        from app import cache
        cache.redis_client = MagicMock()
        cache.redis_client.get.return_value = "https://example.com"
        result = cache.get_cache("abc123")
        cache.redis_client.get.assert_called_once_with("abc123")
        assert result == "https://example.com"

    def test_set_cache_calls_redis_set_with_ttl(self):
        from app import cache
        cache.redis_client = MagicMock()
        cache.set_cache("abc123", "https://example.com")
        cache.redis_client.set.assert_called_once_with(
            "abc123", "https://example.com", ex=3600
        )

    def test_delete_cache_calls_redis_delete(self):
        from app import cache
        cache.redis_client = MagicMock()
        cache.delete_cache("abc123")
        cache.redis_client.delete.assert_called_once_with("abc123")

    def test_get_cache_returns_none_on_miss(self):
        from app import cache
        cache.redis_client = MagicMock()
        cache.redis_client.get.return_value = None
        assert cache.get_cache("missing") is None
