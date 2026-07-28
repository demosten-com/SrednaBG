// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCore

import Foundation

/// Stateful zone-tracking state machine. Mutating value type — embed inside
/// `ZoneTrackingService` (a `@MainActor @Observable` class) so the GPS-consumer
/// task mutates it without `await` per sample.
///
/// `update(_:vehicleType:)` honors the driver's selected vehicle type when
/// looking up the speed limit (Android's `ZoneDetector` matches this).
public struct ZoneDetector: Sendable {
    // Entry provenance. A traversal is only measurable if we watched the vehicle
    // cross the start line, so a confirmed candidate opens a full `inZone`
    // traversal when its *first* fix projected this close to the start of the
    // centerline, and `ZoneState.Unmeasured` otherwise. The reason we missed the
    // entry (app restart, permission granted mid-drive, tunnel, process death,
    // genuinely joining the road late) makes no difference to the driver:
    // untrustworthy is untrustworthy, and a partially-informed number is worse
    // than an honest "can't help".
    //
    // Proximity to `zone.start` cannot make this call — the A3 phantom's first
    // matching fix sat 270–460 m from it, inside the old 500 m entry buffer. Arc
    // position can: for a car genuinely approaching on the road, the first fix
    // that matches the zone at all projects to arc ~0, because a fix short of the
    // camera is still inside the on-road band and its projection clamps to the
    // polyline start.
    //
    // The value is measured, not guessed. Across all 72 bundled zones, the worst
    // first-match arc on a legitimate approach is 121 m at the 2 s near-zone
    // cadence and 148 m at the 5 s cold-start cadence — both at i3-02-north,
    // whose stored centerline opens with a 121 m segment running ~180 degrees
    // against the road (ISSUE-001, shared with i6-01-east and trakiya-03-east),
    // so an approaching car snaps to the far end of that jog rather than to
    // arc 0. 200 m clears the worst legitimate case by 1.35x and still sits under
    // the 268 m the observed A3 phantom projected to. Entry confirmation below
    // remains the primary anti-phantom defence; this constant only separates
    // "approached the camera" from "joined deep inside".
    //
    // Mirrors Android's `START_WITNESS_ARC_M`.
    public static let startWitnessArcM = 200.0

    // Declare the zone finished once within this straight-line distance of the
    // end — by here the end camera is in sight, but the average + remainder
    // guidance stayed live through almost the whole zone. Relies on the
    // centerline actually reaching `zone.end` (the scraper aligns it), so this
    // trips cleanly near the real end rather than hundreds of metres short.
    // Matches Android's `EXIT_DISTANCE_M`.
    public static let exitDistanceM = 100.0
    public static let stopSpeedKmh = 5.0
    public static let stopDurationMs: Int64 = 30_000
    public static let gpsDropoutMs: Int64 = 10_000

    // Off-road exit hysteresis. A single off-road fix is usually a transient
    // GPS/Kalman blip — the smoothed position lags the road on a bend (worse on
    // coarsely-sampled centerlines), or a momentary glitch (overpass, tunnel
    // mouth, urban canyon) throws one fix wide. Exiting on the first such fix
    // produces a spurious Exiting → InZone flap. So require the off-road
    // condition to persist this many consecutive fixes before declaring an exit;
    // a genuine off-ramp diverges steadily and trips it within a few seconds.
    // Mirrors Android's `OFF_ROAD_EXIT_GRACE_FIXES`.
    public static let offRoadExitGraceFixes = 3
    // …unless the fix is this far off the centerline, which is no blip but a
    // real departure (different road / GPS teleport) — exit immediately.
    public static let offRoadHardM = 1000.0

    // Entry confirmation — the mirror of `offRoadExitGraceFixes` on the way in.
    // A fix that merely clips the on-road band must not open a traversal: roads
    // that cross or run alongside a zone sit inside the band, on a course inside
    // `directionToleranceDeg`, for a few hundred metres. The A3 Струма motorway
    // passes within 15 m of the I-1 centerline for ~190 m at the Кочериново
    // interchange, which opened a full phantom traversal of the 10.6 km
    // i1-02-north zone for motorway traffic — reported from a real drive on both
    // platforms (2026-07-26): a 13–21 s "traversal" with an entry announcement
    // and a junk History record.
    //
    // So require the match to hold while the vehicle actually covers this much
    // ground ALONG the centerline before the zone opens. Genuine entries lose
    // nothing: the traversal is back-dated to the candidate's first fix, so only
    // the announcement waits, never the average. Mirrors Android.
    public static let entryConfirmDistanceM = 300.0
    // …but never more than this share of a zone, so a short zone stays enterable
    // (the shortest in the data is 2.3 km; this only binds below ~1.2 km).
    public static let entryConfirmMaxFraction = 0.25
    // …and over at least this many fixes, so one pair of far-apart fixes
    // (dropout, teleport, coarse simulated trace) can't clear the distance on
    // its own.
    public static let entryConfirmFixes = 2
    // Drop a half-confirmed candidate that goes quiet for this long — it is no
    // longer evidence of a continuous approach.
    public static let entryConfirmTimeoutMs: Int64 = 30_000

    // At a co-located camera pair one camera ends zone A and begins zone B, so
    // B's start sits on A's end (24 such pairs in the data, nearly all exactly
    // 0 m apart). Having just driven A to its end IS the continuous on-road
    // evidence the confirmation window exists to gather, so B skips it — keeping
    // the inZone(A) -> exiting(A) -> inZone(B) handover (and the chained
    // exit/entry announcement `AnnouncementPolicy` drives from it) intact.
    public static let colocatedCameraM = 250.0
    // How long the handover stays on offer after the exit. A's exit fires up to
    // `exitDistanceM` before the shared camera, and B only becomes the *nearest*
    // zone (so the only zone `findMatchingZone` will return) once we are past it
    // — a few fixes later, not the very next one. The geometric
    // `colocatedCameraM` test is what actually gates the bypass, so this window
    // can be generous.
    public static let colocatedHandoverMs: Int64 = 30_000

    /// The offer a just-exited zone leaves behind for a co-located successor: the
    /// camera we finished at (`fromZoneEnd`), the direction we were travelling as
    /// we finished (`headingDeg`, nil when the geometry was too short to read a
    /// bearing off), and the moment the offer lapses (`expiresAt`).
    ///
    /// One optional field rather than three loose ones, so the offer is armed and
    /// dropped atomically — a half-cleared handover (an end without its heading)
    /// would silently disable the direction guard in `continuesHandoverDirection`
    /// and let the opposite-carriageway sibling claim the bypass. Mirrors
    /// Android's `Handover`.
    private struct Handover {
        let fromZoneEnd: ZoneEndpoint
        let headingDeg: Double?
        let expiresAt: Int64
    }

    /// A zone that matched but has not yet earned a traversal. Accumulates the
    /// evidence `entryConfirmDistanceM` / `entryConfirmFixes` ask for, plus the
    /// entry-time and distance state to back-date the traversal with once the
    /// candidate is confirmed. Mirrors Android's `PendingEntry`.
    private struct PendingEntry {
        let zone: Zone
        let entryTime: Int64
        let entryArcM: Double

        var fixes = 1
        var lastTime: Int64
        var lastArcM: Double
        var distanceTraveled = 0.0

        /// Ground covered along the centerline since the candidate opened.
        var progressM: Double { lastArcM - entryArcM }

        /// Did we watch this vehicle cross the start line? Decides whether a
        /// confirmed candidate graduates into a measured traversal or into
        /// `ZoneState.Unmeasured`. See `startWitnessArcM`.
        var witnessedStart: Bool { entryArcM <= ZoneDetector.startWitnessArcM }

        init(zone: Zone, entryTime: Int64, entryArcM: Double) {
            self.zone = zone
            self.entryTime = entryTime
            self.entryArcM = entryArcM
            self.lastTime = entryTime
            self.lastArcM = entryArcM
        }
    }

    public private(set) var state: ZoneState = .outside

    // Orient every zone's centerline to run start → end once, up front, so all
    // the order-dependent geometry below (direction matching, polyline
    // projection, remaining distance, puck snapping) is correct regardless of
    // how the source stored the points. A centerline stored end-first — a real
    // server-data bug — would otherwise flip a zone's apparent direction. The
    // start/end endpoints are authoritative, so orienting to them makes the
    // engine immune to the bad point order. NOTE: orient at this detector
    // boundary, NOT as a stored/lazy property on `Zone` — `Zone` round-trips
    // through `Codable` and a derived stored field breaks (de)serialization
    // (matches the Kotlin note).
    private let zones: [Zone]
    // A zone's centerline is immutable after the orientation in `init`, so its
    // total arc length never changes — cache it per zone id rather than re-summing
    // the haversines on every 1 Hz fix in `polylineRemaining`. Mirrors Android.
    private let polylineLengthByZoneId: [String: Double]
    private var lastPoint: GpsPoint?
    private var activeZone: Zone?
    private var entryTime: Int64 = 0
    private var distanceTraveled: Double = 0
    private var totalStopDurationMs: Int64 = 0
    private var stopStartTime: Int64?
    private var offRoadStreak = 0

    // Lifecycle owner: `resetTrackingState()`. It is the single place that ends a
    // candidate's life for state-machine reasons, and every path that finishes
    // with a zone (`handleExiting`, `leaveUnmeasured`) goes through it.
    // `handleOutside` additionally drops the candidate the moment its evidence
    // stops being evidence — no zone matched, the matched zone is one we are
    // finishing, or it has just graduated into a traversal. Nothing else may
    // clear it.
    private var pendingEntry: PendingEntry?

    // Arc length of the previous in-zone fix, used to bridge distance across a
    // GPS dropout (see `handleInZone`).
    private var lastArcM: Double = 0

    // The offer a just-exited zone leaves for a co-located successor, live for
    // `colocatedHandoverMs` (see the direction guard in `handleOutside`).
    private var handover: Handover?

    public init(zones: [Zone]) {
        let oriented = zones.map { $0.with(centerline: orientCenterlineToStart($0.centerline, $0.start)) }
        self.zones = oriented
        self.polylineLengthByZoneId = Dictionary(
            oriented.map { ($0.id, polylineLengthMeters($0.centerline)) },
            uniquingKeysWith: { first, _ in first }
        )
    }

    @discardableResult
    public mutating func update(_ point: GpsPoint, vehicleType: VehicleType = .car) -> ZoneState {
        let newState: ZoneState
        switch state {
        case .outside: newState = handleOutside(point, vehicleType: vehicleType)
        case .inZone: newState = handleInZone(point, vehicleType: vehicleType)
        case .unmeasured: newState = handleUnmeasured(point)
        case .exiting: newState = handleExiting(point, vehicleType: vehicleType)
        }
        state = newState
        lastPoint = point
        return newState
    }

    public mutating func reset() {
        state = .outside
        lastPoint = nil
        activeZone = nil
        entryTime = 0
        distanceTraveled = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
        pendingEntry = nil
        lastArcM = 0
        handover = nil
    }

    private mutating func handleOutside(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        // Past its window the offer is dead — drop it rather than let a later fix
        // find it still sitting there.
        let offer = handover.flatMap { point.timestamp <= $0.expiresAt ? $0 : nil }
        if offer == nil { handover = nil }

        guard let zone = RoadMatcher.findMatchingZone(point, zones) else {
            pendingEntry = nil
            return .outside
        }
        let distToEnd = RoadMatcher.distanceToZoneEnd(point, zone)
        let arcM = arcLengthOnPolyline(point.lat, point.lng, zone.centerline)
        let remaining = remainingFromArc(zone, arcM)

        // We are finishing this zone, not joining it — never admit it again.
        // Gate on the polyline remainder (a point just past the end still in the
        // road-width band has ~0 remaining and must NOT re-enter the just-completed
        // zone), AND require it to be more than the exit distance from the end — a
        // centerline that hooks/overshoots at its tail can make
        // `arcLengthOnPolyline` snap a just-exited point back onto an earlier leg
        // and report a large `remaining`, briefly re-admitting the zone we are
        // exiting (an Exiting → InZone → Exiting flap on the final ~100 m; 11/72
        // zones flapped in qa/validate-zones.sh before it). Mirrors Android.
        if remaining <= Self.exitDistanceM || distToEnd <= Self.exitDistanceM {
            pendingEntry = nil
            return .outside
        }

        // Gather (or extend) the evidence that this is a real entry rather than a
        // neighbouring road clipping the band. A co-located handover already has
        // that evidence — we drove the previous zone to the camera this one
        // starts at — so it opens on the spot.
        let candidate = advancePendingEntry(point, zone, arcM: arcM)
        let handedOver = offer.map {
            haversineDistance(
                $0.fromZoneEnd.lat, $0.fromZoneEnd.lng, zone.start.lat, zone.start.lng
            ) <= Self.colocatedCameraM
                && continuesHandoverDirection($0, zone)
        } ?? false
        if !handedOver && !isConfirmed(candidate, zone) {
            return .outside
        }

        // Confirmed — but confirmation only proves we have been on this road, not
        // that we saw the driver pass the entry camera. A co-located handover is
        // witnessed by construction: driving the previous zone to its end *is*
        // crossing this one's start camera, whatever arc the first fix on the new
        // zone happened to land at.
        pendingEntry = nil
        handover = nil
        activeZone = zone
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
        lastArcM = arcM

        if !candidate.witnessedStart && !handedOver {
            // We are demonstrably inside the zone but never saw the entry, so
            // there is nothing trustworthy to measure. Show the road's facts and
            // stay quiet — see `ZoneState.Unmeasured`.
            entryTime = 0
            distanceTraveled = 0
            return .unmeasured(.init(zone: zone, distanceRemaining: remaining))
        }

        // Open the traversal back-dated to the candidate's *first* fix — its
        // timestamp and the ground covered since — so the confirmation window
        // costs announcement latency, never averaging accuracy. The averaging
        // denominator is always the whole zone: a tracked traversal is by
        // definition one we watched from the start. Use the polyline remainder —
        // not the straight-line `distToEnd` — so the legal-time budget matches the
        // road actually left to drive.
        entryTime = candidate.entryTime
        distanceTraveled = candidate.distanceTraveled

        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: Double(zone.distanceM),
            speedLimitKmh: vehicleType.limit(zone.speedLimits),
            distanceRemainingOverride: remaining
        )

        return .inZone(.init(
            zone: zone,
            entryTime: entryTime,
            distanceTraveled: distanceTraveled,
            speedStatus: status,
            distanceRemaining: remaining
        ))
    }

    private mutating func handleInZone(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        guard let zone = activeZone else { return .outside }

        // One walk of the centerline serves the distance integrator, the off-road
        // test and the remaining label below.
        let position = positionOnPolyline(point.lat, point.lng, zone.centerline)
        let arcM = position?.arcLengthM ?? lastArcM
        let centerlineDist = position?.distanceFromLineM ?? .greatestFiniteMagnitude

        distanceTraveled += travelSince(lastPoint, point, prevArcM: lastArcM, arcM: arcM)
        lastArcM = arcM

        updateStopTracking(point)

        // Accurate live distance to the zone end from the polyline projection —
        // drift-free, unlike the speed×time integrator above. Drives the exit
        // decision, the user-facing remaining label, and the remainder-speed math
        // so integrator drift (or unevenly-spaced simulated fixes) can't fake an
        // early "overshot the end" exit or collapse the remainder to 0 mid-zone.
        let remaining = remainingFromArc(zone, arcM)

        // Check exit conditions. Use the zone-appropriate on-road band (the
        // motorway override widens it to 150 m) — the same band entry matching
        // uses. A single off-road fix is treated as a transient blip: only exit
        // once it persists `offRoadExitGraceFixes` fixes, or immediately when the
        // fix is `offRoadHardM` past the road (a real departure, not a blip).
        if centerlineDist > RoadMatcher.maxOnRoadDistanceM(zone) {
            offRoadStreak += 1
            let farGone = centerlineDist > Self.offRoadHardM
            if farGone || offRoadStreak >= Self.offRoadExitGraceFixes {
                return exitZone(point, zone, vehicleType: vehicleType)
            }
            // Within the grace window — stay in the zone and keep guidance live.
        } else {
            offRoadStreak = 0
        }
        if RoadMatcher.distanceToZoneEnd(point, zone) < Self.exitDistanceM {
            return exitZone(point, zone, vehicleType: vehicleType)
        }
        // Reached the polyline end (e.g. zone end point offset from the road so the
        // haversine check above never trips). Position-based backstop, replacing
        // the old `distanceTraveled >= distanceM * 1.1` integrator check that
        // drifted on simulated/noisy traces.
        if remaining <= 0 {
            return exitZone(point, zone, vehicleType: vehicleType)
        }

        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: Double(zone.distanceM),
            speedLimitKmh: vehicleType.limit(zone.speedLimits),
            distanceRemainingOverride: remaining
        )

        return .inZone(.init(
            zone: zone,
            entryTime: entryTime,
            distanceTraveled: distanceTraveled,
            speedStatus: status,
            distanceRemaining: remaining
        ))
    }

    /// Inside a zone we never saw entered. The only job here is to notice when we
    /// leave it — deliberately no distance integration, no stop tracking, no
    /// `AverageSpeedCalc`: there is no measurement to keep, so there is nothing to
    /// accidentally surface.
    ///
    /// Every departure lands on `.outside` rather than `.exiting`, because there
    /// is no traversal to finalize. That is what keeps a mid-zone join out of
    /// History and out of the exit announcement, with no suppression logic needed
    /// at the consumer layers. Mirrors Android's `handleUnmeasured`.
    private mutating func handleUnmeasured(_ point: GpsPoint) -> ZoneState {
        guard let zone = activeZone else { return .outside }

        let position = positionOnPolyline(point.lat, point.lng, zone.centerline)
        let arcM = position?.arcLengthM ?? lastArcM
        let centerlineDist = position?.distanceFromLineM ?? .greatestFiniteMagnitude
        lastArcM = arcM

        // Same off-road hysteresis as `handleInZone`: a single wide fix is usually
        // a Kalman lag on a bend or a momentary glitch, not a departure.
        if centerlineDist > RoadMatcher.maxOnRoadDistanceM(zone) {
            offRoadStreak += 1
            let farGone = centerlineDist > Self.offRoadHardM
            if farGone || offRoadStreak >= Self.offRoadExitGraceFixes {
                return leaveUnmeasured()
            }
        } else {
            offRoadStreak = 0
        }

        let remaining = remainingFromArc(zone, arcM)
        if RoadMatcher.distanceToZoneEnd(point, zone) < Self.exitDistanceM || remaining <= 0 {
            return leaveUnmeasured()
        }

        return .unmeasured(.init(zone: zone, distanceRemaining: remaining))
    }

    // Leaving an unmeasured zone is not an exit — nothing was being measured, so
    // there is no traversal to finalize and no co-located handover to arm (a
    // successor zone earns its own entry the normal way). The next fix runs
    // through `handleOutside`, exactly as it does one fix after an `.exiting`.
    private mutating func leaveUnmeasured() -> ZoneState {
        resetTrackingState()
        return .outside
    }

    private mutating func handleExiting(_ point: GpsPoint, vehicleType: VehicleType) -> ZoneState {
        resetTrackingState()
        return handleOutside(point, vehicleType: vehicleType)
    }

    private mutating func exitZone(_ point: GpsPoint, _ zone: Zone, vehicleType: VehicleType) -> ZoneState {
        finalizeStop(currentTime: point.timestamp)
        let status = AverageSpeedCalc.calculate(
            entryTime: entryTime,
            currentTime: point.timestamp,
            stopDurationMs: totalStopDurationMs,
            distanceTraveled: distanceTraveled,
            zoneDistance: Double(zone.distanceM),
            speedLimitKmh: vehicleType.limit(zone.speedLimits)
        )
        // Offer a co-located successor the handover (see `colocatedCameraM`).
        // Tagged with the direction we finished this zone on so the opposite
        // carriageway can't claim it (see `continuesHandoverDirection`).
        //
        // `pendingEntry` is deliberately NOT cleared here — `resetTrackingState()`
        // owns that, and `handleExiting` calls it before the next `handleOutside`.
        handover = Handover(
            fromZoneEnd: zone.end,
            headingDeg: localPolylineBearing(
                zone.centerline,
                polylineLengthByZoneId[zone.id] ?? polylineLengthMeters(zone.centerline),
                RoadMatcher.localBearingWindowM
            ),
            expiresAt: point.timestamp + Self.colocatedHandoverMs
        )
        return .exiting(.init(zone: zone, finalAvgSpeed: status.avgSpeed))
    }

    /// Ground covered between `prev` and `point`, for the distance integrator.
    ///
    /// Normally speed × elapsed time (trapezoidal) rather than the haversine
    /// between consecutive lat/lng: position estimates lag the true vehicle
    /// position when the Kalman filter is sluggish, which would make distance —
    /// and therefore avg — read low, while reported GPS speed is Doppler-derived
    /// and tracks the truth far better.
    ///
    /// Across a GPS dropout (gap >= `gpsDropoutMs`) there are no samples to
    /// integrate, so fall back to how far the projection onto the centerline
    /// moved — from `prevArcM` to `arcM` — because the car demonstrably covered
    /// that ground. Dropping the gap outright (the old behaviour) left `elapsed`
    /// counting time the numerator never got credit for, deflating the reported
    /// average: a ~15 s dropout turned an ~87 km/h drive into a reported 24 km/h
    /// (real drive, 2026-07-26).
    ///
    /// Two integrators call this with the same `prev` but a different arc
    /// baseline: the active traversal passes `lastArcM`, the pending-entry buffer
    /// passes its candidate's own `lastArcM`. That works only because both walk
    /// the *same* fix stream — `lastPoint` is always the fix immediately before
    /// `point` for either of them — so pass the baseline in explicitly rather
    /// than reading a property, and the coupling stays visible at the call site.
    private func travelSince(
        _ prev: GpsPoint?,
        _ point: GpsPoint,
        prevArcM: Double,
        arcM: Double
    ) -> Double {
        guard let prev else { return 0 }
        let gap = point.timestamp - prev.timestamp
        if gap >= 1 && gap < Self.gpsDropoutMs {
            return ((prev.speed + point.speed) / 2.0 / 3.6) * (Double(gap) / 1000.0)
        }
        if gap >= Self.gpsDropoutMs {
            return max(arcM - prevArcM, 0)
        }
        return 0
    }

    /// Open or extend the candidate entry for `zone`, returning the live
    /// candidate. Restarts from this fix whenever the previous candidate was for
    /// a different zone, or went quiet past `entryConfirmTimeoutMs` — in both
    /// cases the earlier evidence no longer describes a continuous approach.
    private mutating func advancePendingEntry(
        _ point: GpsPoint,
        _ zone: Zone,
        arcM: Double
    ) -> PendingEntry {
        var candidate: PendingEntry
        if var open = pendingEntry,
           open.zone.id == zone.id,
           point.timestamp - open.lastTime <= Self.entryConfirmTimeoutMs {
            open.fixes += 1
            open.distanceTraveled += travelSince(lastPoint, point, prevArcM: open.lastArcM, arcM: arcM)
            open.lastArcM = arcM
            open.lastTime = point.timestamp
            candidate = open
        } else {
            candidate = PendingEntry(
                zone: zone,
                entryTime: point.timestamp,
                entryArcM: arcM
            )
        }
        pendingEntry = candidate
        return candidate
    }

    /// Does `zone` continue the direction we were travelling when `offer` was
    /// made? The proximity test alone is not enough: at a co-located
    /// camera the **opposite-carriageway sibling** also starts within
    /// `colocatedCameraM` — trakiya-03-west's start is 15 m from
    /// trakiya-03-east's end, which is also trakiya-04-east's start — so without
    /// this it can claim the bypass and open a *measured* traversal of the zone
    /// running back the way we came, on a single wrong-bearing fix. That is
    /// exactly what a stored centerline with an ISSUE-001 backwards start jog
    /// produces: trakiya-04-east opens with a 19 m segment bearing west, so one
    /// fix at the seam legitimately reads as westbound. Caught by
    /// `qa/colocated-zones.sh --all` (7/24 pairs). Mirrors Android.
    private func continuesHandoverDirection(_ offer: Handover, _ zone: Zone) -> Bool {
        guard let fromHeading = offer.headingDeg else { return true }
        guard let startHeading = localPolylineBearing(
            zone.centerline, 0, RoadMatcher.localBearingWindowM
        ) else { return true }
        return bearingDifference(fromHeading, startHeading) <= RoadMatcher.directionToleranceDeg
    }

    /// Has `candidate` earned a traversal? See `entryConfirmDistanceM`.
    private func isConfirmed(_ candidate: PendingEntry, _ zone: Zone) -> Bool {
        let required = min(
            Self.entryConfirmDistanceM,
            Double(zone.distanceM) * Self.entryConfirmMaxFraction
        )
        return candidate.fixes >= Self.entryConfirmFixes && candidate.progressM >= required
    }

    private mutating func updateStopTracking(_ point: GpsPoint) {
        if point.speed < Self.stopSpeedKmh {
            if stopStartTime == nil {
                stopStartTime = point.timestamp
            }
        } else {
            finalizeStop(currentTime: point.timestamp)
        }
    }

    private mutating func finalizeStop(currentTime: Int64) {
        guard let start = stopStartTime else { return }
        let duration = currentTime - start
        if duration >= Self.stopDurationMs {
            totalStopDurationMs += duration
        }
        stopStartTime = nil
    }

    // NB: deliberately does NOT clear `handover` — `handleExiting` calls this on
    // its way into `handleOutside`, which is exactly where the co-located
    // handover has to survive to be seen. That inversion is safe because the
    // offer is self-expiring (`Handover.expiresAt`, checked and dropped at the
    // top of `handleOutside`), so a stale one cannot outlive `colocatedHandoverMs`
    // even if a future caller resets tracking without exiting a zone. Arming it
    // stays the exclusive business of `exitZone`.
    private mutating func resetTrackingState() {
        activeZone = nil
        entryTime = 0
        distanceTraveled = 0
        totalStopDurationMs = 0
        stopStartTime = nil
        offRoadStreak = 0
        lastArcM = 0
        pendingEntry = nil
    }

    // Remaining road to the end for a point already projected onto the
    // centerline. Measured against the centerline's own arc length, not the
    // official `zone.distanceM`, so "remaining" is exactly 0 at the polyline end
    // regardless of any drift between the two (matches Android).
    //
    // Position-derived rather than integrator-derived, so it stays accurate
    // across GPS dropouts, mid-zone cold-starts, and simulated jumps.
    private func remainingFromArc(_ zone: Zone, _ arcM: Double) -> Double {
        let totalLength = polylineLengthByZoneId[zone.id] ?? polylineLengthMeters(zone.centerline)
        return max(totalLength - arcM, 0.0)
    }
}
