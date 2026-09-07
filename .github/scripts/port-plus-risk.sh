#!/usr/bin/env bash
set -Eeuo pipefail

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git remote remove lucky >/dev/null 2>&1 || true
git remote add lucky https://github.com/LuckyKuang/sub2api-plus.git
git fetch --no-tags lucky main

test "$(tr -d '\r\n' < backend/cmd/server/VERSION)" = '0.2.2'
SHARED_BASE="$(git merge-base HEAD lucky/main)"
echo "shared base: $SHARED_BASE"

OWNED_PATHS=(
  backend/internal/auditcontent
  backend/internal/securityaudit
  backend/internal/service/content_moderation.go
  backend/internal/service/content_moderation_input.go
  backend/internal/service/content_moderation_input_test.go
  backend/internal/service/content_moderation_proxy_test.go
  backend/internal/service/content_moderation_runtime_cache_test.go
  backend/internal/service/content_moderation_session_block.go
  backend/internal/service/content_moderation_session_block_test.go
  backend/internal/service/content_moderation_test.go
  backend/internal/service/content_moderation_cyber_test.go
  backend/internal/repository/content_moderation_hash_cache.go
  backend/internal/repository/content_moderation_hash_cache_test.go
  backend/internal/repository/content_moderation_repo.go
  backend/internal/repository/content_moderation_repo_test.go
  backend/internal/repository/content_moderation_session_block_repo.go
  backend/internal/handler/admin/content_moderation_handler.go
  backend/internal/handler/content_moderation_helper.go
  backend/internal/handler/security_audit_content_contract_test.go
  backend/internal/handler/security_audit_errors.go
  backend/internal/handler/security_audit_errors_test.go
  backend/internal/handler/security_audit_helper.go
  backend/internal/handler/security_audit_helper_test.go
  backend/internal/handler/security_audit_media_submit_test.go
  backend/internal/handler/security_audit_order_test.go
  backend/internal/server/routes/prompt_audit_route_coverage_test.go
  backend/migrations/content_moderation_input_content_migration_test.go
  backend/migrations/content_moderation_session_blocks_migration_test.go
  backend/migrations/content_moderation_session_blocks_unique_migration_test.go
  docs/SECURITY_AUDIT_CONTENT_COVERAGE.md
  frontend/src/api/admin/riskControl.ts
  frontend/src/features/prompt-audit
  frontend/src/i18n/locales/en/admin/promptAudit.ts
  frontend/src/i18n/locales/zh/admin/promptAudit.ts
  frontend/src/views/admin/RiskControlView.vue
  frontend/src/views/admin/__tests__/RiskControlView.spec.ts
)

: > /tmp/owned-files.txt
for path in "${OWNED_PATHS[@]}"; do
  git diff --name-only "$SHARED_BASE" lucky/main -- "$path" >> /tmp/owned-files.txt
done
sort -u -o /tmp/owned-files.txt /tmp/owned-files.txt

while IFS= read -r file; do
  [ -n "$file" ] || continue
  case "$file" in
    frontend/src/features/prompt-audit/viewModel.ts|frontend/src/i18n/locales/en/admin/promptAudit.ts|frontend/src/i18n/locales/zh/admin/promptAudit.ts)
      continue
      ;;
  esac

  if git diff --quiet "$SHARED_BASE" HEAD -- "$file"; then
    if git cat-file -e "lucky/main:$file" 2>/dev/null; then
      echo "final-copy owned: $file"
      git checkout lucky/main -- "$file"
    elif [ -e "$file" ]; then
      echo "remove owned file deleted by Plus: $file"
      git rm -- "$file"
    fi
    continue
  fi

  patch="/tmp/owned-$(echo "$file" | tr '/ ' '__').patch"
  git diff --binary "$SHARED_BASE" lucky/main -- "$file" > "$patch"
  [ -s "$patch" ] || continue
  echo "three-way owned: $file"
  if ! git apply --3way --index "$patch"; then
    echo "::error title=Owned v0.2.2 adaptation conflict::$file"
    git status --short
    git diff --name-only --diff-filter=U || true
    exit 1
  fi
done < /tmp/owned-files.txt

cat > frontend/src/features/prompt-audit/viewModel.ts <<'EOF_VIEWMODEL'
import type {
  PromptAuditConfig,
  PromptAuditDraft,
  PromptAuditEndpointDraft,
  PromptAuditUpdateRequest,
  PromptEventFilters,
} from './types'

export const DEFAULT_GUARD_MODEL = 'sileader/qwen3guard:0.6b'
export const MIN_GUARD_TIMEOUT_MS = 100
export const MAX_GUARD_TIMEOUT_MS = 30000
export const MIN_GUARD_INPUT_LIMIT = 128
export const MAX_GUARD_INPUT_LIMIT = 100000
export const CUSTOM_POLICY_CATEGORY = 'custom_policy'

export const SCANNER_CATALOG = [
  { id: 'violent', label: 'Violent' },
  { id: 'non_violent_illegal_acts', label: 'Non-violent Illegal Acts' },
  { id: 'sexual_content_or_sexual_acts', label: 'Sexual Content or Sexual Acts' },
  { id: 'pii', label: 'PII' },
  { id: 'suicide_and_self_harm', label: 'Suicide & Self-Harm' },
  { id: 'unethical_acts', label: 'Unethical Acts' },
  { id: 'politically_sensitive_topics', label: 'Politically Sensitive Topics' },
  { id: 'copyright_violation', label: 'Copyright Violation' },
  { id: 'jailbreak', label: 'Jailbreak' },
] as const

export function cloneData<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function configToDraft(config: PromptAuditConfig): PromptAuditDraft {
  return {
    ...cloneData(config),
    engine_mode: config.engine_mode || 'qwen3guard',
    system_prompt: config.system_prompt || '',
    group_ids: [...(config.group_ids ?? [])],
    scanners: [...(config.scanners ?? [])],
    endpoints: (config.endpoints ?? []).map((endpoint) => ({
      ...endpoint,
      token: '',
      clear_token: false,
    })),
  }
}

export function createDefaultEndpoint(index = 1): PromptAuditEndpointDraft {
  return {
    id: `guard-${Date.now()}-${index}`,
    name: `Guard ${index}`,
    protocol: 'openai_compatible',
    base_url: 'http://127.0.0.1:8000',
    model: DEFAULT_GUARD_MODEL,
    timeout_ms: 3000,
    input_limit: 4000,
    enabled: true,
    has_token: false,
    token_status: 'missing',
    token: '',
    clear_token: false,
  }
}

export function buildUpdateRequest(draft: PromptAuditDraft): PromptAuditUpdateRequest {
  return {
    expected_config_version: draft.config_version,
    enabled: draft.enabled,
    blocking_enabled: draft.enabled && draft.blocking_enabled,
    blocking_latest_turn_only: draft.blocking_latest_turn_only,
    store_pass_events: draft.store_pass_events,
    engine_mode: draft.engine_mode,
    system_prompt: draft.system_prompt,
    strategy: 'priority',
    worker_count: Number(draft.worker_count),
    queue_capacity: Number(draft.queue_capacity),
    scanners: [...draft.scanners],
    all_groups: draft.all_groups,
    group_ids: draft.all_groups ? [] : [...draft.group_ids].sort((a, b) => a - b),
    endpoints: draft.endpoints.map((endpoint) => ({
      id: endpoint.id.trim(),
      name: endpoint.name.trim(),
      protocol: 'openai_compatible',
      base_url: endpoint.base_url.trim(),
      model: endpoint.model.trim() || DEFAULT_GUARD_MODEL,
      token: endpoint.token.trim() || undefined,
      clear_token: endpoint.clear_token,
      timeout_ms: Number(endpoint.timeout_ms),
      input_limit: Number(endpoint.input_limit),
      enabled: endpoint.enabled,
    })),
  }
}

export function draftFingerprint(draft: PromptAuditDraft | null): string {
  if (!draft) return ''
  return JSON.stringify(buildUpdateRequest(draft))
}

export function emptyEventFilters(): PromptEventFilters {
  return {
    decision: '', risk_level: '', endpoint: '', group_id: '', user_id: '', api_key_id: '',
    request_id: '', client_ip: '', prompt_hash: '', keyword: '', start_at: '', end_at: '',
  }
}

function toISO(value: string): string | undefined {
  if (!value.trim()) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString()
}

export function eventQueryParams(filters: PromptEventFilters): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const key of ['decision', 'risk_level', 'endpoint', 'request_id', 'client_ip', 'prompt_hash', 'keyword'] as const) {
    const value = filters[key].trim()
    if (value) result[key] = value
  }
  for (const key of ['group_id', 'user_id', 'api_key_id'] as const) {
    const value = Number(filters[key])
    if (Number.isInteger(value) && value > 0) result[key] = value
  }
  const start = toISO(filters.start_at)
  const end = toISO(filters.end_at)
  if (start) result.start_at = start
  if (end) result.end_at = end
  return result
}

export function eventFilterPayload(filters: PromptEventFilters): Record<string, unknown> {
  return eventQueryParams(filters)
}

export function hasExplicitDeleteRange(filters: PromptEventFilters): boolean {
  const start = toISO(filters.start_at)
  const end = toISO(filters.end_at)
  return Boolean(start && end && new Date(start).getTime() < new Date(end).getTime())
}

export type DeleteRangePreset = '1d' | '7d' | '30d' | '90d' | 'all' | 'custom'
export const DELETE_RANGE_PRESETS: ReadonlyArray<{ id: DeleteRangePreset; days: number | null }> = [
  { id: '1d', days: 1 }, { id: '7d', days: 7 }, { id: '30d', days: 30 },
  { id: '90d', days: 90 }, { id: 'all', days: null }, { id: 'custom', days: null },
]
const DAY_MS = 24 * 60 * 60 * 1000

export function resolveDeleteRangeFilters(
  filters: PromptEventFilters,
  preset: DeleteRangePreset,
  now: number = Date.now(),
): PromptEventFilters {
  const resolved = cloneData(filters)
  if (preset === 'custom') return resolved
  const days = DELETE_RANGE_PRESETS.find((item) => item.id === preset)?.days ?? null
  resolved.start_at = new Date(0).toISOString()
  resolved.end_at = new Date(days === null ? now : now - days * DAY_MS).toISOString()
  return resolved
}
EOF_VIEWMODEL
git add frontend/src/features/prompt-audit/viewModel.ts

# Locale merge: use Plus' final observability/IP/retention wording, then layer
# v0.2.2's custom JSON engine and custom-policy category back on top.
git checkout lucky/main -- \
  frontend/src/i18n/locales/en/admin/promptAudit.ts \
  frontend/src/i18n/locales/zh/admin/promptAudit.ts
python3 - <<'PY'
from pathlib import Path

def replace(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'missing locale anchor in {path}: {old[:80]!r}')
    p.write_text(text.replace(old, new, 1))

en = 'frontend/src/i18n/locales/en/admin/promptAudit.ts'
replace(en,
"    description: 'Review user input asynchronously or block it synchronously through OpenAI-compatible Qwen3Guard nodes. Bounded retained content is available for admin review.',",
"    description: 'Review user input asynchronously or block it synchronously through OpenAI-compatible audit nodes. Supports Qwen3Guard and custom JSON policies; bounded retained content is available for admin review.',")
replace(en, "      jailbreak: 'Jailbreak',\n    },", "      jailbreak: 'Jailbreak',\n      custom_policy: 'Custom Policy Violation',\n    },")
replace(en, "      jailbreak: 'Prompt injection or jailbreak attempt',\n    },", "      jailbreak: 'Prompt injection or jailbreak attempt',\n      custom_policy: 'The custom audit policy marked the input as violating',\n    },")
replace(en,
"      title: 'Audit policy', description: 'Configure group scope, nine input-risk categories, workers, and queue bounds.', scope: 'Scope', allGroups: 'All groups', selectedGroups: 'Selected groups',",
"      title: 'Audit policy', description: 'Configure the audit engine, system prompt, group scope, input risks, workers, and queue bounds.', scope: 'Scope', allGroups: 'All groups', selectedGroups: 'Selected groups',")
replace(en,
"      searchGroups: 'Search groups', noGroups: 'No matching groups', missingGroups: 'Configured IDs for groups that no longer exist', selectedCount: '{count} groups selected',\n      scanners:",
"      searchGroups: 'Search groups', noGroups: 'No matching groups', missingGroups: 'Configured IDs for groups that no longer exist', selectedCount: '{count} groups selected',\n      engineMode: 'Audit engine mode', engineQwen3Guard: 'Qwen3Guard-compatible mode', engineCustomJSON: 'Custom JSON mode', systemPrompt: 'System prompt', systemPromptHint: 'Custom JSON mode sends this value as the system message; changes apply to new audit requests after saving.',\n      scanners:")
replace(en, "blockingLatestTurnOnly: 'Synchronous blocking scans only the latest user input'", "blockingLatestTurnOnly: 'Only latest input and prior output'")
replace(en,
"prompt_audit_groups_required: 'Select at least one group in selected-group mode.', prompt_audit_scanners_required: 'Enable at least one risk category.',\n      prompt_audit_invalid_client_ip:",
"prompt_audit_groups_required: 'Select at least one group in selected-group mode.', prompt_audit_scanners_required: 'Enable at least one risk category.', prompt_audit_invalid_engine_mode: 'The audit engine mode is invalid.', prompt_audit_invalid_system_prompt: 'The system prompt exceeds the allowed length.',\n      prompt_audit_invalid_client_ip:")

zh = 'frontend/src/i18n/locales/zh/admin/promptAudit.ts'
replace(zh,
"    description: '通过 OpenAI 兼容 Qwen3Guard 节点异步复核或同步阻止用户输入；事件会按上限留存审计内容，供管理员复核。',",
"    description: '通过 OpenAI 兼容审计节点异步复核或同步阻止用户输入；支持 Qwen3Guard 和自定义 JSON 审计策略，事件会按上限留存审计内容，供管理员复核。',")
replace(zh, "      jailbreak: '越狱',\n    },", "      jailbreak: '越狱',\n      custom_policy: '自定义策略违规',\n    },")
replace(zh, "      jailbreak: '提示注入或越狱尝试',\n    },", "      jailbreak: '提示注入或越狱尝试',\n      custom_policy: '自定义审计策略判定为违规',\n    },")
replace(zh,
"      title: '审计策略', description: '配置适用分组、九类输入风险、Worker 与队列边界。', scope: '适用范围', allGroups: '全部分组', selectedGroups: '指定分组',",
"      title: '审计策略', description: '配置审计引擎、系统提示词、适用分组、输入风险、Worker 与队列边界。', scope: '适用范围', allGroups: '全部分组', selectedGroups: '指定分组',")
replace(zh,
"      searchGroups: '搜索分组', noGroups: '没有匹配分组', missingGroups: '配置中包含已删除的分组 ID', selectedCount: '已选择 {count} 个分组',\n      scanners:",
"      searchGroups: '搜索分组', noGroups: '没有匹配分组', missingGroups: '配置中包含已删除的分组 ID', selectedCount: '已选择 {count} 个分组',\n      engineMode: '审计引擎模式', engineQwen3Guard: 'Qwen3Guard 兼容模式', engineCustomJSON: '自定义 JSON 模式', systemPrompt: '系统提示词', systemPromptHint: '自定义 JSON 模式会将此内容作为 system message 发送；保存后对新的审计请求生效。',\n      scanners:")
replace(zh, "blockingLatestTurnOnly: '同步阻止仅审最新用户输入'", "blockingLatestTurnOnly: '仅审最新输入和上一轮输出'")
replace(zh,
"prompt_audit_groups_required: '指定分组模式至少需要选择一个分组。', prompt_audit_scanners_required: '至少需要启用一个风险分类。',\n      prompt_audit_invalid_client_ip:",
"prompt_audit_groups_required: '指定分组模式至少需要选择一个分组。', prompt_audit_scanners_required: '至少需要启用一个风险分类。', prompt_audit_invalid_engine_mode: '审计引擎模式无效。', prompt_audit_invalid_system_prompt: '系统提示词超过允许长度。',\n      prompt_audit_invalid_client_ip:")
PY
git add frontend/src/i18n/locales/en/admin/promptAudit.ts frontend/src/i18n/locales/zh/admin/promptAudit.ts

SHARED_PATHS=(
  backend/cmd/server/wire.go
  backend/internal/handler/admin/setting_handler.go
  backend/internal/handler/admin/setting_handler_audit.go
  backend/internal/handler/admin/setting_handler_update.go
  backend/internal/handler/dto/settings.go
  backend/internal/handler/gateway_handler.go
  backend/internal/handler/handler.go
  backend/internal/handler/image_task_handler.go
  backend/internal/handler/openai_gateway_handler.go
  backend/internal/handler/openai_gateway_handler_test.go
  backend/internal/handler/openai_live.go
  backend/internal/handler/openai_live_test.go
  backend/internal/handler/wire.go
  backend/internal/repository/gateway_cache.go
  backend/internal/server/api_contract_test.go
  backend/internal/server/middleware/audit_log.go
  backend/internal/server/middleware/audit_log_test.go
  backend/internal/server/routes/admin.go
  backend/internal/service/domain_constants.go
  backend/internal/service/openai_cyber_session_block.go
  backend/internal/service/openai_live_lifecycle_test.go
  backend/internal/service/openai_ws_v2_passthrough_lifecycle_test.go
  backend/internal/service/setting_parse.go
  backend/internal/service/setting_public.go
  backend/internal/service/setting_update.go
  backend/internal/service/settings_view.go
  backend/internal/service/wire.go
  frontend/src/api/admin/index.ts
  frontend/src/api/admin/settings.ts
  frontend/src/components/layout/AppSidebar.vue
  frontend/src/i18n/locales/en/admin/settings.ts
  frontend/src/i18n/locales/zh/admin/settings.ts
  frontend/src/router/__tests__/feature-access.spec.ts
  frontend/src/router/index.ts
  frontend/src/stores/__tests__/app.spec.ts
  frontend/src/stores/app.ts
  frontend/src/types/index.ts
  frontend/src/views/admin/SettingsView.vue
)

apply_shared_risk_commit() {
  local sha="$1"
  local patch="/tmp/shared-${sha}.patch"
  git show --format= --binary "$sha" -- "${SHARED_PATHS[@]}" > "$patch"
  [ -s "$patch" ] || return 0
  if git apply --reverse --check "$patch" >/dev/null 2>&1; then
    echo "shared risk delta already present: $sha"
    return 0
  fi
  echo "apply shared risk delta: $sha"
  if ! git apply --3way --index "$patch"; then
    echo "::error title=Shared v0.2.2 adaptation conflict::$sha"
    git status --short
    git diff --name-only --diff-filter=U || true
    exit 1
  fi
}

for sha in \
  811930b541bde618ced6b6b46da7e517c529d699 \
  1f08a5849ad766f189cdd9a41abd5676fe335b73 \
  9f5907d9c170a61dd253ab6b706e29cd3ac297ac \
  dc8710a2bf5dfe3121de2e0021d85e825d47ea25 \
  95719a71578b28b88ec9b86483310d9b1ac11372 \
  f08cbc49ceac5c3eeb2dbdce9289dceba5127944 \
  9d33034e4e4138ad7755d5dfbc6f56bb56bb39a6 \
  de6c03cc33cb23adeeaf7036dfff3319d407b431 \
  5e3360cceef76005c5f9b8c6607da2e35c2f54cf \
  893e8eb5df44f94a4a12bf4bc26ddf48f167a442 \
  b6777d88837a6f402d8edf98483b1c98e7bd0a34 \
  e5452f34d430cb219bea1f8efbf634b7ccf3ef42 \
  1abcb597b7b3f1f1f114cb14744e0c2ac8b4de0b \
  65fabed9a34ddb924166d1fb85ec38b18a8804b0 \
  189cbcb22fa639af92077c60fed1074c27aad3fb \
  51a3fcbfa574067df531f620dc4285514ee27a58
do
  apply_shared_risk_commit "$sha"
done

current_max=$(find backend/migrations -maxdepth 1 -type f -name '[0-9]*_*.sql' -printf '%f\n' \
  | sed -nE 's/^([0-9]+)_.*/\1/p' | sort -n | tail -1)
current_max=${current_max:-0}
: > /tmp/migration-map.txt
while IFS= read -r file; do
  base="${file##*/}"
  old_num="${base%%_*}"
  suffix="${base#*_}"
  if find backend/migrations -maxdepth 1 -type f -name "[0-9]*_${suffix}" | grep -q .; then
    echo "migration already represented: $suffix"
    continue
  fi
  target="$base"
  if find backend/migrations -maxdepth 1 -type f -name "${old_num}_*.sql" | grep -q .; then
    current_max=$((current_max + 1))
    target="${current_max}_${suffix}"
  fi
  echo "migration: $base -> $target"
  git show "lucky/main:$file" > "backend/migrations/$target"
  printf '%s\t%s\n' "$base" "$target" >> /tmp/migration-map.txt
done < <(git ls-tree -r --name-only lucky/main backend/migrations \
  | grep -E '/[0-9]+_(prompt_audit|content_moderation|moderation_async_image_observability).*\.sql$')

while IFS=$'\t' read -r old new; do
  [ -n "$old" ] || continue
  grep -rlZ --exclude-dir=.git "$old" backend docs frontend 2>/dev/null \
    | xargs -0 -r sed -i "s#${old}#${new}#g"
done < /tmp/migration-map.txt

grep -rlZ --exclude-dir=.git 'github.com/LuckyKuang/sub2api-plus' backend frontend 2>/dev/null \
  | xargs -0 -r sed -i 's#github.com/LuckyKuang/sub2api-plus#github.com/Wei-Shaw/sub2api#g'
printf '0.2.2\n' > backend/cmd/server/VERSION

mapfile -d '' gofiles < <(git diff --name-only -z HEAD -- '*.go')
if [ "${#gofiles[@]}" -gt 0 ]; then
  gofmt -w "${gofiles[@]}"
fi

(cd backend && go run github.com/google/wire/cmd/wire@v0.7.0 ./cmd/server)

test -z "$(git diff --name-only --diff-filter=U)"
! grep -R 'github.com/LuckyKuang/sub2api-plus' backend frontend
test "$(tr -d '\r\n' < backend/cmd/server/VERSION)" = '0.2.2'

duplicates=$(find backend/migrations -maxdepth 1 -type f -name '[0-9]*_*.sql' -printf '%f\n' \
  | sed -nE 's/^([0-9]+)_.*/\1/p' | sort | uniq -d)
if [ -n "$duplicates" ]; then
  echo "::error::Duplicate migration versions: $duplicates"
  exit 1
fi

git diff --check
echo 'Integration diff summary:'
git status --short
git diff --stat HEAD
