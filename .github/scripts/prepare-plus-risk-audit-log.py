from pathlib import Path

script = Path('.github/scripts/port-plus-risk.sh')
text = script.read_text()
for line in (
    '  backend/internal/server/middleware/audit_log.go\n',
    '  backend/internal/server/middleware/audit_log_test.go\n',
):
    text = text.replace(line, '')

# `grep -l` returns 1 when there are no matches. Under `set -e -o pipefail`
# that is not an integration failure, so make the two optional rewrite scans
# explicitly tolerant of the no-match case.
old = '''  grep -rlZ --exclude-dir=.git "$old" backend docs frontend 2>/dev/null \\
    | xargs -0 -r sed -i "s#${old}#${new}#g"\n'''
new = '''  { grep -rlZ --exclude-dir=.git "$old" backend docs frontend 2>/dev/null || true; } \\
    | xargs -0 -r sed -i "s#${old}#${new}#g"\n'''
if old not in text:
    raise SystemExit('missing migration reference rewrite anchor')
text = text.replace(old, new, 1)
old = '''grep -rlZ --exclude-dir=.git 'github.com/LuckyKuang/sub2api-plus' backend frontend 2>/dev/null \\
  | xargs -0 -r sed -i 's#github.com/LuckyKuang/sub2api-plus#github.com/Wei-Shaw/sub2api#g'\n'''
new = '''{ grep -rlZ --exclude-dir=.git 'github.com/LuckyKuang/sub2api-plus' backend frontend 2>/dev/null || true; } \\
  | xargs -0 -r sed -i 's#github.com/LuckyKuang/sub2api-plus#github.com/Wei-Shaw/sub2api#g'\n'''
if old not in text:
    raise SystemExit('missing module rewrite anchor')
text = text.replace(old, new, 1)

# The upstream migration history intentionally contains repeated numeric prefixes,
# so a repository-wide `uniq -d` check is invalid. Validate only the target names
# produced by this port and make sure every mapped migration was materialized.
old = '''duplicates=$(find backend/migrations -maxdepth 1 -type f -name '[0-9]*_*.sql' -printf '%f\\n' \\
  | sed -nE 's/^([0-9]+)_.*/\\1/p' | sort | uniq -d)\nif [ -n "$duplicates" ]; then\n  echo "::error::Duplicate migration versions: $duplicates"\n  exit 1\nfi\n'''
new = '''duplicates=$(cut -f2 /tmp/migration-map.txt | sed '/^$/d' | sort | uniq -d)\nif [ -n "$duplicates" ]; then\n  echo "::error::Duplicate imported migration targets: $duplicates"\n  exit 1\nfi\nwhile IFS=$'\\t' read -r old_migration new_migration; do\n  [ -n "$new_migration" ] || continue\n  test -f "backend/migrations/$new_migration" || {\n    echo "::error::Imported migration missing: $new_migration"\n    exit 1\n  }\ndone < /tmp/migration-map.txt\n'''
if old not in text:
    raise SystemExit('missing duplicate migration validation anchor')
text = text.replace(old, new, 1)
script.write_text(text)

path = Path('backend/internal/server/middleware/audit_log.go')
text = path.read_text()
needle = '\t"GET /api/v1/admin/data-management/s3/config": "admin.data_management.s3_config.read",\n}'
replacement = '\t"GET /api/v1/admin/data-management/s3/config": "admin.data_management.s3_config.read",\n\t"GET /api/v1/admin/prompt-audit/events/:id":   "admin.prompt_audit.event.read",\n}'
if needle not in text:
    raise SystemExit('missing auditSensitiveReads anchor')
path.write_text(text.replace(needle, replacement, 1))
