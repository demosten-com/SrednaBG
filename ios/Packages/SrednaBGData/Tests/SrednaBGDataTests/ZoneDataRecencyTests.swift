// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Testing
@testable import SrednaBGData

/// Mirrors `android/app/src/test/.../ZoneDataRecencyTest.kt` one-for-one —
/// the Kotlin and Swift gates must stay semantically identical.
@Suite("ZoneDataRecency")
struct ZoneDataRecencyTests {
    private let older = "2026-07-13T06:10:40Z"
    private let newer = "2026-07-17T11:51:47Z"

    // MARK: isStrictlyNewer

    @Test func strictlyNewerTrueWhenCandidateIsLater() {
        #expect(ZoneDataRecency.isStrictlyNewer(newer, than: older) == true)
    }

    @Test func strictlyNewerFalseWhenCandidateIsEarlier() {
        #expect(ZoneDataRecency.isStrictlyNewer(older, than: newer) == false)
    }

    @Test func strictlyNewerFalseWhenEqual() {
        #expect(ZoneDataRecency.isStrictlyNewer(newer, than: newer) == false)
    }

    @Test func strictlyNewerNilOnLegacyOrMalformedVersions() {
        #expect(ZoneDataRecency.isStrictlyNewer("", than: newer) == nil)
        #expect(ZoneDataRecency.isStrictlyNewer(newer, than: "") == nil)
        #expect(ZoneDataRecency.isStrictlyNewer("v1", than: newer) == nil)
        // Non-zero-padded / missing Z would break lexicographic ordering, so
        // they must be rejected, not compared.
        #expect(ZoneDataRecency.isStrictlyNewer("2026-7-17T11:51:47Z", than: older) == nil)
        #expect(ZoneDataRecency.isStrictlyNewer("2026-07-17T11:51:47", than: older) == nil)
    }

    // MARK: decide

    @Test func decideUpToDateWhenHashesMatch() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h1", remoteVersion: older, cachedHash: "h1", cachedVersion: newer
        ) == .upToDate)
    }

    @Test func decideHashMatchWinsEvenWhenRemoteVersionIsNewer() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h1", remoteVersion: newer, cachedHash: "h1", cachedVersion: older
        ) == .upToDate)
    }

    @Test func decideAppliesRemoteWhenHashDiffersAndRemoteIsNewer() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h2", remoteVersion: newer, cachedHash: "h1", cachedVersion: older
        ) == .applyRemote)
    }

    @Test func decideSkipsRemoteWhenHashDiffersAndRemoteIsOlder() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h2", remoteVersion: older, cachedHash: "h1", cachedVersion: newer
        ) == .skipRemoteStale)
    }

    @Test func decideAppliesRemoteWhenHashDiffersAndVersionsAreEqual() {
        // Equal version + different hash can only mean corrupted local state
        // (a fresh scrape always carries a new timestamp) — the server repairs.
        #expect(ZoneDataRecency.decide(
            remoteHash: "h2", remoteVersion: newer, cachedHash: "h1", cachedVersion: newer
        ) == .applyRemote)
    }

    @Test func decideAppliesRemoteWhenEitherVersionIsNotComparable() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h2", remoteVersion: older, cachedHash: "h1", cachedVersion: "v1"
        ) == .applyRemote)
        #expect(ZoneDataRecency.decide(
            remoteHash: "h2", remoteVersion: "", cachedHash: "h1", cachedVersion: newer
        ) == .applyRemote)
    }

    @Test func decideAppliesRemoteWhenCachedHashIsEmpty() {
        #expect(ZoneDataRecency.decide(
            remoteHash: "h1", remoteVersion: newer, cachedHash: "", cachedVersion: ""
        ) == .applyRemote)
        // Even an equal empty hash means "nothing cached" — fetch.
        #expect(ZoneDataRecency.decide(
            remoteHash: "", remoteVersion: newer, cachedHash: "", cachedVersion: ""
        ) == .applyRemote)
    }

    // MARK: shouldReseedFromBundle

    @Test func reseedWhenBundleIsStrictlyNewerWithDifferentHash() {
        #expect(ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h2", bundleVersion: newer, cachedHash: "h1", cachedVersion: older
        ))
    }

    @Test func noReseedWhenBundleHashMatchesCached() {
        #expect(!ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h1", bundleVersion: newer, cachedHash: "h1", cachedVersion: older
        ))
    }

    @Test func noReseedWhenBundleIsOlderOrEqual() {
        #expect(!ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h2", bundleVersion: older, cachedHash: "h1", cachedVersion: newer
        ))
        #expect(!ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h2", bundleVersion: newer, cachedHash: "h1", cachedVersion: newer
        ))
    }

    @Test func noReseedWhenVersionsAreNotComparable() {
        #expect(!ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h2", bundleVersion: newer, cachedHash: "h1", cachedVersion: "v1"
        ))
        #expect(!ZoneDataRecency.shouldReseedFromBundle(
            bundleHash: "h2", bundleVersion: "", cachedHash: "h1", cachedVersion: older
        ))
    }
}
