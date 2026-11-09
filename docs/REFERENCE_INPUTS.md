# Locate and verify the exact reference inputs

The reference protocols require two exact files. `config/reference-inputs.json`
records their expected SHA-256 identities and provenance, without storing either
artifact or inventing a storage location. A null locator means that a durable,
reviewer-accessible location has not been registered. A hash alone is not storage.

The database digest comes from the prior attached-file receipt. The owner reports
169,349,120 bytes in the November 9 plan. The current sandbox has no copy and has
not independently reverified that size or digest. The historical case fixture
can be restored byte for byte from its recorded Git blob using the existing
`scripts/restore_reference_cases.py`; it remains ignored and must not be
reconstructed from descriptions or a different corpus.

Pass operator-managed paths explicitly or set `SUNLIGHT_REFERENCE_DB` and
`SUNLIGHT_REFERENCE_CASES`. No user's home path is hardcoded and no file is
downloaded, modified or created by admission:

```bash
python scripts/verify_reference_inputs.py --db /absolute/operator-storage/sunlight.db --cases /absolute/operator-storage/prosecuted_cases.json
```

An exit code of 0 means the bytes match both expected digests. It does not mean
either validator ran or the floor passed. Exit 2 reports missing, unconfigured
or mismatching inputs, with null measurements for missing files. The helper
never substitutes another database or repeats an earlier measurement as new.

Only after admission, run the recorded protocols with those same paths and
retain the commands, source build, dependency environment and new outputs.
The historically used settings are seed 42, 1,000 bootstrap iterations and 200
presumed-negative comparisons; they belong to the constructed regression
protocol, not a field-accuracy claim. Read the validator's CLI options before
execution and retain its full configuration.

Durability remains an operator decision: preserve the original file, place a
reviewed copy in private storage accessible to the intended reviewer, verify its
hash there, and register only a non-secret locator and custody instructions.
Do not commit the database, credentials or a replacement fixture to Git. This
document and manifest make the missing location explicit; they do not claim that
the database has been backed up or independently reproduced.
