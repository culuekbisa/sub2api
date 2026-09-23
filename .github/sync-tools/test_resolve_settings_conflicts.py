import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("resolve_settings_conflicts.py")


def _load():
    spec = importlib.util.spec_from_file_location("resolve_settings_conflicts", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ResolveTextTests(unittest.TestCase):
    def setUp(self):
        self.module = _load()

    def test_union_keeps_both_sides(self):
        text = (
            "a\n"
            "<<<<<<< ours\n"
            "ours-line\n"
            "=======\n"
            "theirs-line\n"
            ">>>>>>> theirs\n"
            "b\n"
        )
        resolved, hunks = self.module.resolve_text(text)
        self.assertEqual(hunks, 1)
        self.assertEqual(resolved, "a\nours-line\ntheirs-line\nb\n")

    def test_lines_shared_by_both_sides_are_emitted_once(self):
        # The classic additive-settings hunk: both sides restate the whole
        # field list around their own addition.
        text = (
            "<<<<<<< ours\n"
            "\tKeep  bool `json:\"keep\"`\n"
            "\tOurs  bool `json:\"ours\"`\n"
            "=======\n"
            "\tKeep  bool `json:\"keep\"`\n"
            "\tTheirs bool `json:\"theirs\"`\n"
            ">>>>>>> theirs\n"
        )
        resolved, _ = self.module.resolve_text(text)
        self.assertEqual(
            resolved,
            "\tKeep  bool `json:\"keep\"`\n\tOurs  bool `json:\"ours\"`\n\tTheirs bool `json:\"theirs\"`\n",
        )
        self.assertEqual(resolved.count("Keep"), 1)

    def test_multiple_hunks_and_missing_trailing_newline(self):
        text = (
            "<<<<<<< ours\n1\n=======\n2\n>>>>>>> theirs\n"
            "x\n"
            "<<<<<<< ours\n3\n=======\n4\n>>>>>>> theirs"
        )
        resolved, hunks = self.module.resolve_text(text)
        self.assertEqual(hunks, 2)
        self.assertEqual(resolved, "1\n2\nx\n3\n4")
        self.assertFalse(resolved.endswith("\n"))

    def test_diff3_base_section_is_dropped(self):
        text = (
            "<<<<<<< ours\nours\n"
            "||||||| base\nbase\n"
            "=======\ntheirs\n>>>>>>> theirs\n"
        )
        resolved, _ = self.module.resolve_text(text)
        self.assertEqual(resolved, "ours\ntheirs\n")
        self.assertNotIn("base", resolved)

    def test_missing_separator_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module.resolve_text("<<<<<<< ours\nours\n>>>>>>> theirs\n")

    def test_missing_terminator_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module.resolve_text("<<<<<<< ours\nours\n=======\ntheirs\n")

    def test_text_without_conflicts_is_unchanged(self):
        resolved, hunks = self.module.resolve_text("plain\n")
        self.assertEqual(hunks, 0)
        self.assertEqual(resolved, "plain\n")


class ClassifyTests(unittest.TestCase):
    def test_duplicate_config_key_is_rejected(self):
        # A same-line compose conflict unions into a duplicate key that docker
        # compose resolves silently as last-wins, so it must be refused.
        with self.assertRaises(ValueError):
            self.module.assert_no_duplicate_keys("env:\n  - MODE=fork\n  - MODE=upstream\n")

    def test_distinct_config_keys_pass(self):
        self.module.assert_no_duplicate_keys(
            "env:\n  - MODE=fork\n  - OTHER=upstream\n")

    def test_env_style_duplicate_is_rejected(self):
        with self.assertRaises(ValueError):
            self.module.assert_no_duplicate_keys("RUN_MODE=a\nRUN_MODE=b\n")

    def test_config_like_detection(self):
        for path in ("deploy/docker-compose.dev.yml", "deploy/.env.example", "deploy/config.example.yaml"):
            with self.subTest(path=path):
                self.assertTrue(self.module.is_config_like(path))
        self.assertFalse(self.module.is_config_like("frontend/src/types/index.ts"))



    def setUp(self):
        self.module = _load()

    def test_verified_settings_files_are_auto(self):
        # Only files whose union was checked against the real 0.2.8 hand merge.
        for path in (
            "backend/internal/handler/admin/setting_handler.go",
            "backend/internal/service/setting_update.go",
            "backend/internal/service/settings_view.go",
            "backend/internal/service/domain_constants.go",
            "frontend/src/api/admin/settings.ts",
            "frontend/src/types/index.ts",
            "frontend/src/views/admin/SettingsView.vue",
            "deploy/docker-compose.dev.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "auto")

    def test_risk_control_files_stay_manual(self):
        for path in (
            "backend/internal/service/content_moderation_input.go",
            "backend/internal/service/content_moderation.go",
            "backend/internal/auditcontent/extract.go",
            "backend/internal/securityaudit/prompt_snapshot.go",
            "backend/internal/repository/account_repo.go",
            "backend/internal/service/openai_codex_ticket.go",
            "frontend/src/views/admin/RiskControlView.vue",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "manual")

    def test_infrastructure_stays_manual(self):
        for path in (
            ".github/workflows/upstream-sync.yml",
            ".github/workflows/release.yml",
            "backend/migrations/250_content_moderation_input_content.sql",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "manual")

    def test_unverified_settings_files_stay_manual(self):
        # These conflict on nearly every release, but a textual union of the two
        # sides does not compile (gofmt re-alignment / shared signatures), so
        # they stay manual until the resolver proves it matches a hand merge.
        for path in (
            "backend/cmd/server/wire_gen.go",
            "backend/internal/handler/wire.go",
            "backend/internal/handler/dto/settings.go",
            "backend/internal/handler/dto/types.go",
            "backend/internal/service/setting_parse.go",
            "backend/internal/service/setting_service.go",
            "backend/internal/handler/dto/mappers.go",
            "backend/internal/handler/admin/setting_handler_update.go",
            "backend/internal/handler/admin/account_handler.go",
            "backend/internal/repository/account_repo.go",
            "backend/internal/service/content_moderation_input.go",
            ".github/workflows/release.yml",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "manual")

    def test_unknown_path_stays_manual(self):
        self.assertEqual(self.module.classify("backend/internal/service/brand_new.go"), "manual")

    def test_rewrite_files_stay_manual(self):
        # Both sides rewrite the same region in these files, so a union does
        # not compile. They must never be auto-resolved.
        for path in (
            "backend/internal/handler/dto/mappers.go",
            "backend/internal/handler/admin/setting_handler_update.go",
            "backend/internal/handler/admin/account_handler.go",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "manual")

    def test_deny_wins_over_allow(self):
        # A path matching both lists must never be auto-resolved.
        for path in ("backend/internal/service/risk_settings.go",):
            with self.subTest(path=path):
                self.assertEqual(self.module.classify(path), "manual")

    def test_path_normalization_keeps_dot_directories(self):
        # '.github/...' must match the deny rule, not the unlisted fallback.
        self.assertEqual(self.module.classify("./.github/workflows/release.yml"), "manual")
        self.assertEqual(self.module.classify(".github\\workflows\\release.yml"), "manual")
        self.assertEqual(self.module.classify("./frontend/src/types/index.ts"), "auto")


if __name__ == "__main__":
    unittest.main()


class WorkflowContractTests(unittest.TestCase):
    """Guards for the parts of upstream-sync.yml that decide auto vs manual."""

    @classmethod
    def setUpClass(cls):
        cls.text = (Path(__file__).resolve().parents[1] / "workflows" / "upstream-sync.yml").read_text(encoding="utf-8")

    def test_conflict_branch_runs_the_resolver(self):
        self.assertIn("resolve_settings_conflicts.py", self.text)

    def test_toolchain_gates_are_scoped_to_touched_trees(self):
        # A gate must only run for trees the merge touched, otherwise an
        # unrelated toolchain failure rejects an otherwise good merge.
        self.assertIn("merged_paths=", self.text)
        self.assertIn("grep -q '^backend/'", self.text)
        self.assertIn("grep -q '^frontend/'", self.text)

    def test_rejection_aborts_before_committing(self):
        conflict_path = self.text.split("git merge --no-commit --no-ff upstream/main", 1)[1]
        conflict_path = conflict_path.split("git commit -m", 1)[0]
        self.assertIn("merge_state=conflict", conflict_path)
        self.assertGreaterEqual(conflict_path.count("git merge --abort"), 2)

    def test_reporting_step_can_open_issues(self):
        self.assertIn("issues: write", self.text)
        self.assertIn("gh issue", self.text)

    def test_resolver_runs_from_the_checkout(self):
        # The workflow must call the in-repo script, not a global tool.
        self.assertIn("python .github/sync-tools/resolve_settings_conflicts.py", self.text)
