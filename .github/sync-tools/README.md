# Upstream sync tools

`resolve_settings_conflicts.py` is used by the [Sync Upstream workflow](../workflows/upstream-sync.yml)
when merging `Wei-Shaw/sub2api` into this fork.

## Why it exists

Both projects add independent entries to the same settings structs, DTOs and i18n
catalogues, so those files conflict on nearly every upstream release. The union of
the two sides is the intended result, and this script applies it mechanically.

## Guarantees

- Only paths in `ALLOW_PATTERNS` are touched. Anything else - the fork risk-control
  files, `account_repo`, migrations and workflows - stays conflicted for a human.
- `DENY_PATTERNS` always wins over `ALLOW_PATTERNS`.
- The allow list is empirical: every entry was resolved with this script and diffed
  against the hand merge of the 0.2.8 conflict set. Files where a union does not
  compile (shared signatures, rewritten switches, gofmt re-alignment) stay manual.
- Config files get a duplicate-key guard, because a same-line compose conflict
  unions into a last-wins duplicate that the Go compiler cannot catch.
- A union is only accepted when `go build` (and `vue-tsc` for frontend paths) passes
  in the workflow; otherwise the merge is aborted and no commit is made.

## Maintaining it

Run the tests with:

```bash
python -m unittest discover -s .github/sync-tools -p 'test_resolve_settings_conflicts.py'
```

To promote a file from manual to auto, resolve a real upstream conflict with this
script and compare the result against the hand merge (gofmt-normalised for Go),
then add the path and a regression test in the same change.
