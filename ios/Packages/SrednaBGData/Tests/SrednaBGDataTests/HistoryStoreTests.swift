// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData
import SrednaBGCore

@MainActor
@Suite("HistoryStore")
struct HistoryStoreTests {

    private func record(
        id: String,
        zoneId: String = "trakiya-01-east",
        exitTimeMs: Int64,
        avg: Double? = 118.0,
        over: Bool = false
    ) -> ZoneTraversalRecord {
        ZoneTraversalRecord(
            id: id,
            zoneId: zoneId,
            road: "АМ Тракия",
            roadLatin: "Trakiya",
            direction: "east",
            speedLimitKmh: 140,
            vehicleType: "car",
            entryTimeMs: exitTimeMs - 60_000,
            exitTimeMs: exitTimeMs,
            avgSpeedKmh: avg,
            sustainedMinKmh: 90,
            sustainedMaxKmh: 130,
            isOverLimit: over,
            distanceM: 19_000,
            samples: ZoneTraversalRecord.encodeSamples([
                SpeedSample(timestampMs: exitTimeMs - 60_000, speedKmh: 100),
                SpeedSample(timestampMs: exitTimeMs, speedKmh: 120)
            ])
        )
    }

    @Test func insertAndFetchAllSortsByExitDescending() throws {
        let store = try HistoryStore.inMemory()
        store.insert(record(id: "a", exitTimeMs: 1_000))
        store.insert(record(id: "b", exitTimeMs: 3_000))
        store.insert(record(id: "c", exitTimeMs: 2_000))

        let all = store.fetchAll()
        #expect(all.map(\.id) == ["b", "c", "a"])
        #expect(store.count() == 3)
        #expect(store.fetchLatest()?.id == "b")
        #expect(store.fetchById("c")?.exitTimeMs == 2_000)
    }

    @Test func emptyStoreReportsNoLatest() throws {
        let store = try HistoryStore.inMemory()
        #expect(store.count() == 0)
        #expect(store.fetchLatest() == nil)
    }

    @Test func pruneDropsOnlyRecordsOlderThanCutoff() throws {
        let store = try HistoryStore.inMemory()
        store.insert(record(id: "old", exitTimeMs: 1_000))
        store.insert(record(id: "new", exitTimeMs: 10_000))

        store.prune(olderThanMs: 5_000)
        #expect(store.fetchAll().map(\.id) == ["new"])
    }

    @Test func applyRetentionNonePurgesEverything() throws {
        let store = try HistoryStore.inMemory()
        store.insert(record(id: "a", exitTimeMs: 1_000))
        store.insert(record(id: "b", exitTimeMs: 2_000))

        store.applyRetention(.none, nowMs: 10_000)
        #expect(store.count() == 0)
    }

    @Test func applyRetentionKeepsRecordsInsideWindow() throws {
        let store = try HistoryStore.inMemory()
        let now: Int64 = 200 * 24 * 60 * 60 * 1000
        // Well inside 3 months (90 days), and well outside it.
        store.insert(record(id: "recent", exitTimeMs: now - 10 * 24 * 60 * 60 * 1000))
        store.insert(record(id: "stale", exitTimeMs: now - 100 * 24 * 60 * 60 * 1000))

        store.applyRetention(.threeMonths, nowMs: now)
        #expect(store.fetchAll().map(\.id) == ["recent"])
    }

    @Test func encodedSamplesRoundTrip() throws {
        let store = try HistoryStore.inMemory()
        store.insert(record(id: "a", exitTimeMs: 1_000))
        let fetched = try #require(store.fetchById("a"))
        #expect(fetched.speedSamples.count == 2)
        #expect(fetched.speedSamples.first?.speedKmh == 100)
    }
}
