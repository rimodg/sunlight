#!/usr/bin/env python3
"""Verify retained research bytes locally; never contact or mutate the watch."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'research' / 'invariant_core'


def verify(path, entry):
    raw = path.read_bytes()
    if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError(f'Evidence mismatch: {path}')
    print(f"OK {path.name} {len(raw)} {entry['sha256']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Directory containing the original nine XML files')
    args = parser.parse_args()
    entries = json.loads((ROOT / 'sources.json').read_text())
    for entry in entries:
        path = args.source_dir / entry['path'] if args.source_dir else Path(entry['local_path'])
        verify(path, entry)
        verify(ROOT / entry['extract']['path'], entry['extract'])
    sample = json.loads((ROOT / 'watch-fields.json').read_text())
    verify(ROOT / 'watch-example.json', {'bytes': sample['example_bytes'], 'sha256': sample['example_sha256']})
    print(f'{len(entries)} original sources, {len(entries)} extracts and one example verified; hashing alone does not authenticate sources')


if __name__ == '__main__':
    main()
