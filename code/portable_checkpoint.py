"""Portable local evidence checkpoints. Never merge or overwrite an active ledger."""
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile

from connectivity import state_directory

SCHEMA = 'sunlight.offline-checkpoint.v1'
MAX_FILE = 256*1024*1024
MAX_TOTAL = 512*1024*1024
MAX_FILES = 300


def checksum(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def allowed_path(name):
    return name=='operations.sqlite3' or bool(re.fullmatch(r'empirical_[A-Za-z0-9_-]+\.json',name)) or bool(re.fullmatch(r'trade-cache/[A-Za-z0-9_-]+\.json',name))


def runtime_fingerprint():
    versions={}
    for name in ('numpy','scipy','networkx','fastapi','pydantic','httpx','pdfplumber'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]='not_installed'
    return {'python':platform.python_version(),'packages':versions}


@lru_cache(maxsize=1)
def source_fingerprints():
    root=Path(__file__).resolve().parents[1]
    files=[]
    for folder in [root/'code',root/'research/corpus',root/'data']:
        if folder.exists():
            files.extend(p for p in folder.rglob('*') if p.is_file() and not p.is_symlink() and p.suffix in {'.py','.json','.csv','.yaml','.yml','.sql'} and '__pycache__' not in p.parts)
    return {str(p.relative_to(root)):checksum(p) for p in sorted(files)}


def create_checkpoint(output):
    from operations import connection, db_path
    output=Path(output)
    if output.exists():raise ValueError('Checkpoint destination already exists')
    state=state_directory();state.mkdir(parents=True,exist_ok=True)
    # Initialize a fresh local store; SQLite's backup API includes committed WAL
    # contents and yields one consistent database snapshot while writers run.
    with connection():pass
    with tempfile.TemporaryDirectory(prefix='.checkpoint-',dir=state) as temp:
        database=Path(temp)/'operations.sqlite3'
        with sqlite3.connect(db_path().resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(database) as target:
            source.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Ledger integrity check failed')
        files={'operations.sqlite3':database}
        for p in [*state.glob('empirical_*.json'),*(state/'trade-cache').glob('*.json')]:
            relative=p.relative_to(state).as_posix()
            if allowed_path(relative) and not p.is_symlink() and p.is_file():
                # Freeze each atomically stored sidecar before hashing/compression.
                frozen=Path(temp)/relative;frozen.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(p,frozen);files[relative]=frozen
        if len(files)>MAX_FILES or any(p.stat().st_size>MAX_FILE for p in files.values()) or sum(p.stat().st_size for p in files.values())>MAX_TOTAL:
            raise ValueError('Checkpoint exceeds the supported size or file count')
        manifest={'schema_version':SCHEMA,'created_at':datetime.now(timezone.utc).isoformat(),
                  'scope':'Entire registered deployment ledger, uploaded PDF originals, investigations, review and action histories; empirical calibration sidecars and retained trade previews.',
                  'source_files':source_fingerprints(),
                  'runtime':runtime_fingerprint(),
                  'entries':{name:{'bytes':p.stat().st_size,'sha256':checksum(p)} for name,p in files.items()},
                  'integrity_limit':'Content hashes detect changed bytes. They are not issuer signatures or protection against an archive author rewriting its contents and manifest.',
                  'consistency':'SQLite transactionally consistent; calibration/cache sidecars captured individually. Quiesce writes for a checkpoint aligned across all stores.'}
        output.parent.mkdir(parents=True,exist_ok=True)
        try:
            with output.open('xb') as raw:
                os.chmod(output,0o600)
                with zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('manifest.json',json.dumps(manifest,sort_keys=True,indent=2))
                    for name,p in files.items():archive.write(p,name)
        except BaseException:
            output.unlink(missing_ok=True);raise
    return manifest


def verify_checkpoint(path):
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist();names=[i.filename for i in infos]
        if len(infos)>MAX_FILES+1 or len(names)!=len(set(names)) or 'manifest.json' not in names:raise ValueError('Invalid checkpoint file list')
        if archive.getinfo('manifest.json').file_size>1024*1024:raise ValueError('Manifest exceeds limit')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('schema_version')!=SCHEMA or not isinstance(manifest.get('entries'),dict):raise ValueError('Unsupported checkpoint format')
        entries=manifest['entries']
        if set(names)!=set(entries)|{'manifest.json'} or 'operations.sqlite3' not in entries:raise ValueError('Checkpoint contains missing or undeclared files')
        total=0
        for name,expected in entries.items():
            info=archive.getinfo(name)
            if not allowed_path(name) or stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise ValueError('Unsafe checkpoint entry')
            if not isinstance(expected,dict) or type(expected.get('bytes')) is not int or not re.fullmatch('[0-9a-f]{64}',str(expected.get('sha256',''))):raise ValueError('Invalid entry declaration')
            if info.file_size!=expected['bytes'] or not 0<=info.file_size<=MAX_FILE:raise ValueError('Invalid entry size')
            total+=info.file_size
            if total>MAX_TOTAL:raise ValueError('Checkpoint exceeds total limit')
            h=hashlib.sha256();size=0
            with archive.open(name) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    size+=len(block)
                    if size>expected['bytes']:raise ValueError('Expanded entry exceeds declared size')
                    h.update(block)
            if size!=expected['bytes'] or h.hexdigest()!=expected['sha256']:raise ValueError('Checkpoint content hash mismatch')
        sources=manifest.get('source_files')
        if not isinstance(sources,dict) or not 1<=len(sources)<=2000 or any(not isinstance(k,str) or not k.startswith(('code/','data/','research/corpus/')) or '..' in k.split('/') or not re.fullmatch('[0-9a-f]{64}',str(v)) for k,v in sources.items()):
            raise ValueError('Source fingerprint manifest missing or invalid')
        try:
            if datetime.fromisoformat(manifest['created_at']).tzinfo is None:raise ValueError()
        except (KeyError,TypeError,ValueError):raise ValueError('Checkpoint creation timestamp missing or invalid')
        if not isinstance(manifest.get('runtime'),dict) or not isinstance(manifest['runtime'].get('packages'),dict) or not isinstance(manifest['runtime'].get('python'),str):raise ValueError('Runtime version manifest missing')
        return manifest


def restore_checkpoint(path,directory,allow_different_version=False):
    # Restoration is a maintenance operation, never an API write or auto-sync.
    # Stage it beside a destination that does not yet exist; no live data merge.
    manifest=verify_checkpoint(path);destination=Path(directory).absolute()
    if destination.exists() or destination.is_symlink():raise ValueError('Restore destination must not exist; existing records are never overwritten')
    if (manifest['source_files']!=source_fingerprints() or manifest['runtime']!=runtime_fingerprint()) and not allow_different_version:
        raise ValueError('Checkpoint engine/source/runtime version differs; use its matching installation or explicitly allow a version change')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.restore-',dir=destination.parent))
    try:
        os.chmod(staging,0o700)
        with zipfile.ZipFile(path) as archive:
            for name in manifest['entries']:
                target=staging/name;target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as out,archive.open(name) as src:shutil.copyfileobj(src,out)
                if target.stat().st_size!=manifest['entries'][name]['bytes'] or checksum(target)!=manifest['entries'][name]['sha256']:
                    raise ValueError('Checkpoint changed during restoration')
                os.chmod(target,0o600)
        with sqlite3.connect((staging/'operations.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Restored ledger integrity check failed')
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'op_sources','op_revisions','op_audit'}.issubset(tables):raise ValueError('Expected ledger tables missing')
        if destination.exists():raise ValueError('Restore destination appeared during verification; no files replaced')
        staging.rename(destination)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['export','verify','restore'])
    parser.add_argument('archive',type=Path)
    parser.add_argument('--directory',type=Path,help='New destination directory for a stopped local instance')
    parser.add_argument('--allow-different-version',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='export':result=create_checkpoint(args.archive)
        elif args.action=='verify':result=verify_checkpoint(args.archive)
        else:
            if not args.directory:parser.error('restore requires --directory')
            result=restore_checkpoint(args.archive,args.directory,args.allow_different_version)
        print(json.dumps({'action':args.action,'verified_files':len(result['entries']),'checkpoint_created_at':result['created_at']}))
    except (ValueError,OSError,sqlite3.Error,zipfile.BadZipFile,KeyError,TypeError) as exc:
        print('Checkpoint operation failed: '+str(exc));return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
