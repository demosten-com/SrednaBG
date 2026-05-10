// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGWidgets
//
// Lock-Screen + Dynamic Island Live Activity for an active section-control
// (секционен контрол) zone session. Bound to `ZoneActivityAttributes` from
// `SrednaBGTracking`; the host app's `LiveActivityManager` pushes
// `ContentState` updates as the driver progresses through a zone. Visual
// primitives (`LimitBadge`, status colors) come from the shared
// `SrednaBGTheme` module so the widget and the in-app HUD stay in lock-step.
//
// The activity has three phases (`state.phase`):
//   - `.tracking`     — minimal "awaiting zone" pill
//   - `.inZone`       — full StatusChip-style HUD with live progress
//   - `.zoneComplete` — greyed cached recap of the last zone

import ActivityKit
import SrednaBGTheme
import SrednaBGTracking
import SwiftUI
import WidgetKit

struct ZoneLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ZoneActivityAttributes.self) { context in
            ZoneLockScreenView(state: context.state)
                .activityBackgroundTint(Color.black.opacity(0.6))
                .activitySystemActionForegroundColor(Color.white)
        } dynamicIsland: { context in
            let state = context.state
            return DynamicIsland {
                // Order mirrors StatusChip: avg leads, limit trails. Progress
                // and remaining-km stay on the bottom row — if we flipped
                // those, the rounded DI corner would clip the leading digits
                // of the distance ("13.8 km" → "3.8 km") instead of the
                // trailing "km" suffix, which is the more graceful loss.
                DynamicIslandExpandedRegion(.leading) {
                    ExpandedLeading(state: state)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    ExpandedTrailing(state: state)
                }
                DynamicIslandExpandedRegion(.center) {
                    ExpandedCenter(state: state)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottom(state: state)
                }
            } compactLeading: {
                CompactLeading(state: state)
            } compactTrailing: {
                CompactTrailing(state: state)
            } minimal: {
                MinimalView(state: state)
            }
            .keylineTint(keylineTint(for: state))
        }
    }

    private func keylineTint(for state: ZoneActivityAttributes.ContentState) -> Color {
        switch state.phase {
        case .inZone:       return statusSwiftUIColor(state.statusColorPacked)
        case .zoneComplete: return statusSwiftUIColor(state.statusColorPacked).opacity(0.5)
        case .tracking:     return .secondary
        }
    }
}

// MARK: - Lock Screen

struct ZoneLockScreenView: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            TrackingLockView()
        case .inZone:
            InZoneLockView(state: state)
        case .zoneComplete:
            ZoneCompleteLockView(state: state)
        }
    }
}

private struct TrackingLockView: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "location.fill")
                .font(.title3)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text("SrednaBG")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                Text("Awaiting zone")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }
}

private struct InZoneLockView: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        let tint = statusSwiftUIColor(state.statusColorPacked)
        VStack(alignment: .leading, spacing: 10) {
            Text(state.roadName ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            HStack(alignment: .center, spacing: 0) {
                StatCell(
                    value: formatSpeed(state.avgSpeedKmh),
                    label: "avg",
                    valueFont: .system(size: 30, weight: .bold, design: .rounded),
                    valueColor: tint
                )
                Spacer(minLength: 8)
                StatCell(
                    value: formatSpeed(state.currentSpeedKmh),
                    label: "now",
                    valueFont: .title3.weight(.semibold),
                    valueColor: .primary
                )
                Spacer(minLength: 8)
                LimitBadge(limit: state.speedLimitKmh ?? 0, size: 42)
                Spacer(minLength: 8)
                StatCell(
                    value: formatRemainingKm(state.distanceRemainingM),
                    label: "left",
                    valueFont: .callout.weight(.bold),
                    valueColor: .primary
                )
            }

            ProgressCapsule(progress: progress(for: state), tint: tint)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

private struct ZoneCompleteLockView: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(state.roadName ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            HStack(alignment: .center, spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(formatSpeed(state.avgSpeedKmh))
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                    Text("avg km/h")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                LimitBadge(limit: state.speedLimitKmh ?? 0, size: 38)
                    .opacity(0.55)
            }

            ProgressCapsule(progress: 1.0, tint: .secondary)

            HStack(spacing: 6) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Зоната завърши")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }
}

private struct StatCell: View {
    let value: String
    let label: String
    let valueFont: Font
    let valueColor: Color

    var body: some View {
        VStack(alignment: .center, spacing: 2) {
            Text(value)
                .font(valueFont)
                .foregroundStyle(valueColor)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}

// MARK: - Dynamic Island regions

private struct ExpandedLeading: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            Image(systemName: "location.fill")
                .font(.title3)
                .foregroundStyle(.secondary)
        case .inZone:
            VStack(alignment: .leading, spacing: 0) {
                Text(formatSpeed(state.avgSpeedKmh))
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(statusSwiftUIColor(state.statusColorPacked))
                Text("avg km/h")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        case .zoneComplete:
            VStack(alignment: .leading, spacing: 0) {
                Text(formatSpeed(state.avgSpeedKmh))
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
                Text("avg km/h")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct ExpandedTrailing: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            EmptyView()
        case .inZone:
            LimitBadge(limit: state.speedLimitKmh ?? 0, size: 44)
        case .zoneComplete:
            LimitBadge(limit: state.speedLimitKmh ?? 0, size: 44)
                .opacity(0.55)
        }
    }
}

private struct ExpandedCenter: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            VStack(spacing: 2) {
                Text("SrednaBG")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                Text("Awaiting zone")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        case .inZone, .zoneComplete:
            Text(state.roadName ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
    }
}

private struct ExpandedBottom: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            EmptyView()
        case .inZone:
            HStack(spacing: 8) {
                ProgressCapsule(
                    progress: progress(for: state),
                    tint: statusSwiftUIColor(state.statusColorPacked)
                )
                Text(formatRemainingKm(state.distanceRemainingM))
                    .font(.caption.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(.primary)
            }
        case .zoneComplete:
            HStack(spacing: 8) {
                ProgressCapsule(progress: 1.0, tint: .secondary)
                Image(systemName: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Зоната завърши")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
        }
    }
}

private struct CompactLeading: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            Image(systemName: "location.fill")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case .inZone:
            Text(formatSpeed(state.avgSpeedKmh))
                .font(.caption.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(statusSwiftUIColor(state.statusColorPacked))
        case .zoneComplete:
            Text(formatSpeed(state.avgSpeedKmh))
                .font(.caption.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }
    }
}

private struct CompactTrailing: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            Image(systemName: "ellipsis")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case .inZone:
            LimitBadge(limit: state.speedLimitKmh ?? 0, size: 22)
        case .zoneComplete:
            LimitBadge(limit: state.speedLimitKmh ?? 0, size: 22)
                .opacity(0.55)
        }
    }
}

private struct MinimalView: View {
    let state: ZoneActivityAttributes.ContentState

    var body: some View {
        switch state.phase {
        case .tracking:
            Image(systemName: "location.fill")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case .inZone:
            Text(formatSpeed(state.avgSpeedKmh))
                .font(.caption2.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(statusSwiftUIColor(state.statusColorPacked))
        case .zoneComplete:
            Image(systemName: "checkmark")
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
        }
    }
}

// MARK: - Building blocks

/// Capsule progress indicator. Rendered manually rather than `ProgressView`
/// because the system style is too thin on the Lock Screen and ignores tint
/// requests inside `ActivityConfiguration`.
struct ProgressCapsule: View {
    let progress: Double
    let tint: Color

    var body: some View {
        GeometryReader { geo in
            let clamped = min(max(progress, 0), 1)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.18))
                Capsule()
                    .fill(tint)
                    .frame(width: geo.size.width * clamped)
            }
        }
        .frame(height: 6)
    }
}

// MARK: - Helpers

/// Render an optional Int speed as either the integer or the dash placeholder
/// — matches the app's "keep the slot visible" rule for missing GPS values.
private func formatSpeed(_ value: Int?) -> String {
    value.map(String.init) ?? "--"
}

private func formatRemainingKm(_ meters: Int) -> String {
    String(format: "%.1f km", Double(meters) / 1000)
}

private func progress(for state: ZoneActivityAttributes.ContentState) -> Double {
    guard state.zoneTotalM > 0 else { return 0 }
    return Double(state.distanceTraveledM) / Double(state.zoneTotalM)
}
