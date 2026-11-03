"""Cited organizational identity. Names and arrival order never create joins."""
from __future__ import annotations

import hashlib
import json
import re

POLICY = "sunlight.cited-organisations.gb-coh-pad8.v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalise(scheme, published):
    """No whitespace, case or prefix repairs. Invalid identifiers stay unresolved."""
    if not isinstance(published, str):
        return None
    if scheme == "GB-COH":
        if re.fullmatch(r"[0-9]{1,8}", published):
            return published.zfill(8)
        if re.fullmatch(r"[A-Z]{2}[0-9]{6}", published):
            return published
    if scheme == "LEI" and re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", published):
        # ISO 17442 / ISO 7064 checksum. A cited but invalid LEI cannot join.
        expanded = "".join(str(ord(c) - 55) if c.isalpha() else c for c in published)
        if int(expanded) % 97 == 1:
            return published
    return None


def identifier(scheme, published, locator):
    return {"scheme": scheme, "published_value": published,
            "normalised_value": normalise(scheme, published),
            "locator": locator, "policy": POLICY}


def resolve(observations):
    """Resolve explicit co-cited identifiers, retaining unresolved parties as nodes.

    A party's identifiers must come from that party's source record. A name,
    location, publisher ID or activity ID is never an organizational identifier.
    Component IDs are canonical for the complete as-of graph. Adding a bridge can
    change its ID; historical snapshots retain the former ID and membership.
    """
    parent, rows = {}, []

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            key = parent[key]
        return key

    for obs in sorted(observations, key=lambda x: x["id"]):
        for index, party in enumerate(obs.get("parties", [])):
            mappings, keys = [], []
            for raw in party.get("identifiers", []):
                item = identifier(raw.get("scheme"), raw.get("value"), raw.get("locator"))
                mappings.append(item)
                if item["normalised_value"] is not None and item["locator"]:
                    keys.append((item["scheme"], item["normalised_value"]))
            keys = sorted(set(keys))
            for key in keys:
                root = min(find(key), find(keys[0]))
                parent[find(key)] = root
                parent[find(keys[0])] = root
            rows.append((obs, index, party, mappings, keys))
    components = {}
    for key in sorted(parent):
        components.setdefault(find(key), []).append(key)
    subjects = {}
    for obs, index, party, mappings, keys in rows:
        members = components[find(keys[0])] if keys else []
        sid = digest({"identifiers": members}) if keys else digest({"unresolved": [obs["id"], index]})
        subject = subjects.setdefault(sid, {"id": sid, "state": "resolved" if keys else "unresolved",
                                          "identifiers": members, "observations": [], "citations": []})
        subject["observations"].append(obs["id"])
        subject["citations"].append({"observation": obs["id"], "party_index": index,
                                     "identifiers": mappings})
    for subject in subjects.values():
        subject["observations"] = sorted(set(subject["observations"]))
        subject["citations"].sort(key=canonical)
    return sorted(subjects.values(), key=lambda x: x["id"])
