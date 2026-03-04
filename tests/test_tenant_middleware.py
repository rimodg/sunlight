"""
Tests for SUNLIGHT TenantMiddleware
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from tenant_middleware import TenantMiddleware, DEFAULT_TENANT_ID


def create_test_app(db_session_factory=None):
    """Create a minimal FastAPI app with TenantMiddleware."""
    app = FastAPI()
    app.add_middleware(TenantMiddleware, db_session_factory=db_session_factory)

    @app.get("/tenant-check")
    async def tenant_check(request: Request):
        return {"tenant_id": request.state.tenant_id}

    return app


class TestTenantMiddleware:
    """Test tenant resolution from headers, query params, and defaults."""

    def test_tenant_from_header(self):
        app = create_test_app()
        client = TestClient(app)
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": "ten_acme"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "ten_acme"
        assert resp.headers["X-Tenant-ID"] == "ten_acme"

    def test_tenant_from_query_param(self):
        app = create_test_app()
        client = TestClient(app)
        resp = client.get("/tenant-check?tenant_id=ten_globex")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "ten_globex"

    def test_default_tenant_when_missing(self):
        app = create_test_app()
        client = TestClient(app)
        resp = client.get("/tenant-check")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == DEFAULT_TENANT_ID

    def test_header_takes_precedence_over_query(self):
        app = create_test_app()
        client = TestClient(app)
        resp = client.get(
            "/tenant-check?tenant_id=ten_query",
            headers={"X-Tenant-ID": "ten_header"},
        )
        assert resp.json()["tenant_id"] == "ten_header"

    def test_tenant_id_sanitized(self):
        app = create_test_app()
        client = TestClient(app)
        # Whitespace should be stripped
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": "  ten_spaces  "})
        assert resp.json()["tenant_id"] == "ten_spaces"

    def test_tenant_id_truncated(self):
        app = create_test_app()
        client = TestClient(app)
        long_id = "t" * 200
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": long_id})
        assert len(resp.json()["tenant_id"]) == 100

    def test_response_header_set(self):
        app = create_test_app()
        client = TestClient(app)
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": "ten_echo"})
        assert resp.headers["X-Tenant-ID"] == "ten_echo"

    def test_db_session_factory_called(self):
        """Verify that db_session_factory is called to set PG session var."""
        calls = []

        class MockConn:
            def execute(self, sql, params):
                calls.append((sql, params))

        def mock_factory():
            return MockConn()

        app = create_test_app(db_session_factory=mock_factory)
        client = TestClient(app)
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": "ten_pg"})
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0][1] == ("ten_pg",)

    def test_db_session_factory_error_handled(self):
        """If db_session_factory raises, request should still succeed."""
        def broken_factory():
            raise RuntimeError("DB unavailable")

        app = create_test_app(db_session_factory=broken_factory)
        client = TestClient(app)
        resp = client.get("/tenant-check", headers={"X-Tenant-ID": "ten_err"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "ten_err"
