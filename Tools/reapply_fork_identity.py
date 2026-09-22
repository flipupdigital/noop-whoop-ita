#!/usr/bin/env python3
"""Put the FlipUp fork's launcher name and README banner back after an upstream merge.

Upstream files say "NOOP". This fork's launcher name is "NOOP IT" so it can sit
beside the official app. A merge that takes upstream's string resources drops
that name; this script writes it back. It does not translate new strings —
Tools/generate_values_it.py does that, and only for keys that are still missing.

The script also refuses to pass silently when the Gradle hook that reads
android/fork.properties has been lost in a conflict. That hook is what keeps
applicationId = com.noop.whoop.ita.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRADLE = ROOT / "android/app/build.gradle.kts"
MARKER = "FORK-IT-IDENTITY"
README = ROOT / "README.md"
BANNER = """<!-- FORK-IT-BANNER -->
> **Fork italiano FlipUp.** Interfaccia Android in italiano, APK da sideload con id `com.noop.whoop.ita` (nome **NOOP IT**, si installa accanto a NOOP ufficiale) e sincronizzazione da [ryanbr/noop](https://github.com/ryanbr/noop). Istruzioni: [docs/FORK-IT.md](docs/FORK-IT.md).
>
> **Italian FlipUp fork.** Italian Android UI, a sideload APK (`com.noop.whoop.ita`, launcher name **NOOP IT**) that installs beside official NOOP, and a sync from [ryanbr/noop](https://github.com/ryanbr/noop). See [docs/FORK-IT.md](docs/FORK-IT.md).
<!-- /FORK-IT-BANNER -->

"""

APP_NAME_RE = re.compile(r'(<string name="app_name">)([^<]*)(</string>)')


def set_app_name(path: Path, name: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    match = APP_NAME_RE.search(text)
    if match is None or match.group(2) == name:
        return False
    path.write_text(APP_NAME_RE.sub(rf"\g<1>{name}\g<3>", text, count=1), encoding="utf-8")
    print(f"app_name -> {name}: {path.relative_to(ROOT)}")
    return True


def ensure_banner() -> None:
    text = README.read_text(encoding="utf-8")
    if "<!-- FORK-IT-BANNER -->" in text and "<!-- /FORK-IT-BANNER -->" in text:
        return
    stripped = re.sub(
        r"<!-- FORK-IT-BANNER -->.*?<!-- /FORK-IT-BANNER -->\n*",
        "",
        text,
        count=1,
        flags=re.S,
    )
    README.write_text(BANNER + stripped.lstrip("\n"), encoding="utf-8")
    print("README banner restored")


def ensure_changelog_locale() -> int:
    """What's New titles are written for every directory in LOCALE_DIRS.

    A values-it tree that is missing from that map makes Tools Python CI fail
    and drops an Italian title if one is supplied. Upstream merges can reset
    the map; put the Italian entry back.
    """
    path = ROOT / "Tools/appchangelog-gen.py"
    text = path.read_text(encoding="utf-8")
    if '"it": "values-it"' in text:
        return 0
    old = '"pl": "values-pl", "ru": "values-ru"}'
    new = '"pl": "values-pl", "ru": "values-ru", "it": "values-it"}'
    if old not in text:
        print(
            "values-it is not in Tools/appchangelog-gen.py LOCALE_DIRS, and the "
            "expected line was not found. Add \"it\": \"values-it\" before merging.",
            file=sys.stderr,
        )
        return 1
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("LOCALE_DIRS gained it -> values-it")
    return 0


def ensure_gradle_hook() -> int:
    text = GRADLE.read_text(encoding="utf-8")
    if MARKER not in text or "fork.properties" not in text:
        print(
            "FORK-IT-IDENTITY is missing from android/app/build.gradle.kts.\n"
            "An upstream merge conflict likely dropped the hook that reads\n"
            "android/fork.properties (applicationId com.noop.whoop.ita).\n"
            "Restore that block before merging the sync PR. See docs/FORK-IT.md.",
            file=sys.stderr,
        )
        return 1
    props = ROOT / "android/fork.properties"
    if not props.is_file() or "com.noop.whoop.ita" not in props.read_text(encoding="utf-8"):
        print("android/fork.properties is missing applicationId=com.noop.whoop.ita", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    res = ROOT / "android/app/src/main/res"
    for path in sorted(res.glob("values*/strings.xml")):
        set_app_name(path, "NOOP IT")
    set_app_name(ROOT / "android/app/src/debug/res/values/strings.xml", "NOOP IT Debug")
    set_app_name(ROOT / "android/app/src/demo/res/values/strings.xml", "NOOP IT Demo")
    ensure_banner()
    return ensure_changelog_locale() or ensure_gradle_hook()


if __name__ == "__main__":
    raise SystemExit(main())
