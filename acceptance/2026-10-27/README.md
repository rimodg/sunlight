# Frozen owner acceptance evidence, 2026-10-27

These files are owner-supplied evidence of a run performed on the owner's machine
on 2026-10-27. They were not produced in the build environment and have not been
independently reproduced there. Preserve the four supplied files byte for byte.
Do not replace them with newer captures or use them as an operational feed.

The owner reports 27,985 award releases scanned across ten months, 4,489 distinct
GB-COH suppliers, 202 IATI organisations and 20 organisations matched on normalised
identifier. These figures are provenance supplied by the owner. This admission
check did not recompute the population or reproduce the intersection.

## Files and dates

- `intersection.json` and `cf_state.json` were produced on the owner's machine
  on 2026-10-27. The supplied state is the redacted version described below.
- `candidates.json` was re-fetched on 2026-11-02 after the original was cleared
  from a temporary folder. The owner reports 7,912 activity rows in the refetch
  versus 7,911 on 2026-10-27, with the same 202 organisations. This is not the
  original October 27 candidate capture.
- `hashes.txt` is the owner's original path-bearing hash list. Paths in it are
  provenance strings, not instructions or paths to access. Verification matches
  the terminal filenames against the three supplied JSON files.
- `manifest.json` records SHA-256 digests for all four supplied files, including
  the hash list itself. JSON bytes were not reformatted.

## Protection provenance

The owner reports that one supplier-name position in `cf_state.json` held a
personal email address and was replaced by a redaction marker at the protection
boundary. The owner reports a sweep of the whole file found only that one entry.
The state file therefore has a new hash; the other two JSON hashes are unchanged.

As reported by the owner: the buyer published a person's email address in an
open award notice, the protection rule caught it before it entered the
repository, and the match was unaffected because the join was made on the
company identifier.

On 2026-11-03 the build environment checked the supplied hashes, parsed the JSON,
confirmed a redaction marker and found no email-shaped strings in the supplied
JSON bytes. This is a limited admission check, not independent verification of
the original notice, the owner's full protection sweep or the matching result.
No public source requests were made for this check.

## Verify without network access

From the repository root:

```bash
python3 - <<'PYVERIFY'
from pathlib import Path
import hashlib, json, re
root = Path('acceptance/2026-10-27')
manifest = json.loads((root / 'manifest.json').read_text())
expected = {f['name']: f for f in manifest['files']}
assert set(expected) == {'candidates.json', 'intersection.json', 'cf_state.json', 'hashes.txt'}
for name, entry in expected.items():
    data = (root / name).read_bytes()
    assert len(data) == entry['size_bytes'], name
    assert hashlib.sha256(data).hexdigest() == entry['sha256'], name
listed = {}
for line in (root / 'hashes.txt').read_text().splitlines():
    match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(.+)', line)
    assert match, 'Malformed hash line'
    name = Path(match[2]).name
    assert name in expected and name != 'hashes.txt' and name not in listed
    listed[name] = match[1].lower()
assert set(listed) == set(expected) - {'hashes.txt'}
for name, digest in listed.items():
    assert expected[name]['sha256'] == digest, name
print('Verified: all four manifest digests and all three supplied JSON hashes')
PYVERIFY
```
