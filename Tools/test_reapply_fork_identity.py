"""The fork sync may keep only the NOOP IT name and com.noop.whoop.ita id.

Run from Tools/: python3 -m unittest test_reapply_fork_identity -v
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import i18n_audit as ia
import reapply_fork_identity as fork


GRADLE = """
android {
    defaultConfig {
        applicationId = "com.noop.whoop"
        minSdk = 26
        versionCode = 554
        versionName = "12.0.0"
    }
    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
        }
        release {
            if (isStagingRelease) {
                applicationIdSuffix = ".staging"
            }
        }
    }
    productFlavors {
        create("demo") {
            applicationIdSuffix = ".demo"
        }
    }
}
"""


class ConflictPolicy(unittest.TestCase):
    def test_values_it_is_upstream(self):
        self.assertEqual(fork.conflict_action("android/app/src/main/res/values-it/strings.xml"), "theirs")
        self.assertEqual(fork.conflict_action("android/app/src/main/res/values-it/steps_view.xml"), "theirs")

    def test_gradle_and_echo_baseline_are_upstream_then_reapplied(self):
        self.assertEqual(fork.conflict_action("android/app/build.gradle.kts"), "theirs")
        self.assertEqual(fork.conflict_action("Tools/i18n_echo_baseline.txt"), "theirs")

    def test_launcher_strings_are_upstream_then_reapplied(self):
        self.assertEqual(fork.conflict_action("android/app/src/main/res/values/strings.xml"), "theirs")
        self.assertEqual(fork.conflict_action("android/app/src/main/res/values-de/strings.xml"), "theirs")
        self.assertEqual(fork.conflict_action("android/app/src/debug/res/values/strings.xml"), "theirs")
        self.assertEqual(fork.conflict_action("README.md"), "theirs")

    def test_fork_tooling_stays(self):
        self.assertEqual(fork.conflict_action(".github/workflows/sync-upstream.yml"), "ours")
        self.assertEqual(fork.conflict_action(".github/workflows/android-apk.yml"), "ours")
        self.assertEqual(fork.conflict_action("Tools/reapply_fork_identity.py"), "ours")
        self.assertEqual(fork.conflict_action("docs/FORK-IT.md"), "ours")

    def test_other_paths_fail(self):
        self.assertEqual(fork.conflict_action("android/app/src/main/java/com/noop/ui/TodayScreen.kt"), "fail")
        self.assertEqual(fork.conflict_action("Tools/generate_values_it.py"), "fail")
        self.assertEqual(fork.conflict_action("android/app/src/main/java/com/noop/ingest/HealthConnectImporter.kt"), "fail")


class ApplicationId(unittest.TestCase):
    def test_replaces_only_the_default_id(self):
        text = fork.apply_application_id(GRADLE)
        self.assertIn(f'applicationId = "{fork.APP_ID}"', text)
        self.assertNotIn('applicationId = "com.noop.whoop"\n', text)
        self.assertIn('applicationIdSuffix = ".debug"', text)
        self.assertIn('applicationIdSuffix = ".staging"', text)
        self.assertIn('applicationIdSuffix = ".demo"', text)
        self.assertIn('versionName = "12.0.0"', text)
        self.assertIn(fork.MARKER, text)

    def test_is_idempotent(self):
        once = fork.apply_application_id(GRADLE)
        self.assertEqual(fork.apply_application_id(once), once)

    def test_missing_line_is_an_error(self):
        with self.assertRaises(fork.IdentityError):
            fork.apply_application_id("applicationIdSuffix = \".debug\"\n")


class LauncherName(unittest.TestCase):
    def test_rewrites_app_name_once(self):
        text = '<resources>\n    <string name="app_name">NOOP</string>\n</resources>\n'
        self.assertEqual(
            fork.set_app_name(text, "NOOP IT"),
            '<resources>\n    <string name="app_name">NOOP IT</string>\n</resources>\n',
        )

    def test_leaves_a_matching_name(self):
        text = '<string name="app_name">NOOP IT</string>'
        self.assertIsNone(fork.set_app_name(text, "NOOP IT"))

    def test_banner_is_prefixed_and_stable(self):
        readme = "<p>upstream</p>\n"
        once = fork.ensure_banner(readme)
        self.assertTrue(once.startswith("<!-- FORK-IT-BANNER -->"))
        self.assertIn(fork.APP_ID, once)
        self.assertIn("<p>upstream</p>", once)
        self.assertEqual(fork.ensure_banner(once), once)


class EchoBump(unittest.TestCase):
    def test_noop_is_not_an_echo_and_noop_it_is(self):
        self.assertFalse(ia._has_translatable_words("NOOP"))
        self.assertTrue(ia._has_translatable_words("NOOP IT"))

    def test_one_launcher_echo_is_allowed(self):
        target = "android/app/src/main/res/values-it/strings.xml it"
        updates = fork.reconcile_allowance({target: 27}, {target: 26}, {target})
        self.assertEqual(updates, {target: 27})

    def test_slack_in_the_upstream_allowance_is_left_alone(self):
        target = "android/app/src/main/res/values-it/strings.xml it"
        self.assertEqual(fork.reconcile_allowance({target: 21}, {target: 26}, {target}), {})

    def test_extra_echo_is_a_hard_failure(self):
        target = "android/app/src/main/res/values-it/strings.xml it"
        other = "android/app/src/main/res/values-de/strings.xml de"
        with self.assertRaises(fork.EchoOverflow):
            fork.reconcile_allowance({target: 28}, {target: 26}, {target})
        with self.assertRaises(fork.EchoOverflow):
            fork.reconcile_allowance({other: 18}, {other: 17}, {target})

    def test_baseline_rewrite_keeps_comments(self):
        text = (
            "# header\n"
            "android/app/src/main/res/values-it/strings.xml it 26\n"
            "android/app/src/main/res/values-de/strings.xml de 17\n"
        )
        updated = fork.apply_allowance_updates(
            text,
            {"android/app/src/main/res/values-it/strings.xml it": 27},
        )
        self.assertIn("android/app/src/main/res/values-it/strings.xml it 27\n", updated)
        self.assertIn("android/app/src/main/res/values-de/strings.xml de 17\n", updated)
        self.assertIn(fork.ECHO_NOTE, updated)
        self.assertEqual(fork.apply_allowance_updates(updated, {}), updated)


class ResolveOnAMerge(unittest.TestCase):
    def test_known_conflicts_take_upstream_and_a_stranger_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init", "-b", "fork")
            self._git(root, "config", "user.email", "fork-test@example.com")
            self._git(root, "config", "user.name", "fork-test")
            self._write(root, "android/app/build.gradle.kts", '        applicationId = "com.noop.whoop"\n        versionName = "1.0.0"\n')
            self._write(root, "android/app/src/main/res/values-it/strings.xml", '<string name="app_name">NOOP</string>\n<string name="hello">hello</string>\n')
            self._write(root, "Tools/i18n_echo_baseline.txt", "android/app/src/main/res/values-it/strings.xml it 1\n")
            self._write(root, "docs/FORK-IT.md", "fork docs\n")
            self._write(root, "android/app/src/main/java/com/noop/Foo.kt", "class Foo\n")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-m", "base")
            self._git(root, "branch", "upstream")
            # Fork side: identity edits plus an unrelated Kotlin edit.
            self._write(root, "android/app/build.gradle.kts", '        applicationId = "com.noop.whoop.ita"\n        versionName = "1.0.0"\n')
            self._write(root, "android/app/src/main/res/values-it/strings.xml", '<string name="app_name">NOOP IT</string>\n<string name="hello">fork</string>\n')
            self._write(root, "Tools/i18n_echo_baseline.txt", "android/app/src/main/res/values-it/strings.xml it 9\n")
            self._write(root, "docs/FORK-IT.md", "fork docs kept\n")
            self._write(root, "android/app/src/main/java/com/noop/Foo.kt", "class FooFork\n")
            self._git(root, "commit", "-am", "fork")
            self._git(root, "checkout", "upstream")
            self._write(root, "android/app/build.gradle.kts", '        applicationId = "com.noop.whoop"\n        versionName = "12.0.0"\n')
            self._write(root, "android/app/src/main/res/values-it/strings.xml", '<string name="app_name">NOOP</string>\n<string name="hello">ciao</string>\n')
            self._write(root, "Tools/i18n_echo_baseline.txt", "android/app/src/main/res/values-it/strings.xml it 26\n")
            self._write(root, "docs/FORK-IT.md", "upstream docs\n")
            self._write(root, "android/app/src/main/java/com/noop/Foo.kt", "class FooUpstream\n")
            self._git(root, "commit", "-am", "upstream")
            self._git(root, "checkout", "fork")
            merge = subprocess.run(["git", "merge", "upstream", "--no-edit"], cwd=root, text=True, capture_output=True)
            self.assertNotEqual(merge.returncode, 0, merge.stderr)
            code = fork.resolve_conflicts(root)
            self.assertEqual(code, 1)
            gradle = (root / "android/app/build.gradle.kts").read_text(encoding="utf-8")
            italian = (root / "android/app/src/main/res/values-it/strings.xml").read_text(encoding="utf-8")
            baseline = (root / "Tools/i18n_echo_baseline.txt").read_text(encoding="utf-8")
            self.assertIn('versionName = "12.0.0"', gradle)
            self.assertIn('applicationId = "com.noop.whoop"', gradle)
            self.assertIn(">ciao<", italian)
            self.assertIn(">NOOP<", italian)
            self.assertIn("it 26", baseline)
            self.assertEqual((root / "docs/FORK-IT.md").read_text(encoding="utf-8"), "fork docs kept\n")
            unmerged = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], cwd=root, text=True)
            self.assertEqual(unmerged.strip(), "android/app/src/main/java/com/noop/Foo.kt")

    @staticmethod
    def _git(root: Path, *args: str) -> None:
        subprocess.check_call(["git", *args], cwd=root, stdout=subprocess.DEVNULL)

    @staticmethod
    def _write(root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
