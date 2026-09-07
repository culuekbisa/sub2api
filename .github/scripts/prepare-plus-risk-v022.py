from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"missing adaptation anchor in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


# The early Plus hardening commits were written on top of Plus-only Live/IP hook
# infrastructure and intermediate WS/image observability assertions that were
# later superseded or belong to non-risk-control subsystems. Keep those shared
# files out of historical patch replay and adapt only the security-audit boundary
# to the current v0.2.2 implementation.
script = Path('.github/scripts/port-plus-risk.sh')
text = script.read_text()
for line in (
    '  backend/internal/handler/image_task_handler.go\n',
    '  backend/internal/handler/openai_gateway_handler.go\n',
    '  backend/internal/handler/openai_live.go\n',
    '  backend/internal/handler/openai_live_test.go\n',
    '  backend/internal/service/openai_live_lifecycle_test.go\n',
    '  backend/internal/service/openai_ws_v2_passthrough_lifecycle_test.go\n',
):
    text = text.replace(line, '')
script.write_text(text)

# Responses: freeze and audit the immutable inbound body before compact
# normalization and before the compact keepalive can commit a 200 response.
responses = 'backend/internal/handler/openai_gateway_handler.go'
raw_gate = '''\tsetOpsRequestContext(c, "", false)\n'''
raw_audit = '''\tsetOpsRequestContext(c, "", false)\n\tsecurityAuditBody := append([]byte(nil), body...)\n\tif !gjson.ValidBytes(securityAuditBody) {\n\t\tlogRequestBodyParseFailure(reqLog, securityAuditBody, nil)\n\t\th.errorResponse(c, http.StatusBadRequest, "invalid_request_error", "Failed to parse request body")\n\t\treturn\n\t}\n\tauditModelResult := gjson.GetBytes(securityAuditBody, "model")\n\tif !auditModelResult.Exists() || auditModelResult.Type != gjson.String || auditModelResult.String() == "" {\n\t\th.errorResponse(c, http.StatusBadRequest, "invalid_request_error", "model is required")\n\t\treturn\n\t}\n\tauditModel := auditModelResult.String()\n\tensureCompositeTargetPlatform(c, apiKey, auditModel)\n\tif !openAICompatibleTextTargetAllowed(c, apiKey, auditModel) {\n\t\th.errorResponse(c, http.StatusBadRequest, "invalid_request_error", "Model is not supported by this OpenAI-compatible endpoint for composite groups")\n\t\treturn\n\t}\n\tauditStream, auditStreamOK := parseOpenAICompatibleStream(securityAuditBody)\n\tif !auditStreamOK {\n\t\th.errorResponse(c, http.StatusBadRequest, "invalid_request_error", invalidStreamFieldTypeMessage)\n\t\treturn\n\t}\n\tif _, err := service.ValidateOpenAIServiceTierField(securityAuditBody); err != nil {\n\t\th.errorResponse(c, http.StatusBadRequest, "invalid_request_error", err.Error())\n\t\treturn\n\t}\n\tsetOpsRequestContext(c, auditModel, auditStream)\n\tsetOpsEndpointContext(c, "", int16(service.RequestTypeFromLegacy(auditStream, false)))\n\tif decision := h.checkSecurityAudit(c, reqLog, apiKey, subject, service.ContentModerationProtocolOpenAIResponses, auditModel, securityAuditBody); decision != nil && !decision.AllowNextStage {\n\t\th.openAISecurityAuditError(c, decision)\n\t\treturn\n\t}\n\n'''
replace_once(responses, raw_gate, raw_audit)
late_audit = '''\tif decision := h.checkSecurityAudit(c, reqLog, apiKey, subject, service.ContentModerationProtocolOpenAIResponses, reqModel, body); decision != nil && !decision.AllowNextStage {\n\t\th.openAISecurityAuditError(c, decision)\n\t\treturn\n\t}\n\n'''
replace_once(responses, late_audit, '')

# Live create requests must use the Live extraction contract rather than the
# Responses contract.
live_handler = 'backend/internal/handler/openai_live.go'
replace_once(live_handler, 'import (\n\t"encoding/json"', 'import (\n\t"context"\n\t"encoding/json"')
replace_once(live_handler, 'service.ContentModerationProtocolOpenAIResponses,', 'service.ContentModerationProtocolOpenAILive,')

# Audit every sideband client frame before it can be written upstream. This is
# intentionally independent of Plus' separate IP-policy hook.
record_anchor = '''\t\th.errorResponse(c, http.StatusNotFound, "not_found_error", "Live call not found")\n\t\treturn\n\t}\n\tdownstream, err := coderws.Accept'''
record_replacement = '''\t\th.errorResponse(c, http.StatusNotFound, "not_found_error", "Live call not found")\n\t\treturn\n\t}\n\treqLog := requestLogger(\n\t\tc,\n\t\t"handler.openai_gateway.live_sideband",\n\t\tzap.Int64("user_id", subject.UserID),\n\t\tzap.Int64("api_key_id", apiKey.ID),\n\t\tzap.Any("group_id", apiKey.GroupID),\n\t\tzap.String("model", record.Model),\n\t)\n\tdownstream, err := coderws.Accept'''
replace_once(live_handler, record_anchor, record_replacement)
old_proxy = '''\tif err := h.gatewayService.ProxyLiveSideband(c.Request.Context(), record, downstream); err != nil {\n\t\t_ = downstream.Close(coderws.StatusInternalError, "live sideband closed")\n\t\treturn\n\t}\n'''
new_proxy = '''\tif err := h.gatewayService.ProxyLiveSidebandWithHooks(c.Request.Context(), record, downstream, &service.LiveSidebandHooks{\n\t\tBeforeClientFrame: func(ctx context.Context, _ coderws.MessageType, payload []byte) error {\n\t\t\tdecision := h.checkSecurityAuditStage(\n\t\t\t\tc, reqLog, apiKey, subject,\n\t\t\t\tservice.ContentModerationProtocolOpenAILive, record.Model, payload, "live_sideband",\n\t\t\t)\n\t\t\tif decision == nil || decision.AllowNextStage {\n\t\t\t\treturn nil\n\t\t\t}\n\t\t\twriteSecurityAuditWSError(ctx, downstream, decision)\n\t\t\treturn errors.New("security audit rejected live sideband frame")\n\t\t},\n\t}); err != nil {\n\t\t_ = downstream.Close(coderws.StatusInternalError, "live sideband closed")\n\t\treturn\n\t}\n'''
replace_once(live_handler, old_proxy, new_proxy)

# Minimal service hook: existing v0.2.2 proxy lifecycle is untouched; the only
# new behavior is a pre-upstream-write callback for every client frame.
live_service = 'backend/internal/service/openai_live.go'
old_signature = '''// ProxyLiveSideband 让认证后的客户端接管控制连接；媒体始终不经过这里。\nfunc (s *OpenAIGatewayService) ProxyLiveSideband(\n\tctx context.Context,\n\trecord *LiveCallRecord,\n\tdownstream *coderws.Conn,\n) error {\n'''
new_signature = '''// LiveSidebandHooks runs policy checks before a client frame reaches upstream.\ntype LiveSidebandHooks struct {\n\tBeforeClientFrame func(context.Context, coderws.MessageType, []byte) error\n}\n\n// ProxyLiveSideband 让认证后的客户端接管控制连接；媒体始终不经过这里。\nfunc (s *OpenAIGatewayService) ProxyLiveSideband(\n\tctx context.Context,\n\trecord *LiveCallRecord,\n\tdownstream *coderws.Conn,\n) error {\n\treturn s.ProxyLiveSidebandWithHooks(ctx, record, downstream, nil)\n}\n\nfunc (s *OpenAIGatewayService) ProxyLiveSidebandWithHooks(\n\tctx context.Context,\n\trecord *LiveCallRecord,\n\tdownstream *coderws.Conn,\n\thooks *LiveSidebandHooks,\n) error {\n'''
replace_once(live_service, old_signature, new_signature)
write_anchor = '''\t\t\tif writeErr := upstream.WriteFrame(proxyCtx, messageType, payload); writeErr != nil {\n'''
write_replacement = '''\t\t\tif hooks != nil && hooks.BeforeClientFrame != nil {\n\t\t\t\tif auditErr := hooks.BeforeClientFrame(proxyCtx, messageType, payload); auditErr != nil {\n\t\t\t\t\terrCh <- auditErr\n\t\t\t\t\treturn\n\t\t\t\t}\n\t\t\t}\n\t\t\tif writeErr := upstream.WriteFrame(proxyCtx, messageType, payload); writeErr != nil {\n'''
replace_once(live_service, write_anchor, write_replacement)
