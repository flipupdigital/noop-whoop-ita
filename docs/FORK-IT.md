# Fork italiano FlipUp / Italian FlipUp fork

This repository is a fork of [ryanbr/noop](https://github.com/ryanbr/noop) for Italian Android use.
The upstream license stays [PolyForm Noncommercial 1.0.0](../LICENSE). [DISCLAIMER.md](../DISCLAIMER.md),
[ATTRIBUTION.md](../ATTRIBUTION.md), and [NOTICE](../NOTICE) are unchanged. NOOP is not affiliated
with WHOOP.

## What this fork changes

| | Official NOOP | This fork |
|---|---|---|
| Launcher name | NOOP | **NOOP IT** (debug: NOOP IT Debug, demo: NOOP IT Demo) |
| Android `applicationId` | `com.noop.whoop` | `com.noop.whoop.ita` |
| UI language | Phone language, including de/es/fr/… | Italian when the phone is set to Italian (`values-it`) |
| Signing of the sideload APK | Release key, or debug key for staging | Debug keystore already in `android/fork-debug.keystore` |

`applicationId` is set in [`android/fork.properties`](../android/fork.properties), which upstream does
not have. [`android/app/build.gradle.kts`](../android/app/build.gradle.kts) reads it only when that
file exists (the `FORK-IT-IDENTITY` block). The two apps can be installed on the same phone. They do
not share a database. Pair the strap in NOOP IT the same way you would in NOOP; a bond is per app
data, so the first launch of NOOP IT pairs again.

Delete `android/fork.properties` to build as stock `com.noop.whoop`. A real release then needs
`keystore.properties` again.

Code identifiers, route ids, and protocol names stay English.

## Install the APK

1. On the phone: **Impostazioni → Sicurezza** (the label varies) and allow installs from the browser
   or file app you will use. On Android 8+ this is **Installa app sconosciute** for that app.
2. Download `NOOP-IT-android.apk` from the **Android APK** workflow artifact on the pull request or
   on the Actions tab, or from the rolling release
   [noop-it-latest](https://github.com/flipupdigital/noop-whoop-ita/releases/tag/noop-it-latest)
   after someone runs **Android APK** with `workflow_dispatch`.
3. Open the file and install. The launcher icon is **NOOP IT**.
4. Play Protect often blocks sideloaded apps that are not from the Play Store. Choose
   **Installa comunque** / **Install anyway**. The APK is signed with this repo's debug key, not a
   Play upload key. Updates install over the same id only if the next APK is signed with the same
   key (`android/fork-debug.keystore`).

Build it yourself (JDK 17, Android SDK 35):

```bash
echo "sdk.dir=$ANDROID_HOME" > android/local.properties
cd android && ./gradlew assembleFullRelease
```

The APK is `android/app/build/outputs/apk/full/release/`. `minSdk` is 26 (Android 8).

Bluetooth behavior is not proven by this build. Pair a real strap before trusting live heart rate
or sleep sync. See the upstream BLE notes in [AGENTS.md](../AGENTS.md).

## Italian strings

User-facing Android copy is in:

- `android/app/src/main/res/values-it/strings.xml`
- `android/app/src/main/res/values-it/steps_view.xml`

Navigation, onboarding, terms, and the score names **Riposo / Carica / Sforzo** (Rest / Charge /
Effort) were written for this fork. The rest was machine-translated from `values/strings.xml` with
WHOOP, NOOP, and format specifiers (`%1$s`, `%1$d`) shielded. Edit `values-it` directly to change
wording. Do not rename the `name=` keys.

`python3 Tools/generate_values_it.py` fills **missing** keys only, so hand edits stay.
`python3 Tools/generate_values_it.py --force` regenerates everything and keeps the override table
inside that script; other hand edits in the XML are replaced.

### Still English

- 216 Compose strings were already hardcoded in Kotlin before this fork. They are listed in
  `Tools/i18n_audit_baseline.json` and stay English on every locale, including Italian. The largest
  groups are `WorkoutsScreen.kt`, `SettingsScreen.kt`, `HealthScreen.kt`, and `LiveScreen.kt`.
  New hardcoded literals fail CI; this fork does not add any.
- A short list of resource values is intentionally the same as English: Apple Health, Health
  Connect, HRV, Wim Hof, Mi Band, and internal labels such as `wordmark-dx`.
- iOS and macOS catalogs are not part of this change. An Italian phone still gets Italian for
  Android resources only.

## Sync from ryanbr/noop

Workflow: [`.github/workflows/sync-upstream.yml`](../.github/workflows/sync-upstream.yml).

- Runs every Monday at 06:17 UTC, and whenever someone starts **Sync upstream** from the Actions tab.
- Fetches `https://github.com/ryanbr/noop` `main`.
- Updates branch `upstream-sync` from this fork's `main`, then merges upstream.
- Keeps `values-it`, `docs/FORK-IT.md`, `android/fork.properties`, and the fork workflows if those
  paths conflict.
- Takes upstream's English `strings.xml` on conflict, then `Tools/reapply_fork_identity.py` puts the
  launcher name **NOOP IT** and the README banner back.
- Tries to translate keys that upstream added. If that step cannot reach the translator, those keys
  stay missing and the app shows English for them (Android falls back to `values/`).
- Opens or updates a pull request into `main`. It does not push to `main` by itself.

If the job fails, the usual cause is a conflict in `android/app/build.gradle.kts`. Keep the
`FORK-IT-IDENTITY` block. Losing it builds `com.noop.whoop` again and the install replaces or
clashes with official NOOP.

You can also use GitHub's **Sync fork** button. That is a plain merge and can drop the launcher
name or the Gradle hook if those lines conflict. Prefer the Action, then check the PR. After a
manual sync, run:

```bash
python3 Tools/reapply_fork_identity.py
python3 Tools/generate_values_it.py
```

## License

Contributions in this fork are under the same PolyForm Noncommercial 1.0.0 terms as upstream.
Do not remove the upstream license, disclaimer, or attribution when syncing.
