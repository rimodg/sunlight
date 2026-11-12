"""Operator-local append-only journal and frozen, privacy-admitted captures.

The hash chain detects accidental changes. It is not a signature or protection
against an administrator rewriting the entire database. Keep external backups.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from watch_identity import canonical, digest


def utc(value):
    if not isinstance(value, str):
        raise ValueError("Explicit UTC timestamp required")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timezone required")
    return date.astimezone(timezone.utc).isoformat(timespec="microseconds")


def admit(value):
    """Fail closed on known personal fields and email-shaped content.

    Not a privacy classifier. Source policy must additionally be reviewed for
    organization-only scope. No raw response is persisted before admission.
    """
    forbidden = {"contactpoint", "email", "emailaddress", "telephone", "phone",
                 "beneficiary", "beneficiaries", "person", "persons", "personname"}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower().replace("_", "").replace("-", "") in forbidden:
                raise ValueError("protection_boundary")
            admit(child)
    elif isinstance(value, list):
        for child in value:
            admit(child)
    elif isinstance(value, str) and re.search(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", value):
        raise ValueError("protection_boundary")


class Journal:
    def __init__(self, path, *, readonly=False):
        self.path = Path(path)
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=30)
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS watch_events (
                    seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL,
                    previous TEXT NOT NULL, hash TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS watch_event_cutoff ON watch_events(at,kind);
                CREATE TRIGGER IF NOT EXISTS watch_no_update BEFORE UPDATE ON watch_events
                    BEGIN SELECT RAISE(ABORT,'append only'); END;
                CREATE TRIGGER IF NOT EXISTS watch_no_delete BEFORE DELETE ON watch_events
                    BEGIN SELECT RAISE(ABORT,'append only'); END;
            """)
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    def append(self, kind, at, payload):
        return self.append_many([(kind, at, payload)])[0]

    def append_many(self, entries):
        prepared = []
        for kind, at, payload in entries:
            at = utc(at)
            admit(payload)
            prepared.append((kind, at, payload, digest({"kind": kind, "at": at, "payload": payload})))
        ids = []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for kind, at, payload, event_id in prepared:
                ids.append(event_id)
                if self.db.execute("SELECT id FROM watch_events WHERE id=?", (event_id,)).fetchone():
                    continue
                last = self.db.execute("SELECT hash FROM watch_events ORDER BY seq DESC LIMIT 1").fetchone()
                previous = last[0] if last else "0" * 64
                chain_hash = digest({"id": event_id, "previous": previous})
                self.db.execute("INSERT INTO watch_events(id,kind,at,payload,previous,hash) VALUES(?,?,?,?,?,?)",
                                (event_id, kind, at, canonical(payload), previous, chain_hash))
        return ids

    def events(self, *, as_of=None, kind=None):
        clauses, args = [], []
        if as_of is not None:
            clauses.append("at<=?"); args.append(utc(as_of))
        if kind:
            clauses.append("kind=?"); args.append(kind)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in
                self.db.execute("SELECT * FROM watch_events" + where + " ORDER BY seq", args)]

    def verify(self):
        previous = "0" * 64
        for e in self.events():
            expected = digest({"kind": e["kind"], "at": e["at"], "payload": e["payload"]})
            if e["id"] != expected or e["previous"] != previous or e["hash"] != digest({"id": expected, "previous": previous}):
                raise ValueError("journal_integrity_failed")
            previous = e["hash"]
        return previous

    def freeze(self, source, url, at, projection, policy_hash, observations=None, *, source_sha256):
        from watch_projection import SCHEMA, VERSIONS
        if (not isinstance(projection, dict) or projection.get("schema") != SCHEMA
                or projection.get("adapter_version") != VERSIONS.get(projection.get("adapter"))):
            raise ValueError("projection_schema")
        if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
            raise ValueError("source_digest_required")
        admit(projection)
        payload = {"source": source, "url": url, "sha256": source_sha256,
                   "projection": projection, "projection_sha256": digest(projection),
                   "adapter_version": projection["adapter_version"], "policy_hash": policy_hash,
                   "captured_at": utc(at)}
        cid = digest({"kind": "capture", "at": utc(at), "payload": payload})
        entries = [("capture", at, payload)]
        if observations is not None:
            entries.append(("observations", at, {**observations, "capture": cid}))
        return self.append_many(entries)[0]

    def capture(self, event_id):
        row = self.db.execute("SELECT payload FROM watch_events WHERE id=? AND kind='capture'", (event_id,)).fetchone()
        if row is None:
            raise KeyError(event_id)
        payload = json.loads(row[0])
        if "body" in payload:
            raise ValueError("legacy_raw_capture_requires_explicit_migration")
        if digest(payload["projection"]) != payload["projection_sha256"]:
            raise ValueError("capture_integrity_failed")
        return payload
