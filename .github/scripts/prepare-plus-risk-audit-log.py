from pathlib import Path

script = Path('.github/scripts/port-plus-risk.sh')
text = script.read_text()
for line in (
    '  backend/internal/server/middleware/audit_log.go\n',
    '  backend/internal/server/middleware/audit_log_test.go\n',
):
    text = text.replace(line, '')

# auditcontent's final Plus contract normalizes Codex delegation/automation
# bootstrap payloads before extraction. That helper is self-contained (stdlib
# only), so include the small openaiwire package as a required risk dependency.
owned_anchor = 'OWNED_PATHS=(\n  backend/internal/auditcontent\n'
owned_replacement = 'OWNED_PATHS=(\n  backend/internal/auditcontent\n  backend/internal/openaiwire\n'
if owned_anchor not in text:
    raise SystemExit('missing owned paths anchor')
text = text.replace(owned_anchor, owned_replacement, 1)

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

# Normalize the final v0.2.2 Live handler imports after every selected patch has
# landed. The merged handler needs context/errors for the audit hook, while the
# old encoding/json dependency may disappear in the final implementation.
import_anchor = "printf '0.2.2\\n' > backend/cmd/server/VERSION\n\n"
import_fix = r'''python3 - <<'PY_LIVE_IMPORTS'
from pathlib import Path

path = Path('backend/internal/handler/openai_live.go')
source = path.read_text()
start = source.index('import (\n')
end = source.index(')\n\n', start)
imports = source[start:end]
body = source[end + 3:]
for package in ('context', 'errors'):
    if f'{package}.' in body and f'\t"{package}"\n' not in imports:
        imports += f'\t"{package}"\n'
if 'json.' not in body:
    imports = imports.replace('\t"encoding/json"\n', '')
path.write_text(source[:start] + imports + source[end:])
PY_LIVE_IMPORTS
printf '0.2.2\n' > backend/cmd/server/VERSION

'''
if import_anchor not in text:
    raise SystemExit('missing final import normalization anchor')
text = text.replace(import_anchor, import_fix, 1)

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
