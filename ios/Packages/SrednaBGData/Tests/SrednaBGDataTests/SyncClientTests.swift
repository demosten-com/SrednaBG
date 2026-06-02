// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import Testing
@testable import SrednaBGData
import SrednaBGCore

// `.serialized` because MockURLProtocol's handler is process-wide static
// state — parallel tests would race to set/clear it and clobber each other.
@Suite("SyncClient", .serialized)
struct SyncClientTests {

    private let urls = BackendURLs(baseURL: URL(string: "https://api.test.local")!)

    @Test
    func fetchVersionDecodesSnakeCase() async throws {
        let body = Data("""
        {
          "version": "2026-04-12T10:00:00Z",
          "hash": "sha256:abc",
          "min_app_version": "1.0.0",
          "zone_count": 72,
          "map_hash": "sha256:def"
        }
        """.utf8)
        MockURLProtocol.setHandler { req in
            (.ok(req.url!), body)
        }
        defer { MockURLProtocol.setHandler(nil) }

        let client = SyncClient(urls: urls, session: MockURLProtocol.makeSession())
        let response = try await client.fetchVersion()

        #expect(response.version == "2026-04-12T10:00:00Z")
        #expect(response.hash == "sha256:abc")
        #expect(response.minAppVersion == "1.0.0")
        #expect(response.zoneCount == 72)
        #expect(response.mapHash == "sha256:def")
    }

    @Test
    func fetchZonesRoundTripsZone() async throws {
        let zone = Zone(
            id: "trakiya-01-west",
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
        // Hand-crafted snake_case body — the API decoder must convert to camelCase.
        let body = Data("""
        {
          "version": "v1",
          "hash": "sha256:zzz",
          "zones": [
            {
              "id": "trakiya-01-west",
              "road": "АМ Тракия",
              "road_latin": "Trakiya",
              "direction": "west",
              "description": "Test",
              "start": {"lat": 42.427, "lng": 23.855},
              "end":   {"lat": 42.550, "lng": 23.703},
              "distance_m": 19160,
              "speed_limits": {"car": 140, "truck": 90, "bus": 100, "motorcycle": 140},
              "centerline": [[42.427, 23.855], [42.550, 23.703]],
              "source": "test",
              "last_verified": "2026-04-12"
            }
          ]
        }
        """.utf8)
        MockURLProtocol.setHandler { req in (.ok(req.url!), body) }
        defer { MockURLProtocol.setHandler(nil) }

        let client = SyncClient(urls: urls, session: MockURLProtocol.makeSession())
        let response = try await client.fetchZones()

        #expect(response.hash == "sha256:zzz")
        #expect(response.zones.count == 1)
        #expect(response.zones[0] == zone)
    }

    @Test
    func freshnessRequestsBypassHTTPCache() async throws {
        // Regression guard: the backend serves `/api/version` with
        // `Cache-Control: max-age=300`, so the default `.useProtocolCachePolicy`
        // would let `URLSession` answer a "Sync now" tap from `URLCache` without
        // a network round-trip. Every SyncClient request must force a reload.
        let captured = CapturedCachePolicy()
        let body = Data(#"{"version":"v","hash":"sha256:abc"}"#.utf8)
        MockURLProtocol.setHandler { req in
            captured.set(req.cachePolicy)
            return (.ok(req.url!), body)
        }
        defer { MockURLProtocol.setHandler(nil) }

        let client = SyncClient(urls: urls, session: MockURLProtocol.makeSession())
        _ = try await client.fetchVersion()

        #expect(captured.value == .reloadIgnoringLocalCacheData)
    }

    @Test
    func httpFailureSurfacesAsError() async {
        MockURLProtocol.setHandler { req in (.status(503, req.url!), Data()) }
        defer { MockURLProtocol.setHandler(nil) }

        let client = SyncClient(urls: urls, session: MockURLProtocol.makeSession())
        await #expect(throws: SyncClientError.self) {
            _ = try await client.fetchVersion()
        }
    }

    @Test
    func emptyBodySurfacesAsError() async {
        MockURLProtocol.setHandler { req in (.ok(req.url!), Data()) }
        defer { MockURLProtocol.setHandler(nil) }

        let client = SyncClient(urls: urls, session: MockURLProtocol.makeSession())
        await #expect(throws: SyncClientError.self) {
            _ = try await client.fetchVersion()
        }
    }
}

/// Lock-guarded capture box. The mock handler runs on the URL loading thread,
/// not the test actor, so the captured value is read back after the awaited
/// request returns (see `MockURLProtocol`'s strict-concurrency note).
private final class CapturedCachePolicy: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: URLRequest.CachePolicy?

    func set(_ policy: URLRequest.CachePolicy) {
        lock.lock(); defer { lock.unlock() }
        stored = policy
    }

    var value: URLRequest.CachePolicy? {
        lock.lock(); defer { lock.unlock() }
        return stored
    }
}
