"""Read-only views of the operator journal. No capture or model in a request."""
from contextlib import contextmanager
from html import escape
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from watch_engine import now
from watch_health import health
from watch_identity import canonical
from watch_journal import Journal
from watch_packet import packet

router = APIRouter(prefix="/watch-engine", tags=["Organizational watch ledger"])


@contextmanager
def opened():
    data = os.environ.get("SUNLIGHT_WATCH_DATA_DIR")
    if not data:
        raise HTTPException(503, "Watch journal not configured. No observations claimed.")
    root = Path(__file__).resolve().parents[1]
    folder = Path(data).expanduser().resolve()
    if folder == root or root in folder.parents:
        raise HTTPException(503, "Watch operational data must be outside the repository")
    if not (folder / "journal.sqlite3").is_file():
        raise HTTPException(503, "Watch journal not recorded yet")
    journal = Journal(folder / "journal.sqlite3", readonly=True)
    try:
        journal.db.execute("BEGIN")
        journal.verify()
        yield journal
    except ValueError:
        raise HTTPException(503, "Watch journal integrity check failed")
    finally:
        journal.close()


def latest(journal):
    events = journal.events(kind="examination")
    return events[-1] if events else None


@router.get("/status")
def status():
    with opened() as journal:
        last = latest(journal)
        return {"health": health(journal, now()), "examination": last,
                "journal_head": journal.verify()}


@router.get("/subjects")
def subjects():
    with opened() as journal:
        last = latest(journal)
        return {"examination": last["id"] if last else None,
                "subjects": last["payload"]["result"]["subjects"] if last else []}


@router.get("/examinations")
def examinations():
    with opened() as journal:
        return {"examinations": [{"id": e["id"], "as_of": e["at"], "changes": e["payload"]["changes"],
                                    "build": e["payload"]["build"]} for e in journal.events(kind="examination")]}


@router.get("/subjects/{subject_id}")
def subject(subject_id: str):
    with opened() as journal:
        last = latest(journal)
        result = last["payload"]["result"] if last else {}
        item = next((s for s in result.get("subjects", []) if s["id"] == subject_id), None)
        if item is None:
            raise HTTPException(404, "Subject absent from latest examination; inspect historical examinations for former identities")
        ids = set(item["observations"])
        return {"examination": last["id"], "subject": item,
                "observations": [o for o in result["observations"] if o["id"] in ids],
                "readings": [r for r in result["readings"] if r["observation"] in ids],
                "open_questions": [q for q in result["open_questions"] if q["observation"] in ids]}


@router.get("/events/{event_id}")
def event(event_id: str):
    with opened() as journal:
        found = next((e for e in journal.events() if e["id"] == event_id), None)
        if found is None:
            raise HTTPException(404, "No such journal receipt")
        return found


@router.get("/captures/{capture_id}")
def capture(capture_id: str):
    with opened() as journal:
        try:
            item = journal.capture(capture_id)
        except KeyError:
            raise HTTPException(404, "No such frozen capture")
        return Response(item["body"].encode(), media_type="application/json",
                        headers={"X-Content-SHA256": item["sha256"], "X-Content-Type-Options": "nosniff"})


@router.get("/packets/{examination_id}")
def export_packet(examination_id: str):
    with opened() as journal:
        try:
            value = packet(journal, examination_id)
        except KeyError:
            raise HTTPException(404, "No such examination")
        return Response(canonical(value), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="watch-packet-{examination_id}.json"'})


def text(value):
    return escape("Unknown" if value is None else str(value))


def receipt(value):
    return f'<a href="./events/{quote(value)}">{text(value)}</a>' if value else "Not recorded"


@router.get("/ui", response_class=HTMLResponse)
def ui(subject: str | None = None, examination: str | None = None):
    with opened() as journal:
        h = health(journal, now())
        last = latest(journal)
        if examination:
            last = next((e for e in journal.events(kind="examination") if e["id"] == examination), None)
            if last is None:
                raise HTTPException(404, "No such historical examination")
        result = last["payload"]["result"] if last else None
        schedule = h["scheduler"]
        state = "Overdue" if schedule["overdue"] else "Unknown" if schedule["overdue"] is None else "Within interval"
        html = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
                "<title>SUNLIGHT | Subject ledger</title><style>body{background:#0c1c24;color:#dce7e9;font:16px/1.6 system-ui;margin:0}main{max-width:1200px;margin:auto;padding:24px;overflow-wrap:anywhere}a{color:#eed28d;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{padding:12px;border-bottom:1px solid #344a54;text-align:left;vertical-align:top;overflow-wrap:anywhere}article{border:1px solid #344a54;padding:18px;margin:18px 0}code{overflow-wrap:anywhere}small{display:block;color:#adc1c8}.scroll{overflow:auto}</style><main>",
                "<h1>SUNLIGHT | Subject ledger</h1><p>Organizational structural screening. Indicator, never allegation.</p>",
                '<nav><a href="./ui">Population</a> | <a href="./subjects">Subject register</a> | <a href="./status">Journal status</a> | <a href="./ui">Refresh from journal</a></nav>',
                f'<h2>Watch health: {state}</h2><p>Last run: {text(schedule["last_started"])}. Outcome: {text(schedule["outcome"])}. Poll: {text(schedule["interval_seconds"])} seconds.</p>',
                f'<small>Receipt: {receipt(schedule["receipt"])}. Receipts do not prove current process liveness.</small>',
                f'<p>Last-run build: <code>{text(canonical(schedule["build"]) if schedule["build"] else None)}</code></p>',
                '<div class=scroll><table><tr><th>Source</th><th>Last reached</th><th>Outcome</th><th>Silence / interval</th><th>Schedule</th><th>Last good capture</th><th>Receipt</th></tr>']
        for s in h["sources"]:
            state = "Overdue" if s["overdue"] else "Unknown" if s["overdue"] is None else "Within interval"
            good = f'<a href="./captures/{s["last_good_capture"]}">{text(s["last_good_capture"])}</a>' if s["last_good_capture"] else 'Not recorded'
            html.append(f'<tr><td>{text(s["source"])}</td><td>{text(s["last_reached"])}</td><td>{text(s["outcome"])}</td><td>{text(s["silence_seconds"])} / {text(s["interval_seconds"])} seconds</td><td>{state}</td><td>{good}</td><td>{receipt(s["receipt"])}</td></tr>')
        html.append('</table></div>')
        html.append('<details><summary>Examination history</summary><p>Health above is current. A selected examination below is historical.</p>')
        for e in reversed(journal.events(kind="examination")):
            html.append(f'<p><a href="./ui?examination={e["id"]}">{text(e["at"])}</a> | {receipt(e["id"])}</p>')
        html.append('</details>')
        if not h["sources"]:
            html.append('<p>No configured sources recorded. This is silence, not zero world activity.</p>')
        if result is None:
            html.append('<p>No examination recorded. No population or findings claimed.</p>')
        else:
            html.append(f'<p>Examination as of {text(result["as_of"])}. {receipt(last["id"])} | <a href="./packets/{last["id"]}">Download replay packet</a></p>')
            html.append(f'<p>{text(result["scope"])}</p><h2>Subjects</h2>')
            for s in result["subjects"]:
                if subject and subject != s["id"]:
                    continue
                html.append(f'<article><h3><a href="./ui?subject={s["id"]}&amp;examination={last["id"]}">{text(canonical(s["identifiers"]) if s["identifiers"] else s["id"])}</a></h3><p>{text(s["state"])} | {text(", ".join(s["categories"]))}</p>')
                if subject:
                    ids = set(s["observations"])
                    for mapping in s["citations"]:
                        html.append(f'<p>Identifier evidence: {text(canonical(mapping))}</p>')
                    for obs in result["observations"]:
                        if obs["id"] not in ids:
                            continue
                        ev = obs["evidence"]
                        html.append(f'<h4>{text(obs["category"])} | {text(obs["key"])}</h4><p>Captured {text(obs["captured_at"])}. Published {text(obs["published_at"])}.</p>')
                        html.append(f'<p><a href="./captures/{ev["capture"]}">Frozen source document</a> | <a href="{text(ev["url"])}">Publisher URL</a><small>Locator: {text(ev["locator"])}. SHA-256: {text(ev["sha256"])}</small></p>')
                        for reading in result["readings"]:
                            if reading["observation"] == obs["id"]:
                                html.append(f'<p><strong>{text(reading["rule"])}: {text(reading["status"])}</strong> {text(reading["description"])}<small>{text(reading["citation"])}</small></p>')
                                if reading.get("input_basis"):
                                    html.append(f'<p>Input basis: {text(reading["input_basis"]["requires"])}. Available: {text(reading["input_basis"]["available"])}.</p>')
                        for q in result["open_questions"]:
                            if q["observation"] == obs["id"]:
                                html.append(f'<p>{text(q["status"])}: {text(q["reason"])}. Open since {text(q["since"])}; {text(q["age_seconds"])} seconds at examination.</p>')
                html.append('</article>')
            html.append('<h2>Changes in this examination</h2>')
            for key, values in last["payload"]["changes"].items():
                html.append(f'<p>{text(key)}: {text(", ".join(values) if values else "None recorded in this examination")}</p>')
        html.append('</main></html>')
        return HTMLResponse("".join(html), headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'", "X-Content-Type-Options": "nosniff"})
