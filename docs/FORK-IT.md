# NOOP IT fork

This repository tracks [ryanbr/noop](https://github.com/ryanbr/noop). It is for personal use under the [PolyForm Noncommercial 1.0.0](../LICENSE) license.

The only product changes versus upstream are the launcher name **NOOP IT** and `applicationId` `com.noop.whoop.ita`, so the sideload APK installs beside official NOOP (`com.noop.whoop`). Italian UI strings are upstream's `android/app/src/main/res/values-it`.

## Install

The sideload APK is the `NOOP-IT-android` artifact from the Android sideload APK workflow, and the asset on the rolling `noop-it-latest` prerelease. It is signed with `android/fork-debug.keystore`. Android may warn that the app is not from a store.

The release build does not pass `-PstagingRelease`, so the id is `com.noop.whoop.ita` rather than `com.noop.whoop.ita.staging`. CI writes a gitignored `android/keystore.properties` that points the release signing config at the fork debug keystore.

WHOOP 4.0 and 5.0 use the same app.

## Upstream sync

`.github/workflows/sync-upstream.yml` merges `ryanbr/noop` `main` and opens a pull request. On a conflict it:

- takes upstream for `android/app/src/main/res/values-it/`
- takes upstream for `android/app/build.gradle.kts`, then restores only `applicationId = "com.noop.whoop.ita"`
- takes upstream for `Tools/i18n_echo_baseline.txt`, then adds back the single echo caused by the launcher name **NOOP IT**
- takes upstream for the other `app_name` string files, then sets them back to **NOOP IT**
- keeps this fork's sync workflow, APK workflow, and `Tools/reapply_fork_identity.py`

Any other conflict fails the job and lists the paths. Nothing is pushed until that list is empty.

Run `python3 Tools/reapply_fork_identity.py` after a manual merge. It refuses to finish when the `com.noop.whoop` application id line is gone, or when echo counts grew by more than the launcher name.
