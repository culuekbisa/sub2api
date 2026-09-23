#!/usr/bin/env python3
"""Union-resolve additive merge conflicts on the fork's settings surface.

The upstream sync workflow merges Wei-Shaw/sub2api into this fork. Both sides
regularly add independent entries to the same settings structs, DTOs and i18n
catalogues, so those files conflict on nearly every upstream release even
though both changes can simply coexist.

Only files whose conflicts are known to be additive are unioned here. Every
other path - most importantly the fork's risk-control files, the account
repository probe merge, migrations and workflows - must be resolved by a
human, because silently preferring either side can drop an upstream security
fix or the fork's own policy.

Union is a textual operation, not a proof of correctness. Callers must compile
and type-check the result before pushing; if that fails they must fall back to
human resolution.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MARKER_START = "<<<<<<<"
MARKER_BASE = "|||||||"
MARKER_MID = "======="
MARKER_END = ">>>>>>>"

# Never auto-resolve these. Order matters: deny wins over allow, so a rule can
# be added here without touching the allow list.
DENY_PATTERNS = (
    re.compile(r"^\.github/"),
    re.compile(r"^backend/migrations/"),
    re.compile(r"^backend/internal/auditcontent/"),
    re.compile(r"^backend/internal/securityaudit/"),
    re.compile(r"^backend/internal/service/content_moderation"),
    re.compile(r"^backend/internal/service/openai_codex_ticket"),
    re.compile(r"^backend/internal/repository/account_repo"),
    re.compile(r"^frontend/src/views/admin/RiskControlView\.vue$"),
    re.compile(r"^frontend/src/api/admin/riskControl\.ts$"),
    re.compile(r"^backend/internal/service/risk"),
)

# Additive-only files. This list is empirical, not aspirational: each entry was
# checked against the real 0.2.8 conflict set by resolving it here and diffing
# the result against the hand merge (gofmt-normalised). Files whose two sides
# rewrite the same region - wire.go / wire_gen.go (shared ") *AdminHandlers {"
# with differing signatures), dto/settings.go and dto/types.go (each side
# restates the whole field list, and gofmt re-alignment defeats line matching),
# setting_parse.go, setting_service.go, setting_handler_update.go and
# dto/mappers.go - do not survive a union and stay manual.
ALLOW_PATTERNS = (
    re.compile(r"^backend/internal/handler/admin/setting_handler\.go$"),
    re.compile(r"^backend/internal/service/setting_update\.go$"),
    re.compile(r"^backend/internal/service/settings_view\.go$"),
    re.compile(r"^backend/internal/service/domain_constants\.go$"),
    re.compile(r"^frontend/src/api/admin/settings\.ts$"),
    re.compile(r"^frontend/src/types/index\.ts$"),
    re.compile(r"^frontend/src/views/admin/SettingsView\.vue$"),
    re.compile(r"^deploy/(docker-compose\.dev\.yml|\.env\.example|config\.example\.yaml)$"),
)


def classify(path: str) -> str:
    """Return 'auto' or 'manual' for a repository-relative path."""
    normalized = path.replace("\\", "/")
    # Strip only a leading './'; lstrip("./") would also eat the dot in
    # dot-directories such as '.github/' and silently disable the deny rules.
    while normalized.startswith("./"):
        normalized = normalized[2:]
    for pattern in DENY_PATTERNS:
        if pattern.search(normalized):
            return "manual"
    for pattern in ALLOW_PATTERNS:
        if pattern.search(normalized):
            return "auto"
    return "manual"


def resolve_text(text: str) -> tuple[str, int]:
    """Union every conflict hunk, returning the text and the hunk count.

    Both sides are kept, ours first, with lines shared by both sides emitted
    once. The result is still a guess: hunks where the two sides only overlap
    partially (a shared closing brace, a switch that each side rewrote) come
    out broken, which is why callers must build and type-check the result
    before pushing. Raises ValueError on malformed markers so the caller can
    fall back to human resolution instead of writing a broken file.
    """
    has_trailing_newline = text.endswith("\n")
    lines = text.split("\n")
    if has_trailing_newline:
        lines.pop()

    out: list[str] = []
    hunks = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith(MARKER_START):
            out.append(line)
            index += 1
            continue

        hunks += 1
        ours: list[str] = []
        theirs: list[str] = []
        index += 1

        # ours, optionally followed by a diff3-style base section
        while index < len(lines) and not lines[index].startswith((MARKER_BASE, MARKER_MID)):
            ours.append(lines[index])
            index += 1
        if index < len(lines) and lines[index].startswith(MARKER_BASE):
            while index < len(lines) and not lines[index].startswith(MARKER_MID):
                index += 1
        if index >= len(lines):
            raise ValueError("conflict hunk is missing its '=======' separator")
        index += 1

        while index < len(lines) and not lines[index].startswith(MARKER_END):
            theirs.append(lines[index])
            index += 1
        if index >= len(lines):
            raise ValueError("conflict hunk is missing its '>>>>>>>' terminator")
        index += 1

        # Both sides usually quote the unchanged neighbours that frame their
        # addition. Keeping every line twice would redeclare struct fields and
        # return types, so a line present on both sides is emitted once.
        out.extend(ours)
        for line in theirs:
            if line not in ours:
                out.extend([line])

    resolved = "\n".join(out)
    if has_trailing_newline:
        resolved += "\n"
    return resolved, hunks


def conflicted_paths(root: Path) -> list[str]:
    """Paths git currently reports as unmerged, in stable order."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=U"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(line for line in result.stdout.splitlines() if line.strip())


CONFIG_SUFFIXES = (".yml", ".yaml", ".env", ".example")


def is_config_like(path: str) -> bool:
    """Config files where a unioned duplicate key fails silently at runtime.

    Composing two `- KEY=value` lines is valid Go-adjacent text but yields a
    last-wins duplicate in docker compose and .env, so these files get an extra
    duplicate-key guard. Go and TypeScript are protected by their compilers.
    """
    lowered = path.replace("\\", "/").lower()
    return lowered.endswith(CONFIG_SUFFIXES) or "/." in lowered and lowered.endswith(".example")


def assert_no_duplicate_keys(text: str) -> None:
    """Raise ValueError when a config-ish text carries a duplicated key.

    Only the two shapes this repository actually uses are compared: a leading
    `KEY=` for .env files and a `- KEY=` list entry for compose files. A hunk
    that restates the same key therefore falls back to human resolution.
    """
    seen: set[str] = set()
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if not key or " " in key or ":" in key:
            continue
        if key in seen:
            raise ValueError(f"duplicate config key {key!r} after union")
        seen.add(key)


def resolve_file(root: Path, path: str) -> int:
    target = root / path
    text = target.read_text(encoding="utf-8")
    resolved, hunks = resolve_text(text)
    if is_config_like(path):
        assert_no_duplicate_keys(resolved)
    target.write_text(resolved, encoding="utf-8")
    # The file stays unmerged in the index until it is staged, and the caller
    # decides whether the whole merge is committable by looking at
    # 'git diff --diff-filter=U'. Stage here so a fully auto-resolved merge
    # reports zero unmerged paths.
    subprocess.run(
        ["git", "-C", str(root), "add", "--", path],
        check=True,
        capture_output=True,
    )
    return hunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    resolved: list[dict[str, object]] = []
    manual: list[str] = []
    failed: list[str] = []

    for path in conflicted_paths(root):
        if classify(path) != "auto":
            manual.append(path)
            continue
        try:
            hunks = resolve_file(root, path)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            print(f"manual:{path}: {error}", file=sys.stderr)
            failed.append(path)
            continue
        resolved.append({"path": path, "hunks": hunks})

    if args.json:
        print(json.dumps({"resolved": resolved, "manual": manual + failed}))
        return 0

    for entry in resolved:
        print(f"resolved {entry['path']} ({entry['hunks']} hunks)")
    for path in manual:
        print(f"manual   {path}")
    for path in failed:
        print(f"manual   {path} (auto-resolve rejected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
