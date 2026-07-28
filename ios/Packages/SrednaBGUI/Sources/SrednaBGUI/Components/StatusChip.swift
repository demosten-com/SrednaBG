// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore

/// A whole-km/h speed for the HUD, or the "--" placeholder when there is no
/// value to show (no fix yet, or a non-finite one). Shared by `StatusChip` and
/// `UnmeasuredChip` so the two chips can never round or blank differently.
private func formatSpeed(_ value: Double?) -> String {
    guard let value, value.isFinite else { return "--" }
    return String(Int(value.rounded()))
}

/// In-zone HUD strip used by both `HomeScreen` and `ZoneMapScreen`.
/// Shows the four data-points the driver needs at a glance: average,
/// current, limit badge, and distance remaining.
public struct StatusChip: View {
    public let inZone: ZoneState.InZone
    public let currentSpeedKmh: Double?
    /// Vehicle-type-resolved limit — the engine's over-limit verdict uses it,
    /// so the badge must show the same number, not the car default.
    public let limitKmh: Int

    public init(inZone: ZoneState.InZone, currentSpeedKmh: Double?, limitKmh: Int) {
        self.inZone = inZone
        self.currentSpeedKmh = currentSpeedKmh
        self.limitKmh = limitKmh
    }

    public var body: some View {
        let color = zoneStatusColor(state: inZone, currentSpeedKmh: currentSpeedKmh)
        let swiftColor = statusSwiftUIColor(color)
        let shape = RoundedRectangle(cornerRadius: 12)
        HStack(alignment: .center, spacing: 0) {
            VStack(alignment: .center, spacing: 2) {
                Text(formatSpeed(inZone.avgSpeed))
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .foregroundStyle(swiftColor)
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(L10n.avgSpeedLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 12)
            VStack(alignment: .center, spacing: 2) {
                Text(formatSpeed(currentSpeedKmh))
                    .font(.title3.weight(.semibold))
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(L10n.currentSpeedLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            Spacer(minLength: 12)
            LimitBadge(limit: limitKmh)
            Spacer(minLength: 12)
            VStack(alignment: .center, spacing: 2) {
                Text(String(format: "%.1f km", locale: Locale(identifier: "en_US_POSIX"), inZone.distanceRemaining / 1000))
                    .font(.callout.weight(.bold))
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(L10n.remaining)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(shape.fill(.regularMaterial))
        .background(shape.fill(Color.white.opacity(0.55)))
        .overlay(shape.fill(swiftColor.opacity(0.18)))
        .overlay(shape.strokeBorder(swiftColor.opacity(0.65), lineWidth: 1.5))
        .clipShape(shape)
        .shadow(color: .black.opacity(0.18), radius: 6, x: 0, y: 2)
    }
}

/// HUD strip for a zone we're inside but never saw entered. Shows the road's own
/// facts — the limit badge and the distance left — plus the live speed, and
/// nothing derived from timing: no average, no max-for-remainder, no progress.
/// Neutral rather than the green/amber/red traffic light, because that palette
/// *is* a verdict and here we are declining to give one.
///
/// See `ZoneDetector.startWitnessArcM`.
public struct UnmeasuredChip: View {
    public let unmeasured: ZoneState.Unmeasured
    public let currentSpeedKmh: Double?
    public let limitKmh: Int

    public init(unmeasured: ZoneState.Unmeasured, currentSpeedKmh: Double?, limitKmh: Int) {
        self.unmeasured = unmeasured
        self.currentSpeedKmh = currentSpeedKmh
        self.limitKmh = limitKmh
    }

    public var body: some View {
        let neutral = statusSwiftUIColor(zoneColorNeutral)
        let shape = RoundedRectangle(cornerRadius: 12)
        HStack(alignment: .center, spacing: 0) {
            VStack(alignment: .center, spacing: 2) {
                Text(formatSpeed(currentSpeedKmh))
                    .font(.system(size: 34, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Text(L10n.currentSpeedLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 12)
            LimitBadge(limit: limitKmh)
            Spacer(minLength: 12)
            VStack(alignment: .center, spacing: 2) {
                Text(String(format: "%.1f km", locale: Locale(identifier: "en_US_POSIX"),
                            unmeasured.distanceRemaining / 1000))
                    .font(.callout.weight(.bold))
                    .monospacedDigit()
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(L10n.statusUnmeasured)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(neutral)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(shape.fill(.regularMaterial))
        .background(shape.fill(Color.white.opacity(0.55)))
        .overlay(shape.fill(neutral.opacity(0.18)))
        .overlay(shape.strokeBorder(neutral.opacity(0.65), lineWidth: 1.5))
        .clipShape(shape)
        .shadow(color: .black.opacity(0.18), radius: 6, x: 0, y: 2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("map-unmeasured-chip")
    }
}
