// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SrednaBGCore
import Testing
@testable import SrednaBGData

/// Mirrors `android/app/src/test/.../ZoneSanitizerTest.kt` — the two guards
/// must drop exactly the same zones.
@Suite("ZoneSanitizer")
struct ZoneSanitizerTests {

    private func zone(
        id: String = "i8-01-west",
        start: ZoneEndpoint = ZoneEndpoint(lat: 42.4606211, lng: 23.803103),
        end: ZoneEndpoint = ZoneEndpoint(lat: 42.3793752, lng: 23.8763595),
        distanceM: Int = 11440,
        limits: SpeedLimits = SpeedLimits(car: 90, truck: 80, bus: 80),
        centerline: [[Double]] = [
            [42.4606211, 23.803103],
            [42.4200000, 23.840000],
            [42.3793752, 23.8763595]
        ]
    ) -> Zone {
        Zone(
            id: id,
            road: "Път I-8",
            roadLatin: "I-8",
            direction: "west",
            description: "Ихтиман – Мирово",
            start: start,
            end: end,
            distanceM: distanceM,
            speedLimits: limits,
            centerline: centerline,
            source: "bgtoll+tolltracker",
            lastVerified: "2026-08-03"
        )
    }

    @Test("a well-formed zone is usable")
    func wellFormedIsUsable() {
        #expect(ZoneSanitizer.isUsable(zone()))
    }

    // The exact shapes the 2026-08 Път I-8 merge failure put on the wire.

    @Test("an empty centerline is unusable")
    func emptyCenterline() {
        #expect(!ZoneSanitizer.isUsable(zone(centerline: [])))
    }

    @Test("a single-point centerline is unusable")
    func singlePointCenterline() {
        #expect(!ZoneSanitizer.isUsable(zone(centerline: [[42.46, 23.80]])))
    }

    @Test("placeholder zero-zero endpoints are unusable")
    func zeroEndpoints() {
        #expect(!ZoneSanitizer.isUsable(zone(start: ZoneEndpoint(lat: 0, lng: 0))))
        #expect(!ZoneSanitizer.isUsable(zone(end: ZoneEndpoint(lat: 0, lng: 0))))
    }

    @Test("a non-positive distance is unusable")
    func zeroDistance() {
        #expect(!ZoneSanitizer.isUsable(zone(distanceM: 0)))
    }

    @Test("a repaired zone is reported, not silently accepted")
    func repairIsReported() throws {
        // The shape that fails the whole decode on 1.x. This build survives it,
        // so the only way QA can see it is if the repair is reported.
        let json = Data("""
        {"version":"v","hash":"h","zones":[
          {"id":"i8-01-north","road":"Път I-8","direction":"north","description":"d",
           "start":{"lat":42.379,"lng":23.876},"end":{"lat":42.460,"lng":23.803},
           "distance_m":11440,"speed_limits":{"car":90},
           "centerline":[[42.379,23.876],[42.460,23.803]],
           "source":"tolltracker","last_verified":"2026-08-03"}
        ]}
        """.utf8)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(ZonesResponse.self, from: json)

        let result = ZoneSanitizer.sanitize(response.zones)
        #expect(result.repairedIds == ["i8-01-north"])
        #expect(result.droppedIds.isEmpty)
        #expect(result.zones.count == 1)
    }

    @Test("a complete zone is never reported as repaired")
    func completeZoneNotRepaired() {
        #expect(ZoneSanitizer.sanitize([zone()]).repairedIds.isEmpty)
    }

    @Test("one bad zone costs one zone, not the whole catalog")
    func oneBadZoneCostsOne() {
        let result = ZoneSanitizer.sanitize([
            zone(id: "good-1"),
            zone(id: "i8-02-east", start: ZoneEndpoint(lat: 0, lng: 0), centerline: []),
            zone(id: "good-2")
        ])
        #expect(result.zones.map(\.id) == ["good-1", "good-2"])
        #expect(result.droppedIds == ["i8-02-east"])
    }

    /// The iOS-specific half of the outage: a zone missing `truck` / `bus`
    /// used to throw `keyNotFound` and fail the decode of every zone with it,
    /// wedging sync permanently.
    @Test("a zone with only a car limit still decodes, falling back to car")
    func partialSpeedLimitsDecode() throws {
        let json = Data("""
        {"version":"2026-08-03T06:11:22Z","hash":"sha256:abc","zones":[
          {"id":"i8-01-north","road":"Път I-8","road_latin":"I-8","direction":"north",
           "description":"Мирово – Ихтиман",
           "start":{"lat":42.3793752,"lng":23.8763595},
           "end":{"lat":42.4606211,"lng":23.803103},
           "distance_m":11440,"speed_limits":{"car":90},
           "centerline":[[42.3793752,23.8763595],[42.4606211,23.803103]],
           "source":"tolltracker","last_verified":"2026-08-03"}
        ]}
        """.utf8)

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(ZonesResponse.self, from: json)

        #expect(response.zones.count == 1)
        let limits = try #require(response.zones.first).speedLimits
        #expect(limits.car == 90)
        #expect(limits.truck == 90)
        #expect(limits.bus == 90)
        #expect(limits.motorcycle == nil)
    }
}
