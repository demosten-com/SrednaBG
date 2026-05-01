// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData
import SrednaBGCore

@Suite("ZoneStore")
struct ZoneStoreTests {

    private func tmpURL() -> URL {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("SrednaBGZoneStoreTests-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("zones.json")
    }

    private func sampleZone(id: String) -> Zone {
        Zone(
            id: id,
            road: "АМ Тракия",
            roadLatin: "Trakiya",
            direction: "west",
            description: "Test",
            start: ZoneEndpoint(lat: 42.427, lng: 23.855),
            end: ZoneEndpoint(lat: 42.550, lng: 23.703),
            distanceM: 19160,
            speedLimits: SpeedLimits(car: 140, truck: 90, bus: 100, motorcycle: 140),
            centerline: [[42.427, 23.855], [42.550, 23.703]],
            source: "test",
            lastVerified: "2026-04-12"
        )
    }

    @Test
    func emptyStoreLoadsCleanly() async {
        let store = ZoneStore(url: tmpURL())
        await store.loadFromDisk()
        #expect(await store.snapshot().isEmpty)
        #expect(await store.count() == 0)
    }

    @Test
    func replaceAllPersistsAndReloads() async throws {
        let url = tmpURL()
        let zoneA = sampleZone(id: "a")
        let zoneB = sampleZone(id: "b")

        let store = ZoneStore(url: url)
        try await store.replaceAll(with: [zoneA, zoneB])
        #expect(await store.count() == 2)

        let reloaded = ZoneStore(url: url)
        await reloaded.loadFromDisk()
        let snapshot = await reloaded.snapshot()
        #expect(snapshot == [zoneA, zoneB])
    }

    @Test
    func corruptCacheIsDroppedOnLoad() async throws {
        let url = tmpURL()
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try Data("not json".utf8).write(to: url)

        let store = ZoneStore(url: url)
        await store.loadFromDisk()
        #expect(await store.snapshot().isEmpty)
        #expect(!FileManager.default.fileExists(atPath: url.path),
                "Corrupt cache should have been removed")
    }
}
