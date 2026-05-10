// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if os(iOS)
import Foundation
@preconcurrency import ActivityKit
import SrednaBGCore

/// Lock Screen / Dynamic Island Live Activity for the current zone-tracking
/// session. Bound to `ZoneActivityAttributes`; the widget extension renders
/// `ContentState` updates pushed from this manager.
///
/// Lifecycle is **session-scoped**, not zone-scoped: the activity is created
/// when the user taps Start (foreground-only by Apple's rule — `Activity.request`
/// fails silently from the background) and ended only when the user stops
/// tracking. While the session is active we cycle the `phase`:
///   - `.tracking`     — no zone visited yet, minimal placeholder.
///   - `.inZone`       — live updates throttled to ≤1 / second.
///   - `.zoneComplete` — pushed once on zone exit; the greyed cached chip
///                       stays frozen on screen until the next zone-entry
///                       (or `sessionStop`) — saves the iOS background-update
///                       budget we'd otherwise burn outside zones.
@available(iOS 16.2, *)
public actor LiveActivityManager {

    private var activity: Activity<ZoneActivityAttributes>?
    private var lastPushedAt: Date = .distantPast
    /// The phase of the most recent successful push. Used to detect phase
    /// transitions (which bypass the throttle) and to suppress duplicate
    /// outside-zone pushes.
    private var lastPushedPhase: ZoneActivityPhase?
    /// Snapshot of the last `.inZone` content. Used to render the
    /// `.zoneComplete` greyed chip after exit.
    private var lastZoneContent: ZoneActivityAttributes.ContentState?

    private static let minUpdateInterval: TimeInterval = 1.0
    /// Time after which iOS dims the activity if no fresh content arrives.
    /// Only set on `.inZone` pushes — outside-zone phases pin `staleDate = nil`
    /// because the chip is intentionally frozen.
    private static let staleAfter: TimeInterval = 30

    public init() {}

    /// Create the Live Activity for a fresh tracking session. **Must be called
    /// from a foregrounded app** — `Activity.request` is rejected from the
    /// background. Any leftover activity from a prior process lifecycle is
    /// ended first so the session starts from a clean slate.
    public func sessionStart() async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }

        // Drain any leftovers — iOS persists Live Activities across app
        // launches, so without this we'd accumulate ghost chips.
        for stale in Activity<ZoneActivityAttributes>.activities {
            await stale.end(nil, dismissalPolicy: .immediate)
        }
        self.activity = nil
        self.lastZoneContent = nil
        self.lastPushedPhase = nil

        let placeholder = Self.trackingPlaceholder()
        do {
            let attrs = ZoneActivityAttributes(road: "SrednaBG")
            self.activity = try Activity.request(
                attributes: attrs,
                content: .init(state: placeholder, staleDate: nil)
            )
            self.lastPushedPhase = .tracking
            self.lastPushedAt = Date()
        } catch {
            // Live Activity start can fail (system limit, missing entitlement);
            // we degrade gracefully — the in-app HomeScreen still shows status.
        }
    }

    /// End the Live Activity. Called when tracking stops.
    public func sessionStop() async {
        await endIfActive()
        self.lastZoneContent = nil
        self.lastPushedPhase = nil
    }

    /// Push a content update for the current `ZoneState`. No-op if the activity
    /// hasn't been started yet (i.e., before `sessionStart`).
    public func update(state: ZoneState, currentSpeedKmh: Double?) async {
        guard activity != nil else { return }
        switch state {
        case .outside, .exiting:
            await pushOutsidePhase()
        case .inZone(let inZone):
            let content = Self.contentState(from: inZone, currentSpeedKmh: currentSpeedKmh)
            self.lastZoneContent = content
            await pushInZone(content: content)
        }
    }

    public func endIfActive() async {
        guard let activity else { return }
        await activity.end(nil, dismissalPolicy: .immediate)
        self.activity = nil
    }

    // MARK: - Internal push paths

    private func pushInZone(content: ZoneActivityAttributes.ContentState) async {
        guard let activity else { return }
        let now = Date()
        let phaseChanged = lastPushedPhase != .inZone
        if !phaseChanged && now.timeIntervalSince(lastPushedAt) < Self.minUpdateInterval {
            return
        }
        await activity.update(.init(
            state: content,
            staleDate: now.addingTimeInterval(Self.staleAfter)
        ))
        lastPushedAt = now
        lastPushedPhase = .inZone
    }

    /// Push at most ONCE per outside-phase transition. While outside, we don't
    /// burn the iOS background-update budget on a frozen chip.
    private func pushOutsidePhase() async {
        guard let activity else { return }
        let target: ZoneActivityPhase = lastZoneContent == nil ? .tracking : .zoneComplete
        guard lastPushedPhase != target else { return }
        let content: ZoneActivityAttributes.ContentState
        if let cached = lastZoneContent {
            content = Self.zoneComplete(from: cached)
        } else {
            content = Self.trackingPlaceholder()
        }
        await activity.update(.init(state: content, staleDate: nil))
        lastPushedAt = Date()
        lastPushedPhase = target
    }

    // MARK: - Pure projections (testable without ActivityKit runtime)

    /// Pure projection from `ZoneState.InZone` + the latest GPS speed to the
    /// payload the widget renders.
    public static func contentState(
        from inZone: ZoneState.InZone,
        currentSpeedKmh: Double?
    ) -> ZoneActivityAttributes.ContentState {
        ZoneActivityAttributes.ContentState(
            phase: .inZone,
            roadName: inZone.zone.road,
            avgSpeedKmh: roundedInt(inZone.avgSpeed),
            currentSpeedKmh: roundedInt(currentSpeedKmh),
            speedLimitKmh: inZone.zone.speedLimits.car,
            distanceTraveledM: max(0, Int(inZone.distanceTraveled.rounded())),
            zoneTotalM: max(1, inZone.zone.distanceM),
            distanceRemainingM: max(0, Int(inZone.distanceRemaining.rounded())),
            isOverLimit: inZone.speedStatus.isOverLimit,
            statusColorPacked: zoneStatusColor(state: inZone, currentSpeedKmh: currentSpeedKmh)
        )
    }

    /// Initial chip shown right after `sessionStart` when the user hasn't
    /// reached any zone yet. The widget renders it as a minimal "tracking"
    /// pill.
    public static func trackingPlaceholder() -> ZoneActivityAttributes.ContentState {
        ZoneActivityAttributes.ContentState(
            phase: .tracking,
            roadName: nil,
            avgSpeedKmh: nil,
            currentSpeedKmh: nil,
            speedLimitKmh: nil,
            distanceTraveledM: 0,
            zoneTotalM: 0,
            distanceRemainingM: 0,
            isOverLimit: false,
            statusColorPacked: 0
        )
    }

    /// Greyed-out cached chip pushed once when the user exits a zone. Holds
    /// the last in-zone snapshot so the user sees a recap (road, avg, limit)
    /// until the next zone-entry — but no further updates burn the budget.
    public static func zoneComplete(
        from cached: ZoneActivityAttributes.ContentState
    ) -> ZoneActivityAttributes.ContentState {
        ZoneActivityAttributes.ContentState(
            phase: .zoneComplete,
            roadName: cached.roadName,
            avgSpeedKmh: cached.avgSpeedKmh,
            currentSpeedKmh: nil,
            speedLimitKmh: cached.speedLimitKmh,
            distanceTraveledM: cached.zoneTotalM,
            zoneTotalM: cached.zoneTotalM,
            distanceRemainingM: 0,
            isOverLimit: cached.isOverLimit,
            statusColorPacked: cached.statusColorPacked
        )
    }

    private static func roundedInt(_ value: Double?) -> Int? {
        guard let value, value.isFinite else { return nil }
        return Int(value.rounded())
    }
}

/// Phase of a tracking session as reflected in the Live Activity.
@available(iOS 16.2, *)
public enum ZoneActivityPhase: String, Codable, Hashable, Sendable {
    /// Session active, no zone visited yet — minimal placeholder pill.
    case tracking
    /// Currently inside a zone — live updates throttled to ≤1 / second.
    case inZone
    /// Zone just ended — frozen greyed cached chip until the next zone-entry.
    case zoneComplete
}

/// `ActivityAttributes` describing a zone-tracking session. The fixed `road`
/// is reserved for compatibility but not rendered — the widget reads from
/// `ContentState.roadName`, which can change as the user enters successive
/// zones in a single session.
@available(iOS 16.2, *)
public struct ZoneActivityAttributes: ActivityAttributes {
    public typealias ContentState = State

    public let road: String

    public init(road: String) { self.road = road }

    public struct State: Codable, Hashable, Sendable {
        public let phase: ZoneActivityPhase
        public let roadName: String?
        public let avgSpeedKmh: Int?
        public let currentSpeedKmh: Int?
        public let speedLimitKmh: Int?
        public let distanceTraveledM: Int
        public let zoneTotalM: Int
        public let distanceRemainingM: Int
        public let isOverLimit: Bool
        /// 0xAARRGGBB packed status color from `zoneStatusColor(state:currentSpeedKmh:)`.
        /// The widget extension renders this via `SrednaBGTheme.statusSwiftUIColor(_:)`.
        public let statusColorPacked: Int32

        public init(
            phase: ZoneActivityPhase,
            roadName: String?,
            avgSpeedKmh: Int?,
            currentSpeedKmh: Int?,
            speedLimitKmh: Int?,
            distanceTraveledM: Int,
            zoneTotalM: Int,
            distanceRemainingM: Int,
            isOverLimit: Bool,
            statusColorPacked: Int32
        ) {
            self.phase = phase
            self.roadName = roadName
            self.avgSpeedKmh = avgSpeedKmh
            self.currentSpeedKmh = currentSpeedKmh
            self.speedLimitKmh = speedLimitKmh
            self.distanceTraveledM = distanceTraveledM
            self.zoneTotalM = zoneTotalM
            self.distanceRemainingM = distanceRemainingM
            self.isOverLimit = isOverLimit
            self.statusColorPacked = statusColorPacked
        }
    }
}
#endif
