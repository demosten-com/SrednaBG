// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Outcome of comparing remote zone data against what the client already has.
public enum ZoneSyncDecision: Sendable {
    /// Remote hash matches the cached hash — nothing to do.
    case upToDate
    /// Remote data should replace the local zones.
    case applyRemote
    /// Local data is provably newer than the remote — keep local.
    case skipRemoteStale
}

/// Recency gate for zone data. A hash mismatch alone does not mean the server
/// is newer — a client bundling a fresh local scrape can be ahead of the
/// weekly server cron. The `version` field is the scrape timestamp in the
/// fixed format `yyyy-MM-ddTHH:mm:ssZ` (UTC, zero-padded — see
/// `scrapers/src/zone_schema.py now_version()`), so lexicographic order equals
/// chronological order. Values that don't match that format (legacy "", "v1")
/// are treated as not comparable and fall back to the pre-recency behavior.
///
/// Kotlin twin: `android/app/.../data/ZoneDataRecency.kt` — keep the
/// semantics identical.
public enum ZoneDataRecency {
    private static let versionFormat = "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"

    private static func isWellFormed(_ version: String) -> Bool {
        version.range(of: versionFormat, options: .regularExpression) != nil
    }

    /// Whether `candidate` is strictly newer than `baseline`. Returns nil when
    /// either side isn't a well-formed version timestamp (not comparable).
    public static func isStrictlyNewer(_ candidate: String, than baseline: String) -> Bool? {
        guard isWellFormed(candidate), isWellFormed(baseline) else { return nil }
        return candidate > baseline
    }

    /// Gate for applying server data during a zone sync.
    public static func decide(
        remoteHash: String,
        remoteVersion: String,
        cachedHash: String,
        cachedVersion: String
    ) -> ZoneSyncDecision {
        if !cachedHash.isEmpty, remoteHash == cachedHash { return .upToDate }
        // Skip only when local data is provably NEWER than the remote. Equal
        // or not-comparable versions fall through to apply: a fresh scrape
        // always carries a new timestamp, so an equal version with a
        // different hash means corrupted local state — applying lets the
        // server repair it (and keeps the pre-recency behavior for legacy
        // installs with no stored version).
        if isStrictlyNewer(cachedVersion, than: remoteVersion) == true { return .skipRemoteStale }
        return .applyRemote
    }

    /// Gate for re-seeding a non-empty local store from the bundled
    /// zones.json (app upgrade carrying fresher data than the last sync).
    /// Conservative: requires the bundle to be provably newer — not-comparable
    /// keeps the existing local data. The empty-store first-launch seed
    /// bypasses this.
    public static func shouldReseedFromBundle(
        bundleHash: String,
        bundleVersion: String,
        cachedHash: String,
        cachedVersion: String
    ) -> Bool {
        bundleHash != cachedHash &&
            isStrictlyNewer(bundleVersion, than: cachedVersion) == true
    }
}
