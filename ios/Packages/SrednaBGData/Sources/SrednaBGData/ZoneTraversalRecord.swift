// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation
import SwiftData
import SrednaBGCore

/// A completed average-speed-zone traversal, persisted for the History tab.
///
/// Fields are **denormalized** on purpose: the zone's road / direction / limit
/// and the driver's speeds are all copied in, so a record survives the source
/// zone being edited, re-numbered, or deleted by a later data sync. The captured
/// speed-over-time series lives in `samples` as encoded JSON (`[SpeedSample]`),
/// downsampled to ≤500 points before storage.
///
/// Mirrors Android's `ZoneTraversalEntity` (Room). SwiftData rather than the
/// JSON-file `ZoneStore` because history is append-heavy, date-queried, growing,
/// and carries a per-record blob — the shape SwiftData fits.
@Model
public final class ZoneTraversalRecord {
    /// Stable identity. Uses the exit timestamp + zone id so a re-inserted
    /// identical record (unexpected) collapses rather than duplicating.
    @Attribute(.unique) public var id: String
    public var zoneId: String
    public var road: String
    public var roadLatin: String?
    public var direction: String
    public var speedLimitKmh: Int
    public var vehicleType: String
    public var entryTimeMs: Int64
    public var exitTimeMs: Int64
    public var avgSpeedKmh: Double?
    public var sustainedMinKmh: Double
    public var sustainedMaxKmh: Double
    public var isOverLimit: Bool
    public var distanceM: Int
    /// JSON-encoded `[SpeedSample]` (downsampled). Decoded via `speedSamples`.
    public var samples: Data

    public init(
        id: String,
        zoneId: String,
        road: String,
        roadLatin: String?,
        direction: String,
        speedLimitKmh: Int,
        vehicleType: String,
        entryTimeMs: Int64,
        exitTimeMs: Int64,
        avgSpeedKmh: Double?,
        sustainedMinKmh: Double,
        sustainedMaxKmh: Double,
        isOverLimit: Bool,
        distanceM: Int,
        samples: Data
    ) {
        self.id = id
        self.zoneId = zoneId
        self.road = road
        self.roadLatin = roadLatin
        self.direction = direction
        self.speedLimitKmh = speedLimitKmh
        self.vehicleType = vehicleType
        self.entryTimeMs = entryTimeMs
        self.exitTimeMs = exitTimeMs
        self.avgSpeedKmh = avgSpeedKmh
        self.sustainedMinKmh = sustainedMinKmh
        self.sustainedMaxKmh = sustainedMaxKmh
        self.isOverLimit = isOverLimit
        self.distanceM = distanceM
        self.samples = samples
    }
}

public extension ZoneTraversalRecord {
    /// Decode the stored speed-over-time series (empty on malformed/blank).
    var speedSamples: [SpeedSample] {
        guard !samples.isEmpty else { return [] }
        return (try? JSONDecoder().decode([SpeedSample].self, from: samples)) ?? []
    }

    /// Encode a captured series into the `samples` column payload.
    ///
    /// Casing note: `JSONEncoder` defaults produce **camelCase** keys
    /// (`timestampMs` / `speedKmh`). Android serializes the same `SpeedSample`
    /// through its shared `Gson` (`LOWER_CASE_WITH_UNDERSCORES`), yielding
    /// **snake_case** (`timestamp_ms` / `speed_kmh`). Each platform round-trips
    /// its own blob, so this is not a runtime bug — but a future cross-platform
    /// history import/export must reconcile the casing. Kept intentionally.
    static func encodeSamples(_ series: [SpeedSample]) -> Data {
        (try? JSONEncoder().encode(series)) ?? Data()
    }
}
