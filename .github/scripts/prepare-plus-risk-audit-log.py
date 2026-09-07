from pathlib import Path

script = Path('.github/scripts/port-plus-risk.sh')
text = script.read_text()
for line in (
    '  backend/internal/server/middleware/audit_log.go\n',
    '  backend/internal/server/middleware/audit_log_test.go\n',
):
    text = text.replace(line, '')
script.write_text(text)

path = Path('backend/internal/server/middleware/audit_log.go')
text = path.read_text()
needle = '\t"GET /api/v1/admin/data-management/s3/config": "admin.data_management.s3_config.read",\n}'
replacement = '\t"GET /api/v1/admin/data-management/s3/config": "admin.data_management.s3_config.read",\n\t"GET /api/v1/admin/prompt-audit/events/:id":   "admin.prompt_audit.event.read",\n}'
if needle not in text:
    raise SystemExit('missing auditSensitiveReads anchor')
path.write_text(text.replace(needle, replacement, 1))
