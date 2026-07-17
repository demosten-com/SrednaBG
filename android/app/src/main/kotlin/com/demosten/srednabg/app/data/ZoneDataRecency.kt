// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

/** Outcome of comparing remote zone data against what the client already has. */
enum class ZoneSyncDecision {
    /** Remote hash matches the cached hash — nothing to do. */
    UP_TO_DATE,

    /** Remote data should replace the local zones. */
    APPLY_REMOTE,

    /** Local data is provably newer than the remote — keep local. */
    SKIP_REMOTE_STALE,
}

/**
 * Recency gate for zone data. A hash mismatch alone does not mean the server
 * is newer — a client bundling a fresh local scrape can be ahead of the
 * weekly server cron. The `version` field is the scrape timestamp in the
 * fixed format `yyyy-MM-ddTHH:mm:ssZ` (UTC, zero-padded — see
 * `scrapers/src/zone_schema.py now_version()`), so lexicographic order equals
 * chronological order. Values that don't match that format (legacy "", "v1")
 * are treated as not comparable and fall back to the pre-recency behavior.
 *
 * Swift twin: `ios/Packages/SrednaBGData/Sources/SrednaBGData/ZoneDataRecency.swift`
 * — keep the semantics identical.
 */
object ZoneDataRecency {
    private val VERSION_FORMAT = Regex("""^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$""")

    /**
     * Whether [candidate] is strictly newer than [baseline]. Returns null when
     * either side isn't a well-formed version timestamp (not comparable).
     */
    fun isStrictlyNewer(candidate: String, baseline: String): Boolean? {
        if (!VERSION_FORMAT.matches(candidate) || !VERSION_FORMAT.matches(baseline)) return null
        return candidate > baseline
    }

    /** Gate for applying server data during a zone sync. */
    fun decide(
        remoteHash: String,
        remoteVersion: String,
        cachedHash: String,
        cachedVersion: String,
    ): ZoneSyncDecision = when {
        cachedHash.isNotEmpty() && remoteHash == cachedHash -> ZoneSyncDecision.UP_TO_DATE
        // Skip only when local data is provably NEWER than the remote. Equal
        // or not-comparable versions fall through to apply: a fresh scrape
        // always carries a new timestamp, so an equal version with a
        // different hash means corrupted local state — applying lets the
        // server repair it (and keeps the pre-recency behavior for legacy
        // installs with no stored version).
        isStrictlyNewer(cachedVersion, remoteVersion) == true -> ZoneSyncDecision.SKIP_REMOTE_STALE
        else -> ZoneSyncDecision.APPLY_REMOTE
    }

    /**
     * Gate for re-seeding a non-empty local store from the bundled zones.json
     * (app upgrade carrying fresher data than the last sync). Conservative:
     * requires the bundle to be provably newer — not-comparable keeps the
     * existing local data. The empty-store first-launch seed bypasses this.
     */
    fun shouldReseedFromBundle(
        bundleHash: String,
        bundleVersion: String,
        cachedHash: String,
        cachedVersion: String,
    ): Boolean = bundleHash != cachedHash &&
        isStrictlyNewer(bundleVersion, cachedVersion) == true
}
