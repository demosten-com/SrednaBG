// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if os(iOS)
import Foundation
@preconcurrency import ActivityKit
import SrednaBGCore

/// Lock Screen / Dynamic Island Live Activity for the current zone-tracking
/// state. The widget bundle (`ZoneActivityWidget`) lives in the UI package
/// and reads `ZoneActivityAttributes.ContentState` from this manager.
///
/// We deliberately throttle updates to ≤1/second to stay within iOS's Live
/// Activity update budget — the system applies a hard cap and silently drops
/// excess pushes.
@available(iOS 16.2, *)
public actor LiveActivityManager {

    private var activity: Activity<ZoneActivityAttributes>?
    private var lastPushedAt: Date = .distantPast
    private static let minUpdateInterval: TimeInterval = 1.0

    public init() {}

    public func update(state: ZoneState) async {
        switch state {
        case .outside:
            await endIfActive()
        case .inZone(let inZone):
            let content = ZoneActivityAttributes.ContentState(
                roadName: inZone.zone.road,
                avgSpeedKmh: inZone.avgSpeed.map { Int($0) },
                distanceRemainingM: Int(inZone.distanceRemaining),
                isOverLimit: inZone.speedStatus.isOverLimit
            )
            await pushOrStart(content: content, road: inZone.zone.road)
        case .exiting:
            await endIfActive()
        }
    }

    private func pushOrStart(content: ZoneActivityAttributes.ContentState, road: String) async {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let now = Date()
        if let activity {
            guard now.timeIntervalSince(lastPushedAt) >= Self.minUpdateInterval else { return }
            await activity.update(.init(state: content, staleDate: nil))
            lastPushedAt = now
            return
        }
        do {
            let attributes = ZoneActivityAttributes(road: road)
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: content, staleDate: nil)
            )
            self.activity = activity
            lastPushedAt = now
        } catch {
            // Live Activity start can fail (system limit, missing entitlement);
            // we degrade gracefully — the in-app HomeScreen still shows status.
        }
    }

    public func endIfActive() async {
        guard let activity else { return }
        await activity.end(nil, dismissalPolicy: .immediate)
        self.activity = nil
    }
}

/// `ActivityAttributes` describing a zone-tracking session. Mirrors the
/// equivalent struct that the Widget extension binds to.
@available(iOS 16.2, *)
public struct ZoneActivityAttributes: ActivityAttributes {
    public typealias ContentState = State

    public let road: String

    public init(road: String) { self.road = road }

    public struct State: Codable, Hashable, Sendable {
        public let roadName: String
        public let avgSpeedKmh: Int?
        public let distanceRemainingM: Int
        public let isOverLimit: Bool

        public init(
            roadName: String,
            avgSpeedKmh: Int?,
            distanceRemainingM: Int,
            isOverLimit: Bool
        ) {
            self.roadName = roadName
            self.avgSpeedKmh = avgSpeedKmh
            self.distanceRemainingM = distanceRemainingM
            self.isOverLimit = isOverLimit
        }
    }
}
#endif
