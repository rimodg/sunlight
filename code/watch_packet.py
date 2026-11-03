"""Portable frozen-input replay. Packets are operational artifacts, never Git data."""
import tempfile
from pathlib import Path

from watch_engine import build_identity, snapshot
from watch_identity import canonical, digest
from watch_journal import Journal


def packet(journal, examination_id):
    journal.verify()
    examination = next((e for e in journal.events(kind="examination") if e["id"] == examination_id), None)
    if examination is None:
        raise KeyError(examination_id)
    cutoff = examination["at"]
    inputs = [e for e in journal.events(as_of=cutoff) if e["kind"] in {"capture", "observations"}]
    return {"schema": "sunlight.watch-packet.v1", "examination": examination,
            "inputs": inputs, "result_sha256": digest(examination["payload"]["result"]),
            "limits": "This replays frozen inputs. It does not authenticate a publisher or prove a source claim."}


def replay(value, *, reader=None):
    if value.get("schema") != "sunlight.watch-packet.v1":
        raise ValueError("packet_schema")
    exam = value["examination"]
    if digest({"kind": exam["kind"], "at": exam["at"], "payload": exam["payload"]}) != exam["id"]:
        raise ValueError("packet_examination_digest")
    if exam["payload"]["build"]["source_sha256"] != build_identity()["source_sha256"]:
        raise ValueError("replay_requires_matching_rule_build")
    with tempfile.TemporaryDirectory(prefix="sunlight-replay-") as folder:
        journal = Journal(Path(folder) / "journal.sqlite3")
        try:
            for e in value["inputs"]:
                if e["kind"] not in {"capture", "observations"}:
                    raise ValueError("packet_input_kind")
                eid = journal.append(e["kind"], e["at"], e["payload"])
                if eid != e["id"]:
                    raise ValueError("packet_input_digest")
            result = snapshot(journal, exam["at"], reader=reader)
            if canonical(result) != canonical(exam["payload"]["result"]) or digest(result) != value["result_sha256"]:
                raise ValueError("packet_replay_mismatch")
            return result
        finally:
            journal.close()
