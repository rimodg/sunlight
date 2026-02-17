"""
SUNLIGHT API Authentication & Rate Limiting
=============================================

API key auth with per-client rate limiting, key rotation, and usage tracking.

Key storage: SQLite table `api_keys` in the main database.
Rate limiting: In-memory sliding window per key.
Usage tracking: SQLite table `api_usage` for audit/billing.

Usage:
    from auth import require_api_key, get_auth_db
    from fastapi import Depends

    @app.get("/endpoint")
    def endpoint(client: dict = Depends(require_api_key)):
        ...
"""

import os
import sys
import time
import secrets
import hashlib
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("auth")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KEY_PREFIX = "sk_sunlight_"
KEY_BYTES = 32  # 256-bit keys
DEFAULT_RATE_LIMIT = 100       # requests per window
DEFAULT_RATE_WINDOW = 3600     # 1 hour in seconds
AUTH_ENABLED = os.environ.get("SUNLIGHT_AUTH_ENABLED", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_auth_schema(db_path: str):
    """Create auth tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL UNIQUE,
            client_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            revoked_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            rate_limit INTEGER NOT NULL DEFAULT 100,
            rate_window INTEGER NOT NULL DEFAULT 3600,
            scopes TEXT NOT NULL DEFAULT 'read,analyze',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER,
            response_time_ms REAL,
            ip_address TEXT,
            FOREIGN KEY (key_id) REFERENCES api_keys(key_id)
        );

        CREATE INDEX IF NOT EXISTS idx_api_usage_key_id ON api_usage(key_id);
        CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp ON api_usage(timestamp);
        CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def generate_api_key(db_path: str, client_name: str,
                     rate_limit: int = DEFAULT_RATE_LIMIT,
                     rate_window: int = DEFAULT_RATE_WINDOW,
                     scopes: str = "read,analyze",
                     expires_at: Optional[str] = None,
                     notes: str = "") -> dict:
    """
    Generate a new API key for a client.

    Returns the plaintext key (shown once, never stored).
    Only the SHA-256 hash is persisted.
    """
    init_auth_schema(db_path)

    raw_key = secrets.token_hex(KEY_BYTES)
    plaintext_key = f"{KEY_PREFIX}{raw_key}"
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    key_id = f"key_{secrets.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        "INSERT INTO api_keys (key_id, key_hash, client_name, created_at, "
        "expires_at, is_active, rate_limit, rate_window, scopes, notes) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
        (key_id, key_hash, client_name, now, expires_at,
         rate_limit, rate_window, scopes, notes),
    )
    conn.commit()
    conn.close()

    logger.info("API key generated",
                extra={"key_id": key_id, "client_name": client_name,
                       "rate_limit": rate_limit, "scopes": scopes})

    return {
        "key_id": key_id,
        "api_key": plaintext_key,
        "client_name": client_name,
        "created_at": now,
        "expires_at": expires_at,
        "rate_limit": rate_limit,
        "rate_window": rate_window,
        "scopes": scopes,
        "warning": "Store this key securely. It cannot be retrieved after this response.",
    }


def rotate_api_key(db_path: str, key_id: str) -> dict:
    """
    Rotate an API key: revoke the old one and generate a new one
    for the same client with the same settings.
    """
    init_auth_schema(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM api_keys WHERE key_id = ?", (key_id,))
    old_key = c.fetchone()
    if not old_key:
        conn.close()
        raise ValueError(f"Key {key_id} not found")

    old_key = dict(old_key)
    now = datetime.now(timezone.utc).isoformat()

    # Revoke old key
    c.execute(
        "UPDATE api_keys SET is_active = 0, revoked_at = ? WHERE key_id = ?",
        (now, key_id),
    )
    conn.commit()
    conn.close()

    logger.info("API key revoked for rotation",
                extra={"key_id": key_id, "client_name": old_key['client_name']})

    # Generate new key with same settings
    return generate_api_key(
        db_path,
        client_name=old_key['client_name'],
        rate_limit=old_key['rate_limit'],
        rate_window=old_key['rate_window'],
        scopes=old_key['scopes'],
        notes=f"Rotated from {key_id}",
    )


def revoke_api_key(db_path: str, key_id: str):
    """Revoke an API key."""
    init_auth_schema(db_path)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "UPDATE api_keys SET is_active = 0, revoked_at = ? WHERE key_id = ?",
        (now, key_id),
    )
    conn.commit()
    conn.close()
    logger.info("API key revoked", extra={"key_id": key_id})


def list_api_keys(db_path: str) -> list:
    """List all API keys (without hashes)."""
    init_auth_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT key_id, client_name, created_at, expires_at, revoked_at, "
        "is_active, rate_limit, rate_window, scopes, notes FROM api_keys "
        "ORDER BY created_at DESC"
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_key_usage(db_path: str, key_id: str, limit: int = 100) -> dict:
    """Get usage statistics for a key."""
    init_auth_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as total FROM api_usage WHERE key_id = ?", (key_id,))
    total = c.fetchone()['total']

    c.execute(
        "SELECT COUNT(*) as count, endpoint, method FROM api_usage "
        "WHERE key_id = ? GROUP BY endpoint, method ORDER BY count DESC",
        (key_id,),
    )
    by_endpoint = [dict(r) for r in c.fetchall()]

    c.execute(
        "SELECT timestamp, endpoint, method, status_code, response_time_ms "
        "FROM api_usage WHERE key_id = ? ORDER BY timestamp DESC LIMIT ?",
        (key_id, limit),
    )
    recent = [dict(r) for r in c.fetchall()]
    conn.close()

    return {
        "key_id": key_id,
        "total_requests": total,
        "by_endpoint": by_endpoint,
        "recent_requests": recent,
    }


# ---------------------------------------------------------------------------
# Rate limiter (in-memory sliding window)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key_id: str, limit: int, window: int) -> tuple[bool, dict]:
        """
        Check if request is allowed.

        Returns (allowed, info) where info contains:
        - remaining: requests remaining in window
        - reset: seconds until window resets
        - limit: the rate limit
        """
        now = time.time()
        cutoff = now - window

        with self._lock:
            # Prune expired entries
            timestamps = self._windows[key_id]
            self._windows[key_id] = [t for t in timestamps if t > cutoff]
            timestamps = self._windows[key_id]

            if len(timestamps) >= limit:
                reset = timestamps[0] + window - now
                return False, {
                    "remaining": 0,
                    "reset": int(reset) + 1,
                    "limit": limit,
                }

            timestamps.append(now)
            remaining = limit - len(timestamps)
            return True, {
                "remaining": remaining,
                "reset": int(window - (now - timestamps[0])) if timestamps else window,
                "limit": limit,
            }


# Module-level rate limiter instance
_rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _lookup_key(db_path: str, plaintext_key: str) -> Optional[dict]:
    """Look up an API key by its hash."""
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT key_id, client_name, is_active, rate_limit, rate_window, "
        "scopes, expires_at FROM api_keys WHERE key_hash = ?",
        (key_hash,),
    )
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def _log_usage(db_path: str, key_id: str, request: Request,
               status_code: int = 200, response_time_ms: float = 0):
    """Log API usage asynchronously."""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "INSERT INTO api_usage (key_id, timestamp, endpoint, method, "
            "status_code, response_time_ms, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key_id, datetime.now(timezone.utc).isoformat(),
             request.url.path, request.method, status_code,
             response_time_ms, request.client.host if request.client else None),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Don't let logging failures break requests


def create_auth_dependency(db_path: str):
    """
    Create a FastAPI dependency for API key authentication.

    Returns a dependency function that validates the API key,
    checks rate limits, and logs usage.
    """
    init_auth_schema(db_path)

    async def require_api_key(
        request: Request,
        api_key: Optional[str] = Security(_api_key_header),
    ) -> dict:
        # If auth is disabled, return a dummy client
        if not AUTH_ENABLED:
            return {"key_id": "anonymous", "client_name": "anonymous",
                    "scopes": "read,analyze,admin"}

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing API key. Include X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        client = _lookup_key(db_path, api_key)
        if not client:
            logger.warning("Invalid API key attempt",
                           extra={"ip": request.client.host if request.client else "unknown"})
            raise HTTPException(status_code=401, detail="Invalid API key.")

        if not client['is_active']:
            raise HTTPException(status_code=403, detail="API key has been revoked.")

        # Check expiration
        if client.get('expires_at'):
            expires = datetime.fromisoformat(client['expires_at'])
            if datetime.now(timezone.utc) > expires:
                raise HTTPException(status_code=403, detail="API key has expired.")

        # Rate limiting
        allowed, rate_info = _rate_limiter.check(
            client['key_id'], client['rate_limit'], client['rate_window']
        )
        if not allowed:
            logger.warning("Rate limit exceeded",
                           extra={"key_id": client['key_id'],
                                  "client_name": client['client_name'],
                                  "reset_sec": rate_info['reset']})
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {rate_info['reset']} seconds.",
                headers={
                    "X-RateLimit-Limit": str(rate_info['limit']),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(rate_info['reset']),
                    "Retry-After": str(rate_info['reset']),
                },
            )

        # Log usage (fire and forget)
        _log_usage(db_path, client['key_id'], request)

        return {
            "key_id": client['key_id'],
            "client_name": client['client_name'],
            "scopes": client['scopes'],
            "rate_limit_remaining": rate_info['remaining'],
            "rate_limit_reset": rate_info['reset'],
        }

    return require_api_key


# Module-level dependency that resolves DB_PATH from the api module at call time.
# This allows tests to patch api.DB_PATH and have auth pick it up.
async def require_api_key_dynamic(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> dict:
    """Module-level auth dependency that reads DB_PATH from api module."""
    # Import here to avoid circular import at module level
    import api as _api
    db_path = _api.DB_PATH

    if not AUTH_ENABLED:
        return {"key_id": "anonymous", "client_name": "anonymous",
                "scopes": "read,analyze,admin"}

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    client = _lookup_key(db_path, api_key)
    if not client:
        logger.warning("Invalid API key attempt",
                       extra={"ip": request.client.host if request.client else "unknown"})
        raise HTTPException(status_code=401, detail="Invalid API key.")

    if not client['is_active']:
        raise HTTPException(status_code=403, detail="API key has been revoked.")

    if client.get('expires_at'):
        expires = datetime.fromisoformat(client['expires_at'])
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=403, detail="API key has expired.")

    allowed, rate_info = _rate_limiter.check(
        client['key_id'], client['rate_limit'], client['rate_window']
    )
    if not allowed:
        logger.warning("Rate limit exceeded",
                       extra={"key_id": client['key_id'],
                              "client_name": client['client_name'],
                              "reset_sec": rate_info['reset']})
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {rate_info['reset']} seconds.",
            headers={
                "X-RateLimit-Limit": str(rate_info['limit']),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(rate_info['reset']),
                "Retry-After": str(rate_info['reset']),
            },
        )

    _log_usage(db_path, client['key_id'], request)

    return {
        "key_id": client['key_id'],
        "client_name": client['client_name'],
        "scopes": client['scopes'],
        "rate_limit_remaining": rate_info['remaining'],
        "rate_limit_reset": rate_info['reset'],
    }


# ---------------------------------------------------------------------------
# CLI for key management
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SUNLIGHT API Key Management")
    parser.add_argument('--db', default='data/sunlight.db')
    sub = parser.add_subparsers(dest='command')

    gen = sub.add_parser('generate', help='Generate a new API key')
    gen.add_argument('client_name', help='Client name')
    gen.add_argument('--rate-limit', type=int, default=DEFAULT_RATE_LIMIT)
    gen.add_argument('--rate-window', type=int, default=DEFAULT_RATE_WINDOW)
    gen.add_argument('--scopes', default='read,analyze')
    gen.add_argument('--expires', default=None, help='ISO 8601 expiration date')

    rot = sub.add_parser('rotate', help='Rotate an API key')
    rot.add_argument('key_id', help='Key ID to rotate')

    rev = sub.add_parser('revoke', help='Revoke an API key')
    rev.add_argument('key_id', help='Key ID to revoke')

    sub.add_parser('list', help='List all API keys')

    use = sub.add_parser('usage', help='Get usage for a key')
    use.add_argument('key_id', help='Key ID')

    args = parser.parse_args()
    db = args.db
    if not os.path.exists(db):
        db = '../data/sunlight.db'

    if args.command == 'generate':
        result = generate_api_key(db, args.client_name,
                                  rate_limit=args.rate_limit,
                                  rate_window=args.rate_window,
                                  scopes=args.scopes,
                                  expires_at=args.expires)
        print("\nAPI Key Generated:")
        print(f"  Key ID:    {result['key_id']}")
        print(f"  API Key:   {result['api_key']}")
        print(f"  Client:    {result['client_name']}")
        print(f"  Rate:      {result['rate_limit']} req/{result['rate_window']}s")
        print(f"  Scopes:    {result['scopes']}")
        print("\n  WARNING: Store this key securely. It cannot be retrieved.")

    elif args.command == 'rotate':
        result = rotate_api_key(db, args.key_id)
        print("\nKey Rotated:")
        print(f"  Old Key ID: {args.key_id} (revoked)")
        print(f"  New Key ID: {result['key_id']}")
        print(f"  API Key:    {result['api_key']}")
        print("\n  WARNING: Store this key securely. It cannot be retrieved.")

    elif args.command == 'revoke':
        revoke_api_key(db, args.key_id)
        print(f"\nKey {args.key_id} revoked.")

    elif args.command == 'list':
        keys = list_api_keys(db)
        if not keys:
            print("\nNo API keys found.")
        else:
            print(f"\n{'Key ID':<24} {'Client':<20} {'Active':<8} {'Rate':<12} {'Created':<12}")
            print("-" * 80)
            for k in keys:
                active = "YES" if k['is_active'] else "NO"
                created = k['created_at'][:10]
                print(f"{k['key_id']:<24} {k['client_name']:<20} {active:<8} "
                      f"{k['rate_limit']}/{k['rate_window']}s  {created}")

    elif args.command == 'usage':
        usage = get_key_usage(db, args.key_id)
        print(f"\nUsage for {args.key_id}: {usage['total_requests']} total requests")
        if usage['by_endpoint']:
            print(f"\n  {'Endpoint':<30} {'Method':<8} {'Count':<8}")
            print("  " + "-" * 50)
            for e in usage['by_endpoint']:
                print(f"  {e['endpoint']:<30} {e['method']:<8} {e['count']:<8}")

    else:
        parser.print_help()
