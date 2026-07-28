// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import os
import SrednaBGCore
import SrednaBGData

/// Captures completed average-speed-zone traversals for the History tab.
/// Injected into `ZoneTrackingService` and driven from `process(point:)` — the
/// same site as the announcement pipeline — so history mirrors what was (or
/// would have been) announced.
///
/// Buffering (append while `.inZone`, finalize on the exit transition) runs
/// entirely on the caller's isolation (`@MainActor`, the location callback), so
/// the buffer needs no locking. Only the store write hops to a detached task.
///
/// Mirrors Android's `HistoryRecorder`.
@MainActor
public final class HistoryRecorder {

    /// Mirror of the retention setting so the hot path never reads the store.
    /// Seeded from the *default's* verdict; the app updates it from the
    /// retention observer. When `false`, the recorder both drops any open
    /// buffer and records nothing (a separate observer purges existing
    /// history).
    public var recordingEnabled: Bool =
        HistoryRetention.fromSetting(SettingsDefaults.historyRetention).isRecording

    private let store: HistoryStore
    /// Injected clock for the record `id`; defaults to the fix timestamp so it
    /// stays deterministic under the QA harness's simulated timeline.
    private var capture: Capture?

    private let log = Logger(subsystem: QALog.subsystem, category: "SrednaBG.History")

    public init(store: HistoryStore) {
        self.store = store
    }

    /// The in-progress traversal. Only touched on the caller's actor.
    private struct Capture {
        let zone: Zone
        let entryTimeMs: Int64
        var samples: [SpeedSample]
    }

    /// - Parameters:
    ///   - point: the filtered fix that produced `next`.
    ///   - previous / next: the zone-state transition.
    ///   - vehicleType: the driver's current vehicle-type setting.
    ///   - limitKmh: the vehicle-type-resolved limit for `next`'s zone, used
    ///     for the stored over-limit verdict (matches the exit-chip verdict).
    public func onZoneStateChanged(
        point: GpsPoint,
        previous: ZoneState,
        next: ZoneState,
        vehicleType: VehicleType,
        limitKmh: Int
    ) {
        guard recordingEnabled else {
            // Drop any buffer opened before recording was turned off mid-zone.
            capture = nil
            return
        }
        switch next {
        case .inZone(let inZone):
            if capture == nil || capture?.zone.id != inZone.zone.id {
                // Starting a fresh traversal. A still-open buffer for a
                // different zone means we jumped zones without an `.exiting`
                // (unexpected — the engine steps through `.exiting` even at
                // co-located cameras); drop it rather than mis-attribute it.
                if let open = capture {
                    log.warning("dropping stale buffer for \(open.zone.id, privacy: .public); entered \(inZone.zone.id, privacy: .public)")
                }
                capture = Capture(zone: inZone.zone, entryTimeMs: inZone.entryTime, samples: [])
            }
            capture?.samples.append(SpeedSample(timestampMs: point.timestamp, speedKmh: point.speed))

        case .exiting(let exiting):
            if let open = capture, open.zone.id == exiting.zone.id {
                finalize(open, exitTimeMs: point.timestamp, finalAvg: exiting.finalAvgSpeed,
                         vehicleType: vehicleType, limitKmh: limitKmh)
            }
            capture = nil

        case .unmeasured, .outside:
            // The exit is finalized on `.inZone -> .exiting`; by the time
            // `.outside` arrives the buffer is already closed. Clear defensively.
            //
            // `.unmeasured` is handled identically and records nothing: we never
            // saw the entry camera, so there is no traversal to attribute samples
            // to. It also cannot reach `.exiting` (it drops straight to
            // `.outside`), so no half-open buffer can ever be finalized from it —
            // which is exactly what keeps mid-zone joins out of History.
            capture = nil
        }
    }

    private func finalize(
        _ capture: Capture,
        exitTimeMs: Int64,
        finalAvg: Double?,
        vehicleType: VehicleType,
        limitKmh: Int
    ) {
        let durationMs = exitTimeMs - capture.entryTimeMs
        if durationMs < Self.transientExitWindowMs {
            // Transient blip / very short zone — the same window
            // `AnnouncementPolicy` uses to suppress the exit announcement, so
            // history matches the audio.
            log.debug("skipping transient traversal \(capture.zone.id, privacy: .public) (\(durationMs, privacy: .public)ms)")
            return
        }
        let samples = capture.samples
        let extremes = HistoryStats.sustainedExtremes(samples)
        let downsampled = HistoryStats.downsample(samples)
        let record = ZoneTraversalRecord(
            id: "\(capture.zone.id)-\(exitTimeMs)",
            zoneId: capture.zone.id,
            road: capture.zone.road,
            roadLatin: capture.zone.roadLatin,
            direction: capture.zone.direction,
            speedLimitKmh: limitKmh,
            vehicleType: vehicleType.rawValue,
            entryTimeMs: capture.entryTimeMs,
            exitTimeMs: exitTimeMs,
            avgSpeedKmh: finalAvg,
            sustainedMinKmh: extremes.min,
            sustainedMaxKmh: extremes.max,
            isOverLimit: finalAvg != nil && finalAvg! > Double(limitKmh),
            distanceM: capture.zone.distanceM,
            samples: ZoneTraversalRecord.encodeSamples(downsampled)
        )
        // Keep the DB write off the 1 Hz loop. `store` is `@MainActor`, so hop
        // back to it on a later turn instead of blocking the current fix.
        let store = self.store
        Task { @MainActor in
            store.insert(record)
        }
        log.info("recorded traversal \(record.zoneId, privacy: .public) over=\(record.isOverLimit, privacy: .public)")
    }

    /// Mirror `AnnouncementPolicy.transientExitWindowSec` (5 s) so a suppressed
    /// exit announcement and a skipped history record stay in lock-step.
    private static let transientExitWindowMs: Int64 = 5_000
}
