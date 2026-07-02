// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

// Debug-only: reachable solely through `DebugActionRouter` (`/history?action=seed`),
// which is itself `#if DEBUG`. Gating the implementation keeps the fabricated
// sample data — and the fixed BG-highway fallback zones below — out of release.
#if DEBUG
import Foundation
import SrednaBGCore

/// Fills the History store with a curated, deterministic set of varied
/// `ZoneTraversalRecord`s so a developer can launch the app and browse realistic
/// scenarios — within-limit vs over-limit, every vehicle type, short and long
/// traversals, spread across several days — without driving every zone by hand.
///
/// This is the iOS counterpart to how Android's QA harness fills the emulator's
/// History DB (there, by replaying GPS through zones). Rather than replay the
/// whole GPS pipeline, the seeder writes finalized records straight into
/// `HistoryStore`, computing the same sustained-min/max, running-average and
/// downsample stats the real `HistoryRecorder` would, so the History list and
/// the detail graph look exactly like recorded drives.
///
/// Triggered over the loopback debug server: `GET /history?action=seed[&count=N]`.
public enum HistorySeeder {

    /// One scripted traversal. `deltaFromLimitKmh` is added to the zone's
    /// vehicle-resolved limit to get the held average, so the over/under-limit
    /// mix holds regardless of which real zone (and limit) the scenario lands on
    /// — a negative delta stays green, a positive one flips the row red.
    private struct Scenario {
        let vehicle: VehicleType
        let dayOffset: Int
        let hour: Int
        let minute: Int
        let deltaFromLimitKmh: Double
        let durationSec: Int
    }

    /// Fixed script — deterministic so repeated seeds and store screenshots look
    /// identical. Covers all four vehicle types, both sides of the limit,
    /// short/long traversals, and a spread of days (today back to ~a month ago).
    private static let scenarios: [Scenario] = [
        Scenario(vehicle: .car, dayOffset: 0, hour: 8, minute: 12, deltaFromLimitKmh: -22, durationSec: 210),
        Scenario(vehicle: .car, dayOffset: 0, hour: 17, minute: 40, deltaFromLimitKmh: 9, durationSec: 240),
        Scenario(vehicle: .truck, dayOffset: 1, hour: 10, minute: 5, deltaFromLimitKmh: -12, durationSec: 300),
        Scenario(vehicle: .car, dayOffset: 1, hour: 19, minute: 22, deltaFromLimitKmh: -2, durationSec: 180),
        Scenario(vehicle: .bus, dayOffset: 3, hour: 7, minute: 33, deltaFromLimitKmh: 6, durationSec: 260),
        Scenario(vehicle: .motorcycle, dayOffset: 3, hour: 14, minute: 50, deltaFromLimitKmh: -8, durationSec: 150),
        Scenario(vehicle: .car, dayOffset: 5, hour: 9, minute: 18, deltaFromLimitKmh: -44, durationSec: 200),
        Scenario(vehicle: .truck, dayOffset: 8, hour: 12, minute: 47, deltaFromLimitKmh: 5, durationSec: 280),
        Scenario(vehicle: .car, dayOffset: 12, hour: 16, minute: 9, deltaFromLimitKmh: -16, durationSec: 220),
        Scenario(vehicle: .bus, dayOffset: 15, hour: 11, minute: 55, deltaFromLimitKmh: -8, durationSec: 240),
        Scenario(vehicle: .car, dayOffset: 20, hour: 18, minute: 3, deltaFromLimitKmh: 3, durationSec: 200),
        Scenario(vehicle: .motorcycle, dayOffset: 26, hour: 13, minute: 27, deltaFromLimitKmh: -12, durationSec: 160)
    ]

    /// Wipe the History store and refill it with `count` curated records. Returns
    /// the number inserted. `count` above the script length cycles the scenarios,
    /// pushing each extra pass ~a month further back so the day-grouped list keeps
    /// gaining older sections. `zones` should be the app's loaded zones so records
    /// reference real roads; falls back to a small built-in BG-highway set when
    /// none are loaded yet.
    @MainActor
    public static func seed(into store: HistoryStore, zones: [Zone], count: Int, nowMs: Int64) -> Int {
        let pool = zones.isEmpty ? fallbackZones : zones
        store.deleteAll()
        let total = max(1, count)
        var records = [ZoneTraversalRecord]()
        records.reserveCapacity(total)
        for i in 0..<total {
            let scenario = scenarios[i % scenarios.count]
            let cyclePush = (i / scenarios.count) * 30
            let zone = pool[i % pool.count]
            let limit = scenario.vehicle.limit(zone.speedLimits)
            let targetAvg = max(20, Double(limit) + scenario.deltaFromLimitKmh)

            let (entryMs, exitMs) = traversalBounds(
                nowMs: nowMs,
                dayOffset: scenario.dayOffset + cyclePush,
                hour: scenario.hour,
                minute: scenario.minute,
                durationSec: scenario.durationSec
            )

            let samples = makeSamples(
                entryMs: entryMs,
                durationSec: Int((exitMs - entryMs) / 1000),
                targetAvgKmh: targetAvg,
                seed: UInt64(bitPattern: Int64(i &* 2_654_435_761))
            )
            let avg = HistoryStats.runningAverage(samples).last?.speedKmh ?? targetAvg
            let extremes = HistoryStats.sustainedExtremes(samples)
            let stored = HistoryStats.downsample(samples)

            let record = ZoneTraversalRecord(
                id: "\(zone.id)-\(exitMs)",
                zoneId: zone.id,
                road: zone.road,
                roadLatin: zone.roadLatin,
                direction: zone.direction,
                speedLimitKmh: limit,
                vehicleType: scenario.vehicle.rawValue,
                entryTimeMs: entryMs,
                exitTimeMs: exitMs,
                avgSpeedKmh: avg,
                sustainedMinKmh: extremes.min,
                sustainedMaxKmh: extremes.max,
                isOverLimit: avg > Double(limit),
                distanceM: zone.distanceM,
                samples: ZoneTraversalRecord.encodeSamples(stored)
            )
            records.append(record)
        }
        // One save() for the whole batch — the per-row insert path issued N.
        store.insertAll(records)
        return records.count
    }

    /// Entry/exit epoch-ms for a traversal on the target local calendar day at the
    /// target time. Clamped so a traversal never lands in the future (matters for
    /// `dayOffset == 0` when "now" is earlier in the day than the scripted hour).
    private static func traversalBounds(
        nowMs: Int64,
        dayOffset: Int,
        hour: Int,
        minute: Int,
        durationSec: Int
    ) -> (entryMs: Int64, exitMs: Int64) {
        let cal = Calendar.current
        let now = Date(timeIntervalSince1970: Double(nowMs) / 1000)
        let startOfToday = cal.startOfDay(for: now)
        let day = cal.date(byAdding: .day, value: -dayOffset, to: startOfToday) ?? startOfToday
        let entryDate = cal.date(byAdding: .second, value: hour * 3600 + minute * 60, to: day) ?? day
        var entryMs = Int64(entryDate.timeIntervalSince1970 * 1000)
        var exitMs = entryMs + Int64(durationSec) * 1000
        if exitMs > nowMs {
            let shift = exitMs - nowMs + 60_000
            entryMs -= shift
            exitMs -= shift
        }
        return (entryMs, exitMs)
    }

    /// A plausible speed-over-time series at 1 Hz: an entry acceleration ramp, a
    /// gently undulating cruise with deterministic noise, and an exit
    /// deceleration — then shifted so the mean lands exactly on `targetAvgKmh`
    /// (uniform 1 s spacing makes the arithmetic mean track the time-weighted one,
    /// so the stored running average comes out on the intended side of the limit).
    private static func makeSamples(
        entryMs: Int64,
        durationSec: Int,
        targetAvgKmh: Double,
        seed: UInt64
    ) -> [SpeedSample] {
        var rng = LCG(seed: seed)
        let n = max(8, durationSec)
        let entryRamp = max(1, min(15, n / 4))
        let exitRamp = max(1, min(10, n / 5))
        var raw = [Double](repeating: 0, count: n)
        for i in 0..<n {
            var v = targetAvgKmh
            if i < entryRamp {
                let f = Double(i) / Double(entryRamp)
                v -= (targetAvgKmh * 0.18) * (1 - f)
            }
            if i >= n - exitRamp {
                let f = Double(n - i) / Double(exitRamp)
                v -= (targetAvgKmh * 0.12) * (1 - f)
            }
            v += sin(Double(i) / 18.0) * 3.5
            v += (rng.nextUnit() - 0.5) * 5.0
            raw[i] = max(5, v)
        }
        let mean = raw.reduce(0, +) / Double(n)
        let offset = targetAvgKmh - mean
        var samples = [SpeedSample]()
        samples.reserveCapacity(n)
        for i in 0..<n {
            samples.append(
                SpeedSample(timestampMs: entryMs + Int64(i) * 1000, speedKmh: max(5, raw[i] + offset))
            )
        }
        return samples
    }

    /// Representative BG average-speed zones for the case where the app hasn't
    /// loaded `zones.json` yet. Records are denormalized, so only the id / road /
    /// direction / limits / distance are used — geometry is placeholder.
    private static let fallbackZones: [Zone] = [
        demoZone(id: "trakiya-a1-demo", road: "А1 Тракия", roadLatin: "A1 Trakiya",
                 direction: "EAST", car: 140, truck: 100, distanceM: 23_800),
        demoZone(id: "hemus-a2-demo", road: "А2 Хемус", roadLatin: "A2 Hemus",
                 direction: "WEST", car: 140, truck: 100, distanceM: 18_400),
        demoZone(id: "struma-a3-demo", road: "А3 Струма", roadLatin: "A3 Struma",
                 direction: "SOUTH", car: 140, truck: 100, distanceM: 12_600),
        demoZone(id: "topli-dol-demo", road: "Тунел Топли дол", roadLatin: "Topli Dol Tunnel",
                 direction: "NORTH", car: 100, truck: 80, distanceM: 3_100),
        demoZone(id: "cherni-vrah-demo", road: "бул. Черни връх", roadLatin: "Cherni Vrah Blvd",
                 direction: "SOUTH", car: 90, truck: 70, distanceM: 2_400)
    ]

    private static func demoZone(
        id: String,
        road: String,
        roadLatin: String,
        direction: String,
        car: Int,
        truck: Int,
        distanceM: Int
    ) -> Zone {
        Zone(
            id: id,
            road: road,
            roadLatin: roadLatin,
            direction: direction,
            description: road,
            start: ZoneEndpoint(lat: 42.7, lng: 25.3),
            end: ZoneEndpoint(lat: 42.7, lng: 25.5),
            distanceM: distanceM,
            speedLimits: SpeedLimits(car: car, truck: truck, bus: truck, motorcycle: nil),
            centerline: [[25.3, 42.7], [25.5, 42.7]],
            source: "debug-seed",
            lastVerified: "2026-01-01"
        )
    }

    /// Small deterministic PRNG so the seeded data (and any screenshots taken from
    /// it) reproduce exactly. Not for cryptography.
    private struct LCG {
        private var state: UInt64
        init(seed: UInt64) { state = seed ^ 0x9E37_79B9_7F4A_7C15 }
        mutating func next() -> UInt64 {
            state = state &* 6_364_136_223_846_793_005 &+ 1_442_695_040_888_963_407
            return state
        }
        mutating func nextUnit() -> Double {
            Double(next() >> 11) / Double(1 << 53)
        }
    }
}
#endif
