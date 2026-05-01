// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGCarPlay

import Foundation
import SrednaBGCore

/// Pure-logic projection of `ZoneState` + current speed + vehicle type
/// into the strings the CarPlay overlay renders. macOS-testable —
/// mirrors what `StatusChip` / `SpeedDisplay` do in SwiftUI.
///
/// Kept separate from the UIView so the overlay can be driven by a
/// value-semantic model diff (cheap `Equatable` compare) and the UIKit
/// side re-renders only when the model actually changes.
public struct CarPlaySpeedOverlayModel: Equatable, Sendable {

    public enum Mode: Equatable, Sendable {
        case notTracking
        case outside
        case inZone
        case exiting
    }

    public let mode: Mode
    public let heroSpeedText: String      // hero number: avg speed in-zone; current outside; "--" when tracking and no fix
    public let heroSubtitle: String       // e.g. "avg" / "current" / the exiting recap title
    public let smallSpeedText: String?    // secondary readout — current speed when in-zone; otherwise nil
    public let smallSubtitle: String?     // e.g. "current" / nil
    public let limitText: String?         // "90" or nil
    public let limitSubtitle: String?     // "limit" or nil
    public let distanceText: String?      // "3.2 km" or nil
    public let distanceSubtitle: String?  // "remaining" or nil
    public let statusLabel: String        // "over limit" / "within limit" / "" / "tap phone to start"
    public let packedStatusColor: Int32   // feeds SrednaBGMapCore.statusUIColor at render time

    public static func from(
        isTracking: Bool,
        state: ZoneState,
        currentSpeedKmh: Double?,
        vehicleType: VehicleType,
        labels: CarPlayLabels
    ) -> Self {
        guard isTracking else {
            return Self(
                mode: .notTracking,
                heroSpeedText: Self.dash,
                heroSubtitle: labels.avgSpeedLabel,
                smallSpeedText: nil,
                smallSubtitle: nil,
                limitText: nil,
                limitSubtitle: nil,
                distanceText: nil,
                distanceSubtitle: nil,
                statusLabel: labels.tapToStartHint,
                packedStatusColor: 0
            )
        }

        switch state {
        case .outside:
            return Self(
                mode: .outside,
                heroSpeedText: Self.formatSpeed(currentSpeedKmh),
                heroSubtitle: labels.currentSpeedLabel,
                smallSpeedText: nil,
                smallSubtitle: nil,
                limitText: nil,
                limitSubtitle: nil,
                distanceText: nil,
                distanceSubtitle: nil,
                statusLabel: labels.trackingOutsideTitle,
                packedStatusColor: 0
            )

        case .inZone(let inZone):
            let limit = vehicleType.limit(inZone.zone.speedLimits)
            let packed = zoneStatusColor(state: inZone, currentSpeedKmh: currentSpeedKmh)
            let statusLabel = inZone.speedStatus.isOverLimit ? labels.overLimit : labels.withinLimit
            return Self(
                mode: .inZone,
                heroSpeedText: Self.formatSpeed(inZone.avgSpeed),
                heroSubtitle: labels.avgSpeedLabel,
                smallSpeedText: Self.formatSpeed(currentSpeedKmh),
                smallSubtitle: labels.currentSpeedLabel,
                limitText: String(limit),
                limitSubtitle: labels.speedLimit,
                distanceText: Self.formatDistance(inZone.distanceRemaining),
                distanceSubtitle: labels.remaining,
                statusLabel: statusLabel,
                packedStatusColor: packed
            )

        case .exiting(let exiting):
            let finalSpeed = Self.formatSpeed(exiting.finalAvgSpeed)
            let recap = String(format: labels.finalAvgSpeedFormat, finalSpeed)
            return Self(
                mode: .exiting,
                heroSpeedText: finalSpeed,
                heroSubtitle: labels.avgSpeedLabel,
                smallSpeedText: nil,
                smallSubtitle: nil,
                limitText: nil,
                limitSubtitle: nil,
                distanceText: nil,
                distanceSubtitle: nil,
                statusLabel: recap.isEmpty ? labels.zoneCompleteTitle : recap,
                packedStatusColor: 0
            )
        }
    }

    public init(
        mode: Mode,
        heroSpeedText: String,
        heroSubtitle: String,
        smallSpeedText: String?,
        smallSubtitle: String?,
        limitText: String?,
        limitSubtitle: String?,
        distanceText: String?,
        distanceSubtitle: String?,
        statusLabel: String,
        packedStatusColor: Int32
    ) {
        self.mode = mode
        self.heroSpeedText = heroSpeedText
        self.heroSubtitle = heroSubtitle
        self.smallSpeedText = smallSpeedText
        self.smallSubtitle = smallSubtitle
        self.limitText = limitText
        self.limitSubtitle = limitSubtitle
        self.distanceText = distanceText
        self.distanceSubtitle = distanceSubtitle
        self.statusLabel = statusLabel
        self.packedStatusColor = packedStatusColor
    }

    // MARK: - Formatting

    /// Memory: render nullable numerics as "--", keep slot visible (see
    /// `feedback_dash_placeholder.md`).
    public static let dash = "--"

    public static func formatSpeed(_ value: Double?) -> String {
        guard let value, value.isFinite else { return dash }
        return String(Int(value.rounded()))
    }

    public static func formatDistance(_ meters: Double) -> String {
        guard meters.isFinite, meters >= 0 else { return dash }
        let km = meters / 1000
        return String(format: "%.1f km", km)
    }
}
