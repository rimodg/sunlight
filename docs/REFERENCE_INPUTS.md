# Corpus location of record

Both exact files were independently read and verified on November 12, 2026,
on the owner's Mac. These locators are now committed in
`config/reference-inputs.json`; neither artifact is committed to Git.

| Artifact | Absolute path | Measured bytes | SHA-256 |
|---|---|---:|---|
| Database | `/Users/rimodg/brain/SUNLIGHT/data/sunlight.db` | 169349120 | `d90c30354df7a5c5ffe912d3fff095d6387ae5a568a38975853cd778d7aeeb8e` |
| Cases | `/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/prosecuted_cases.json` | 6821 | `f196d1f3a36dc820ce3fe33fc2885faad791700b0326a0e81a07dd9db850dc2f` |

The cases file is restored byte for byte from Git blob
`b0043dca177daffb6bce8c05363efba617ce31d4`, not reconstructed from descriptions.
The database's measured digest and size both match the owner's supplied receipt.
The source files remain in place and are not modified by verification.
A recorded local location is not a backup or access for another reviewer.

## Required pre-run verification command

Run this exact command before either evaluator. Exit 0 requires both SHA-256
hashes and both recorded byte sizes to match; a mismatch exits 2. Do not proceed
on failure or substitute a different corpus.

```bash
'/Users/rimodg/Documents/Codex/2026-11-09/realtime-voice-chat-2/runtime-3.12.14/bin/python' \
  '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/scripts/verify_reference_inputs.py' \
  --db '/Users/rimodg/brain/SUNLIGHT/data/sunlight.db' \
  --cases '/Users/rimodg/Documents/ChatGPT/Sunlight(the new SIGI)/prosecuted_cases.json'
```

Admission only verifies inputs. It does not assert that an evaluator ran or a
floor passed. The exact run settings are seed 42, 1,000 bootstrap iterations,
200 presumed-negative comparisons and `doj_federal` for `evaluation.py`.
The second evaluator, `doj_validation.py`, has no profile option. Pass the same
explicit input paths and separate external report destinations to both.
Unset `SUNLIGHT_DB_PATH` before the first evaluator, since that environment
variable takes precedence over its `--db` argument.

The reference population consists of synthesized positive price examples and
presumed-negative comparisons. A new regression measurement is not field
accuracy, a money-recovery result or independent verification of the case claims.
Preserve new output separately from historical reports and record the source
revision, runtime, command, input hashes and date. Verify hashes again after
execution. If these files move, update the committed locators and reverify them.
