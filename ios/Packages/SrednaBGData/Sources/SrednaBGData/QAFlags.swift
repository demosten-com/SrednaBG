// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// QA-only runtime flags toggled by the `srednabg-debug://` URL scheme.
///
/// Kept off the main `SettingsStore` so a QA run can't accidentally bleed
/// into a user's preferences (the flags live under separate UserDefaults
/// keys and never appear in the Settings screen). Reads are
/// `UserDefaults.standard` lookups — fast enough to do on the GPS hot path.
public enum QAFlags {

    /// When true, the TTS engine drops `speak` calls. The `speak:` log line
    /// still fires (QA tripwire), so muting doesn't break the parser
    /// self-test — only the audible output is suppressed.
    public static var ttsMuted: Bool {
        get { UserDefaults.standard.bool(forKey: "qa_tts_muted") }
        set { UserDefaults.standard.set(newValue, forKey: "qa_tts_muted") }
    }

    /// When true, sync calls short-circuit to `Failed` without hitting the
    /// network. The Android counterpart toggles airplane mode; iOS has no
    /// scriptable equivalent so we gate at the app layer.
    public static var networkOffline: Bool {
        get { UserDefaults.standard.bool(forKey: "qa_network_offline") }
        set { UserDefaults.standard.set(newValue, forKey: "qa_network_offline") }
    }
}

/// Compile-time ship gates. Distinct from `QAFlags` (runtime QA toggles) — these
/// stay constant across every build flavor and only flip in a release that
/// intentionally enables the feature.
public enum FeatureFlags {

    /// Map-sync client paths (`runMapSync`, `BackgroundSyncScheduler.scheduleMapSync`,
    /// `SyncClient.downloadMapBundle`) are plumbed but the production backend
    /// (`srednabg.com/api/*`) does not yet serve `/api/map/bundle.zip` or
    /// populate `map_hash` — the Namecheap scraper cron only emits zones. Stay
    /// `false` across debug and release until the backend bundle pipeline is
    /// live and the round-trip has been QA'd; otherwise we'd ship untested
    /// client code that lights up the moment the backend changes. Mirrors
    /// `FeatureFlags.IS_MAP_SYNC_ENABLED` on Android.
    public static let isMapSyncEnabled = false
}
