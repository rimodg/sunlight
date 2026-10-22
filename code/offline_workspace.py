"""Offline capability and explicit, deployment-wide portable checkpoints."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from starlette.background import BackgroundTask

from connectivity import offline_enabled, state_directory
from operations import connection
from portable_checkpoint import create_checkpoint

router=APIRouter(prefix='/offline',tags=['Offline workspace'])


@router.get('/guide',response_class=HTMLResponse)
def guide():
    from readable_reports import page
    return page('SUNLIGHT local and offline installation','''
    <p>Use the prepared local edition on a computer with Docker Engine or Docker Desktop installed. Install Docker and obtain the package while a connection is available, or have your institution supply them through its normal offline distribution process.</p>
    <h2>Start the prepared edition</h2><ol><li>Extract the SUNLIGHT offline bundle.</li><li>On macOS/Linux run <code>sh start.sh</code>. On Windows run <code>powershell -File start.ps1</code> from the extracted folder.</li><li>The launcher verifies the image archive checksum and loads it locally. No image pull is performed.</li><li>Open <code>http://127.0.0.1:8000/watch/</code> in a browser.</li></ol>
    <p>The backend runs locally with offline policy enabled, durable Docker volume storage, and an internal Docker network. The public watch sources and analytical engines are included. Cloud AI and external refreshes are disabled. Closing the browser does not delete the volume.</p>
    <h2>Evidence portability</h2><p>Download a full evidence checkpoint from Offline workspace before changing machines. It contains all registered records and uploaded originals, across every country, and should be handled as a copy of that deployment's records.</p>
    <p>To verify a checkpoint with the installed image, run <code>python -m portable_checkpoint verify checkpoint.zip</code> inside the local installation. To restore, use <code>python -m portable_checkpoint restore checkpoint.zip --directory /app/calibration/restored</code> while the service is stopped, with the checkpoint mounted read-only. The destination must not already exist. Then select that data directory for the new local instance. The package's OFFLINE.md provides complete Docker commands.</p>
    <p>Keep the checkpoint's matching engine/image version. A changed version requires an explicit maintenance decision; restoration never silently merges records or uploads them to another deployment.</p>
    <h2>What travels through existing mechanisms</h2><p>Import source records through Records &amp; review; enter attributed sender/recipient references, delivery acceptance and source documents through Delivery assurance. Local evidence search and saved inquiries work on retained records. An authorized institutional system may supply these records over the local network or via a carried file.</p>
    <p>Trade previews are reused from a checked disk cache when available. Missing previews remain unavailable. Packaged statistical datasets and source observations retain their actual dates; no internet connection is needed to calculate from them. New facts still require new delivered evidence.</p>
    <p>Local content hashes and audit chains preserve traceability. They do not independently authenticate the original issuing bank, supplier, recipient or field observer. Ephemeral session analysis caches are not durable records; register source records or save an investigation before a restart.</p>
    ''','Local engine · no external network required for retained evidence')


@router.get('/status')
def status():
    with connection() as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def count(table):return db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] if table in tables else 0
        last=db.execute('SELECT MAX(received_at),MAX(published_at) FROM op_revisions').fetchone()
        records={'source_revisions':count('op_revisions'),'obligations':count('assurance_obligations'),
                 'evidence_entries':count('assurance_evidence'),'investigations':count('research_inquiries'),
                 'documents':count('research_documents')}
    from watch_money import SNAPSHOT
    return {'offline_policy':offline_enabled(),'mode':'local_analysis_no_external_network' if offline_enabled() else 'connected_deployment',
            'checked_at':datetime.now(timezone.utc).isoformat(),'records':records,
            'last_source_record_received_at':last[0],'last_source_record_published_at':last[1],
            'clock_note':'Deadline-sensitive checks use this instance’s clock. Verify system time when working without a trusted time service.',
            'monetary_extract':{'revision':SNAPSHOT['source_revision'],'retrieved_at':SNAPSHOT['retrieved_at'],'years':SNAPSHOT['years']},
            'capabilities':['Packaged monetary, procurement, material, arms and conflict context','Local procurement and delivery engines','Attributed debit/credit and acceptance reconciliation','Document reading, cited evidence search, review and follow-up','Readable briefs and portable evidence checkpoints'],
            'external_services':'Remote refreshes, cloud model requests and non-loopback Python socket traffic are disabled.' if offline_enabled() else 'Remote data services may be requested by connected features; this status does not test internet reachability.',
            'traceability':'Stable source/event/transfer/issuer references, retained source revisions, document hashes and local audit chains. These remain usable without internet; their hashes do not authenticate external issuers.',
            'arrival_limit':'New events require delivered records: local forms, attributable file imports, an authorized local system or a later connection. No observation is invented during an interruption.',
            'checkpoint_scope':'Entire deployment, including PDF originals and saved investigations; not limited by the current country filter.',
            'restart_limit':'Persistent storage is required. Ephemeral in-process analysis/dossier caches are not checkpointed; save source records and investigations for durable work.'}


@router.get('/checkpoint')
def checkpoint():
    # Uses the same access gate as all submitted records. Restoration is CLI-only
    # and refuses an existing destination; downloading cannot alter live data.
    state=state_directory();state.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='.download-',dir=state))
    output=folder/'sunlight-evidence-checkpoint.zip'
    try:create_checkpoint(output)
    except (ValueError,OSError,sqlite3.Error) as exc:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(409,'Checkpoint could not be completed; existing records were not changed') from exc
    return FileResponse(output,media_type='application/zip',filename='sunlight-evidence-checkpoint.zip',
                        headers={'Cache-Control':'no-store'},background=BackgroundTask(shutil.rmtree,folder,ignore_errors=True))
