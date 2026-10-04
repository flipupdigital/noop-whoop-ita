#!/usr/bin/env python3
"""Restore this fork's sideload identity after an upstream merge.

The product delta versus ryanbr/noop is the launcher name "NOOP IT" and
applicationId com.noop.whoop.ita. Italian strings stay upstream's values-it;
this script only writes the name back into string resources that already
declare app_name.

`resolve-conflicts` is the sync workflow's merge driver. It takes upstream for
values-it, build.gradle.kts, and Tools/i18n_echo_baseline.txt, then `reapply`
puts the name and id back. Any other conflict is a hard failure.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "FORK-IT-IDENTITY"
APP_ID = "com.noop.whoop.ita"
APP_NAME = "NOOP IT"
DEBUG_NAME = "NOOP IT Debug"
DEMO_NAME = "NOOP IT Demo"

# Fork-owned files. A conflict here keeps our copy; upstream does not ship them.
OURS = {
    ".github/workflows/sync-upstream.yml",
    ".github/workflows/android-apk.yml",
    "Tools/reapply_fork_identity.py",
    "Tools/test_reapply_fork_identity.py",
    "docs/FORK-IT.md",
}

# Upstream wins, then reapply restores the name or id.
THEIRS = {
    "android/app/build.gradle.kts",
    "Tools/i18n_echo_baseline.txt",
    "README.md",
    "android/app/src/debug/res/values/strings.xml",
    "android/app/src/demo/res/values/strings.xml",
}

APP_ID_LINE = re.compile(
    r'^(?P<indent>[ \t]*)applicationId[ \t]*=[ \t]*"(?P<id>com\.noop\.whoop(?:\.ita)?)"[ \t]*$',
    re.MULTILINE,
)
APP_NAME_RE = re.compile(r'(<string name="app_name">)([^<]*)(</string>)')
STRINGS_OURS_TOUCH = re.compile(
    r"^android/app/src/main/res/values(?:-[^/]+)?/strings\.xml$"
)
BANNER = """<!-- FORK-IT-BANNER -->
> **NOOP IT** (`com.noop.whoop.ita`) is this fork's sideload build of [ryanbr/noop](https://github.com/ryanbr/noop). It installs beside official NOOP and uses upstream's Italian (`values-it`). Personal use under the PolyForm Noncommercial license. See [docs/FORK-IT.md](docs/FORK-IT.md).
<!-- /FORK-IT-BANNER -->

"""
ECHO_NOTE = (
    "Fork launcher name \"NOOP IT\" repeats the English source, so each locale that "
    "declares app_name is one echo above upstream. reapply_fork_identity.py owns that bump."
)


class IdentityError(Exception):
    """The tree cannot be given the fork id without a hand edit."""


class EchoOverflow(Exception):
    """Echo counts grew by more than the launcher-name override."""

    def __init__(self, extras: list[tuple[str, int, int]]):
        self.extras = extras
        super().__init__(self.format())

    def format(self) -> str:
        lines = [
            "Echo allowance exceeded by more than the NOOP IT launcher name.",
            "Taking upstream's baseline and adding that one echo still does not cover:",
        ]
        for target, found, allow in self.extras:
            lines.append(f"  {target}: found {found}, allowance {allow}")
        lines.append(
            "This is a real translation conflict, not the application id. "
            "Fix Tools/i18n_echo_baseline.txt by hand or drop the extra untranslated strings."
        )
        return "\n".join(lines)


def conflict_action(path: str) -> str:
    """How a conflicted path is resolved: 'ours', 'theirs', or 'fail'."""
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path in OURS:
        return "ours"
    if path in THEIRS or path.startswith("android/app/src/main/res/values-it/"):
        return "theirs"
    if STRINGS_OURS_TOUCH.fullmatch(path):
        return "theirs"
    return "fail"


def apply_application_id(text: str) -> str:
    """Point the defaultConfig applicationId at the sideload id.

    Leaves applicationIdSuffix and every other line alone. Raises IdentityError
    when the stock `com.noop.whoop` assignment is missing or duplicated, so a
    conflict resolution cannot silently publish the official id.
    """
    matches = list(APP_ID_LINE.finditer(text))
    if len(matches) != 1:
        raise IdentityError(
            "expected exactly one defaultConfig applicationId = \"com.noop.whoop\" "
            f"line in android/app/build.gradle.kts, found {len(matches)}. "
            "Restore that line from upstream, then re-run this script."
        )
    match = matches[0]
    indent = match.group("indent")
    line_start = text.rfind("\n", 0, match.start()) + 1
    prev_end = line_start - 1
    prev_start = text.rfind("\n", 0, max(prev_end, 0)) + 1
    prev_line = text[prev_start:prev_end] if prev_end >= 0 else ""
    replacement = f'{indent}applicationId = "{APP_ID}"'
    comment = (
        f"{indent}// {MARKER}: sideload id, installs beside official com.noop.whoop."
    )
    if match.group("id") == APP_ID and MARKER in prev_line:
        return text
    if MARKER in prev_line:
        return text[: match.start()] + replacement + text[match.end() :]
    return text[:line_start] + comment + "\n" + replacement + text[match.end() :]


def set_app_name(text: str, name: str) -> str | None:
    """Replace the first app_name value. None when the file has no such string or it already matches."""
    match = APP_NAME_RE.search(text)
    if match is None or match.group(2) == name:
        return None
    return APP_NAME_RE.sub(rf"\g<1>{name}\g<3>", text, count=1)


def ensure_banner(text: str) -> str:
    """Put the fork banner at the top of README, refreshing it when the wording drifted."""
    if "<!-- FORK-IT-BANNER -->" in text and "<!-- /FORK-IT-BANNER -->" in text:
        current = re.search(
            r"<!-- FORK-IT-BANNER -->.*?<!-- /FORK-IT-BANNER -->\n*",
            text,
            flags=re.S,
        )
        if current and current.group(0) == BANNER:
            return text
        return re.sub(
            r"<!-- FORK-IT-BANNER -->.*?<!-- /FORK-IT-BANNER -->\n*",
            BANNER,
            text,
            count=1,
            flags=re.S,
        )
    return BANNER + text.lstrip("\n")


def reconcile_allowance(
    echoes: dict[str, int],
    allowed: dict[str, int],
    targets: set[str],
) -> dict[str, int]:
    """Allowance updates for the launcher-name echo only.

    A locale that repeats "NOOP IT" is one new echo, because upstream's "NOOP"
    is a single word and is not counted. Growth of any other string, or of more
    than one echo on those lines, is refused.
    """
    updates: dict[str, int] = {}
    extras: list[tuple[str, int, int]] = []
    for target, found in sorted(echoes.items()):
        allow = allowed.get(target, 0)
        if found <= allow:
            continue
        if target in targets and found == allow + 1:
            updates[target] = found
        else:
            extras.append((target, found, allow))
    if extras:
        raise EchoOverflow(extras)
    return updates


def apply_allowance_updates(text: str, updates: dict[str, int]) -> str:
    """Write new counts into an echo-baseline file. Unknown targets are appended."""
    if not updates:
        return text
    lines = text.splitlines(keepends=True)
    seen: set[str] = set()
    out: list[str] = []
    note = f"# {ECHO_NOTE}\n"
    has_note = any(ECHO_NOTE in line for line in lines)
    for line in lines:
        raw = line.split("#", 1)[0].strip()
        if not raw:
            out.append(line)
            continue
        target, _, _count = raw.rpartition(" ")
        target = target.strip()
        if target not in updates:
            out.append(line)
            continue
        nl = "\n" if line.endswith("\n") else ""
        comment = ""
        if "#" in line:
            comment = " #" + line.split("#", 1)[1].rstrip("\n")
        out.append(f"{target} {updates[target]}{comment}{nl}")
        seen.add(target)
    missing = [t for t in sorted(updates) if t not in seen]
    if missing and out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    for target in missing:
        out.append(f"{target} {updates[target]}\n")
    rendered = "".join(out)
    if not has_note:
        if not rendered.endswith("\n"):
            rendered += "\n"
        rendered += note
    return rendered


def app_name_echo_targets(root: Path) -> set[str]:
    """Baseline keys whose app_name value is the English launcher name and therefore an echo."""
    import xml.etree.ElementTree as ET

    sys.path.insert(0, str(root / "Tools"))
    import i18n_audit as ia

    base_path = root / "android/app/src/main/res/values/strings.xml"
    base_name = ""
    for node in ET.parse(base_path).getroot().findall("string"):
        if node.attrib.get("name") == "app_name":
            base_name = node.text or ""
            break
    if not ia._has_translatable_words(base_name):
        return set()
    targets: set[str] = set()
    res = root / "android/app/src/main/res"
    for locale_dir in ia.shipped_android_locale_dirs():
        path = res / locale_dir / "strings.xml"
        lang = locale_dir[len("values-") :]
        for node in ET.parse(path).getroot().findall("string"):
            if node.attrib.get("name") == "app_name" and (node.text or "") == base_name:
                rel = path.relative_to(root).as_posix()
                targets.add(f"{rel} {lang}")
    return targets


def _write_if_changed(path: Path, text: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == text:
        return False
    path.write_text(text, encoding="utf-8")
    print(f"updated {path.relative_to(ROOT)}")
    return True


def reapply(root: Path) -> int:
    """Rewrite the id, launcher names, README banner, and the echo bump."""
    gradle = root / "android/app/build.gradle.kts"
    try:
        gradle_text = apply_application_id(gradle.read_text(encoding="utf-8"))
    except IdentityError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    _write_if_changed(gradle, gradle_text)

    names = [(path, APP_NAME) for path in sorted((root / "android/app/src/main/res").glob("values*/strings.xml"))]
    names.append((root / "android/app/src/debug/res/values/strings.xml", DEBUG_NAME))
    names.append((root / "android/app/src/demo/res/values/strings.xml", DEMO_NAME))
    for path, name in names:
        if not path.is_file():
            continue
        updated = set_app_name(path.read_text(encoding="utf-8"), name)
        if updated is not None:
            _write_if_changed(path, updated)

    readme = root / "README.md"
    _write_if_changed(readme, ensure_banner(readme.read_text(encoding="utf-8")))

    sys.path.insert(0, str(root / "Tools"))
    import i18n_audit as ia

    try:
        updates = reconcile_allowance(
            ia.echoed_translation_counts(),
            ia.echo_allowance(),
            app_name_echo_targets(root),
        )
    except EchoOverflow as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    baseline = root / "Tools/i18n_echo_baseline.txt"
    _write_if_changed(baseline, apply_allowance_updates(baseline.read_text(encoding="utf-8"), updates))
    return 0


def resolve_conflicts(root: Path) -> int:
    """Checkout ours or theirs for known conflicts. Exit 1 if anything else is unmerged."""
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=root,
        text=True,
    )
    paths = [line for line in out.splitlines() if line]
    if not paths:
        print("::error::Merge failed but no unmerged paths were found.", file=sys.stderr)
        return 1
    failed: list[str] = []
    for path in paths:
        action = conflict_action(path)
        if action == "fail":
            failed.append(path)
            continue
        print(f"{action}: {path}")
        subprocess.check_call(["git", "checkout", f"--{action}", "--", path], cwd=root)
        subprocess.check_call(["git", "add", "--", path], cwd=root)
    if failed:
        print(
            "::error::Unresolved conflicts. Auto-resolved paths are values-it "
            "(take upstream), build.gradle.kts (upstream, then applicationId "
            f"{APP_ID}), Tools/i18n_echo_baseline.txt (upstream, then the NOOP IT "
            "echo bump), and app_name string files. Resolve these by hand:",
            file=sys.stderr,
        )
        for path in failed:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "reapply"
    if command == "reapply":
        return reapply(ROOT)
    if command == "resolve-conflicts":
        return resolve_conflicts(ROOT)
    print(f"Unknown command {command!r}. Use reapply or resolve-conflicts.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
