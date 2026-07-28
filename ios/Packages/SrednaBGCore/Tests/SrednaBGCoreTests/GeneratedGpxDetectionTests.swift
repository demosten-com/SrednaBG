// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation
import Testing
@testable import SrednaBGCore

/// Mirrors GeneratedGpxDetectionTest.kt — guards against the class of bug
/// where GPX files produced by `scrapers/scripts/make_test_route.py` drift
/// off-road on the approach, so ZoneDetector misses zone entry until the drive
/// is already deep inside the zone.
@Suite("GeneratedGpxDetection")
struct GeneratedGpxDetectionTests {

    @Test(arguments: ["struma-02-south"])
    func generatedGpxEntersZoneBeforeMidpointAndExitsCleanly(zoneId: String) throws {
        let zone = try loadZone(zoneId: zoneId)
        let gpxPoints = try parseGpx(resource: "Resources/gpx/\(zoneId)", ext: "gpx")
        #expect(gpxPoints.count > 20, "GPX fixture suspiciously short: \(gpxPoints.count)")

        let c0 = zone.centerline.first!
        let zoneStartIdx = gpxPoints.firstIndex(where: { $0.lat == c0[0] && $0.lng == c0[1] }) ?? -1
        // Zone boundary must be an explicit GPX point — without this guarantee the
        // original bug could recur (whole-polyline resampling at step_m skipping past
        // centerline[0], landing the zone crossing "between samples" and shifting
        // detected entry by up to a full sample interval).
        #expect(
            zoneStartIdx >= 0,
            "Zone \(zoneId) centerline[0] (\(c0[0]), \(c0[1])) is not an explicit GPX point — make_test_route.py must emit the zone boundary verbatim"
        )

        var detector = ZoneDetector(zones: [zone])
        let states = gpxPoints.map { detector.update($0) }

        let firstInZoneIdx = states.firstIndex(where: { state in
            if case .inZone = state { return true }
            return false
        }) ?? -1
        #expect(firstInZoneIdx >= 0, "Zone \(zoneId) was never entered during playback")

        // The inZone *flip* now trails the zone start: a traversal only opens
        // once the match has held over `ZoneDetector.entryConfirmDistanceM` of
        // travel along the centerline, so a neighbouring road that merely clips
        // the on-road band can't open one. What must NOT slip is the recorded
        // entry — the traversal is back-dated to the first confirming fix, so
        // the reported entryTime still lands at or before the zone-start sample
        // (`ZoneDetector.entryDistanceM` lets the approach count).
        guard case .inZone(let firstInZone) = states[firstInZoneIdx] else {
            Issue.record("Zone \(zoneId) first inZone index did not hold an inZone state")
            return
        }
        #expect(
            firstInZone.entryTime <= gpxPoints[zoneStartIdx].timestamp,
            "Zone \(zoneId) recorded entryTime \(firstInZone.entryTime) is AFTER the zone-start sample at \(gpxPoints[zoneStartIdx].timestamp) — the traversal was not back-dated to the approach"
        )

        // And the flip itself must land inside the confirmation window, not deep
        // inside the zone — a genuinely lost transition shows up as a much larger
        // lag than the window can explain.
        let lagM = (zoneStartIdx..<firstInZoneIdx).reduce(0.0) { acc, i in
            acc + haversineDistance(
                gpxPoints[i].lat, gpxPoints[i].lng,
                gpxPoints[i + 1].lat, gpxPoints[i + 1].lng
            )
        }
        #expect(
            lagM <= ZoneDetector.entryConfirmDistanceM * 1.5,
            "Zone \(zoneId) entry fired \(Int(lagM)) m past the zone start (GPX index \(firstInZoneIdx) vs \(zoneStartIdx)) — more than the confirmation window explains, so the detector lost the transition"
        )

        let exited = states.contains(where: { state in
            if case .exiting = state { return true }
            return false
        })
        #expect(exited, "Zone \(zoneId) never exited — centerline traversal did not complete")

        let inZoneCount = states.filter {
            if case .inZone = $0 { return true } else { return false }
        }.count
        #expect(
            Double(inZoneCount) >= Double(gpxPoints.count) * 0.25,
            "Only \(inZoneCount) / \(gpxPoints.count) points registered InZone — detector is losing the zone mid-traversal"
        )
    }

    private func loadZone(zoneId: String) throws -> Zone {
        let url = try #require(
            Bundle.module.url(forResource: "Resources/zones_subset", withExtension: "json"),
            "Missing test resource zones_subset.json"
        )
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let db = try decoder.decode(TestZoneDatabase.self, from: data)
        let zone = try #require(
            db.zones.first(where: { $0.id == zoneId }),
            "Zone \(zoneId) missing from zones_subset.json"
        )
        return zone.toCoreZone()
    }

    private func parseGpx(resource: String, ext: String) throws -> [GpsPoint] {
        let url = try #require(
            Bundle.module.url(forResource: resource, withExtension: ext),
            "Missing GPX fixture \(resource).\(ext)"
        )
        let xml = try String(contentsOf: url, encoding: .utf8)
        let regex = try NSRegularExpression(
            pattern: #"<trkpt\s+lat="([\d.\-]+)"\s+lon="([\d.\-]+)">"#
        )
        let nsXml = xml as NSString
        let matches = regex.matches(in: xml, range: NSRange(location: 0, length: nsXml.length))
        let coords: [(Double, Double)] = matches.compactMap { m in
            guard m.numberOfRanges == 3 else { return nil }
            let lat = Double(nsXml.substring(with: m.range(at: 1))) ?? .nan
            let lng = Double(nsXml.substring(with: m.range(at: 2))) ?? .nan
            return (lat, lng)
        }
        try #require(coords.count >= 2, "Not enough trkpt entries in \(resource).\(ext)")

        // Synthetic 1 Hz timeline. Playback speed doesn't affect detection so long
        // as we stay above ZoneDetector.stopSpeedKmh everywhere.
        let dtMs: Int64 = 1_000
        let epochBaseLocal: Int64 = 1_700_000_000_000
        var points: [GpsPoint] = []
        points.reserveCapacity(coords.count)
        for i in coords.indices {
            let (lat, lng) = coords[i]
            let bearing: Double
            let speedKmh: Double
            if i == 0 {
                bearing = bearingBetween(coords[0].0, coords[0].1, coords[1].0, coords[1].1)
                speedKmh = haversineDistance(coords[0].0, coords[0].1, coords[1].0, coords[1].1) * 3.6
            } else {
                bearing = bearingBetween(coords[i - 1].0, coords[i - 1].1, lat, lng)
                speedKmh = haversineDistance(coords[i - 1].0, coords[i - 1].1, lat, lng) * 3.6
            }
            points.append(GpsPoint(
                lat: lat,
                lng: lng,
                speed: speedKmh,
                timestamp: epochBaseLocal + Int64(i) * dtMs,
                bearing: bearing
            ))
        }
        return points
    }
}

private struct TestZoneDatabase: Decodable {
    let zones: [TestZoneDto]
}

private struct TestZoneDto: Decodable {
    let id: String
    let road: String
    let roadLatin: String?
    let direction: String
    let description: String
    let start: TestEndpointDto
    let end: TestEndpointDto
    let distanceM: Int
    let speedLimits: TestSpeedLimitsDto
    let centerline: [[Double]]
    let source: String
    let lastVerified: String

    func toCoreZone() -> Zone {
        Zone(
            id: id,
            road: road,
            roadLatin: roadLatin,
            direction: direction,
            description: description,
            start: start.toCore(),
            end: end.toCore(),
            distanceM: distanceM,
            speedLimits: speedLimits.toCore(),
            centerline: centerline,
            source: source,
            lastVerified: lastVerified
        )
    }
}

private struct TestEndpointDto: Decodable {
    let lat: Double
    let lng: Double
    let kmMarker: String?
    let settlement: String?
    let settlementLatin: String?

    func toCore() -> ZoneEndpoint {
        ZoneEndpoint(lat: lat, lng: lng, kmMarker: kmMarker, settlement: settlement, settlementLatin: settlementLatin)
    }
}

private struct TestSpeedLimitsDto: Decodable {
    let car: Int
    let truck: Int
    let bus: Int
    let motorcycle: Int?

    func toCore() -> SpeedLimits {
        SpeedLimits(car: car, truck: truck, bus: bus, motorcycle: motorcycle)
    }
}
