"""Package an already built SUNLIGHT image for installation without downloads.

Uses Docker's existing configured daemon/credentials. No registry upload or
application records are included. Recipients need Docker installed beforehand.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

START_SH='''#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if command -v sha256sum >/dev/null 2>&1; then sha256sum -c SHA256SUMS;
elif command -v shasum >/dev/null 2>&1; then shasum -a 256 -c SHA256SUMS;
else echo "A SHA-256 checker is required before loading the image." >&2; exit 1; fi
image_id=$(cat image-id.txt)
platform=$(cat platform.txt)
if ! docker image inspect "$image_id" >/dev/null 2>&1; then docker image load --input image.tar.gz; fi
if [ "$(docker image inspect --format '{{.Id}}' "$image_id")" != "$image_id" ]; then echo "Image identity mismatch" >&2; exit 1; fi
if docker container inspect sunlight-offline >/dev/null 2>&1; then
  if [ "$(docker container inspect --format '{{.Image}}' sunlight-offline)" != "$image_id" ]; then echo "Existing installation uses another image. Its records were not changed; follow OFFLINE.md before upgrading." >&2; exit 1; fi
  if [ "$(docker container inspect --format '{{range .Config.Env}}{{if eq . "SUNLIGHT_OFFLINE=1"}}active{{end}}{{end}}' sunlight-offline)" != active ]; then echo "Existing container does not have offline policy enabled. No changes made." >&2; exit 1; fi
  docker start sunlight-offline >/dev/null
  echo "Open http://127.0.0.1:8000/watch/ after its health check passes. Existing records were retained."
  exit 0
fi
volume=${SUNLIGHT_STATE_VOLUME:-sunlight-offline-state}
subdir=${SUNLIGHT_DATA_SUBDIR:-}
case "$subdir" in *..*|/*|*\\\\*) echo "Use a simple relative data subdirectory" >&2; exit 1;; esac
data_dir=/app/calibration
if [ -n "$subdir" ]; then data_dir="$data_dir/$subdir"; fi
docker network inspect sunlight-offline-browser >/dev/null 2>&1 || docker network create sunlight-offline-browser >/dev/null
if [ "$(docker network inspect --format '{{.Internal}}' sunlight-offline-browser)" != false ]; then echo "Existing network blocks the local browser port; no container started." >&2; exit 1; fi
docker volume create "$volume" >/dev/null
docker run -d --pull=never --platform "$platform" --name sunlight-offline --network sunlight-offline-browser \\
  -p 127.0.0.1:8000:8000 --restart unless-stopped --read-only --tmpfs /tmp:size=64m,mode=1777 \\
  --cap-drop ALL --security-opt no-new-privileges \\
  --mount "type=volume,src=$volume,dst=/app/calibration" \\
  -e SUNLIGHT_OFFLINE=1 -e "SUNLIGHT_CALIBRATION_DIR=$data_dir" "$image_id"
echo "SUNLIGHT is starting locally. Open http://127.0.0.1:8000/watch/"
echo "Records stay in Docker volume: $volume. No external refresh or cloud AI is enabled."
'''

START_PS='''$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
foreach ($line in Get-Content SHA256SUMS) {
  $parts = $line -split "  ", 2
  if ((Get-FileHash -Algorithm SHA256 $parts[1]).Hash.ToLower() -ne $parts[0]) { throw "Bundle checksum mismatch" }
}
$imageId = (Get-Content image-id.txt -Raw).Trim()
$platform = (Get-Content platform.txt -Raw).Trim()
docker image inspect $imageId *> $null
if ($LASTEXITCODE -ne 0) { docker image load --input image.tar.gz; if ($LASTEXITCODE -ne 0) { throw "Image load failed" } }
if ((docker image inspect --format '{{.Id}}' $imageId) -ne $imageId) { throw "Image identity mismatch" }
docker container inspect sunlight-offline *> $null
if ($LASTEXITCODE -eq 0) {
  if ((docker container inspect --format '{{.Image}}' sunlight-offline) -ne $imageId) { throw "Existing installation uses another image; records were not changed. See OFFLINE.md." }
  $policy = docker container inspect --format '{{range .Config.Env}}{{if eq . "SUNLIGHT_OFFLINE=1"}}active{{end}}{{end}}' sunlight-offline
  if ($policy -ne "active") { throw "Existing container does not have offline policy enabled" }
  docker start sunlight-offline | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Existing local instance did not start" }
  Write-Output "Open http://127.0.0.1:8000/watch/ after startup. Existing records were retained."; exit 0
}
$volume = if ($env:SUNLIGHT_STATE_VOLUME) { $env:SUNLIGHT_STATE_VOLUME } else { "sunlight-offline-state" }
$dataDir = "/app/calibration"
if ($env:SUNLIGHT_DATA_SUBDIR) {
  if ($env:SUNLIGHT_DATA_SUBDIR -match "(^/|\\.\\.|\\\\)") { throw "Use a simple relative data subdirectory" }
  $dataDir += "/" + $env:SUNLIGHT_DATA_SUBDIR
}
docker network inspect sunlight-offline-browser *> $null
if ($LASTEXITCODE -ne 0) { docker network create sunlight-offline-browser | Out-Null; if ($LASTEXITCODE -ne 0) { throw "Network creation failed" } }
if ((docker network inspect --format '{{.Internal}}' sunlight-offline-browser) -ne "false") { throw "Existing network blocks the local browser port" }
docker volume create $volume | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Volume creation failed" }
docker run -d --pull=never --platform $platform --name sunlight-offline --network sunlight-offline-browser -p 127.0.0.1:8000:8000 --restart unless-stopped --read-only --tmpfs /tmp:size=64m,mode=1777 --cap-drop ALL --security-opt no-new-privileges --mount "type=volume,src=$volume,dst=/app/calibration" -e SUNLIGHT_OFFLINE=1 -e "SUNLIGHT_CALIBRATION_DIR=$dataDir" $imageId
if ($LASTEXITCODE -ne 0) { throw "Local start failed" }
Write-Output "Open http://127.0.0.1:8000/watch/ after startup. Records stay in the Docker volume."
'''


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',required=True,type=Path,help='New bundle directory; a sibling ZIP is also created')
    args=parser.parse_args();folder=args.output.absolute();archive=folder.with_suffix('.zip')
    if folder.exists() or archive.exists():parser.error('Output paths must not already exist')
    meta=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]
    folder.mkdir(parents=True)
    try:
        saved=folder/'image.tar.gz'
        with saved.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as compressed:
            proc=subprocess.Popen(['docker','image','save',meta['Id']],stdout=subprocess.PIPE)
            try:shutil.copyfileobj(proc.stdout,compressed,1024*1024)
            finally:proc.stdout.close()
            if proc.wait():raise RuntimeError('Docker image export failed')
        (folder/'image-id.txt').write_text(meta['Id']+'\n')
        (folder/'platform.txt').write_text(meta['Os']+'/'+meta['Architecture']+'\n')
        (folder/'start.sh').write_text(START_SH);(folder/'start.sh').chmod(0o755)
        (folder/'start.ps1').write_text(START_PS)
        shutil.copyfile(ROOT/'docs/OFFLINE.md',folder/'OFFLINE.md')
        (folder/'bundle.json').write_text(json.dumps({'format':'sunlight.offline-installation.v1','image_id':meta['Id'],
            'platform':meta['Os']+'/'+meta['Architecture'],'source_revision':meta['Config'].get('Labels',{}).get('org.opencontainers.image.revision'),
            'records_included':False,'requires':'Docker Engine or Docker Desktop already installed; CPU architecture supported directly or by Docker emulation.',
            'integrity_limit':'Checksums identify unchanged bytes; obtain the bundle and its source identity through a trusted channel.'},indent=2))
        (folder/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(folder.iterdir())))
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_STORED) as output:
            for p in sorted(folder.iterdir()):output.write(p,p.name)
        print(json.dumps({'bundle':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive),'image_id':meta['Id']}))
    except BaseException:
        shutil.rmtree(folder);archive.unlink(missing_ok=True);raise


if __name__=='__main__':main()
