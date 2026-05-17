// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGCore
import SrednaBGData
import SrednaBGTracking

/// Mirrors `HomeScreen.kt`: hero speed display + start/stop button. Reads
/// live state from `ZoneTrackingService` (an `@Observable @MainActor` class)
/// so SwiftUI re-renders on every transition.
public struct HomeScreen: View {

    @Bindable public var tracking: ZoneTrackingService
    public let settings: SettingsStore

    @Environment(\.scenePhase) private var scenePhase

    public init(tracking: ZoneTrackingService, settings: SettingsStore) {
        self.tracking = tracking
        self.settings = settings
    }

    public var body: some View {
        VStack(spacing: 16) {
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            startStopButton
        }
        .padding(16)
        // Pick up authorization changes the user made in Settings while the
        // app was suspended. SwiftUI delivers `.active` on initial appear too,
        // which doubles as the initial seed — `permission` was `.unknown`
        // before any system query.
        .task { await tracking.refreshPermission() }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await tracking.refreshPermission() }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if !tracking.isTracking, tracking.permission == .whenInUse || tracking.permission == .denied {
            permissionCard
        } else if !tracking.isTracking {
            notTrackingCard
        } else {
            switch tracking.zoneState {
            case .outside:
                outsideCard
            case .inZone(let inZone):
                inZoneCard(inZone)
            case .exiting(let exiting):
                exitingCard(exiting)
            }
        }
    }

    private var notTrackingCard: some View {
        VStack(spacing: 8) {
            Spacer()
            Text(L10n.statusNotTracking)
                .font(.title.weight(.bold))
            Text(L10n.tapToStartHint)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
        .accessibilityIdentifier("home-not-tracking-card")
    }

    private var permissionCard: some View {
        let isDenied = tracking.permission == .denied
        let title = isDenied ? L10n.permissionDeniedTitle : L10n.permissionAlwaysRequiredTitle
        let body = isDenied ? L10n.permissionDeniedBody : L10n.permissionAlwaysRequiredBody

        return VStack(alignment: .leading, spacing: 16) {
            Spacer(minLength: 0)
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "location.slash.fill")
                    .font(.title)
                    .foregroundStyle(Theme.statusRed)
                Text(title)
                    .font(.title3.weight(.bold))
            }
            Text(body)
                .font(.body)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            #if os(iOS)
            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                Label(L10n.permissionOpenSettings, systemImage: "gearshape")
                    .font(.headline)
                    .frame(maxWidth: .infinity, minHeight: 48)
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("home-permission-open-settings")
            #endif
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(24)
        .background(Theme.statusRed.opacity(0.10), in: RoundedRectangle(cornerRadius: 20))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("home-permission-card")
    }

    private var outsideCard: some View {
        VStack(spacing: 12) {
            Text(L10n.statusTrackingOutside)
                .font(.headline)
            Spacer()
            SpeedDisplay(
                value: tracking.currentPosition?.speed,
                label: L10n.currentSpeedLabel,
                statusColor: .accentColor
            )
            .accessibilityIdentifier("home-speed-display")
            Spacer()
            Text(String(format: L10n.zonesLoaded, tracking.zones.count))
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
        .accessibilityIdentifier("home-outside-card")
    }

    private func inZoneCard(_ inZone: ZoneState.InZone) -> some View {
        let statusColor = zoneStatusColor(state: inZone, currentSpeedKmh: tracking.currentPosition?.speed)
        let swiftColor = statusSwiftUIColor(statusColor)
        let statusText = inZone.speedStatus.isOverLimit ? L10n.statusOverLimit : L10n.statusWithinLimit

        return VStack(alignment: .leading, spacing: 12) {
            Text(String(format: L10n.statusInZone, inZone.zone.road))
                .font(.headline)

            Spacer()

            VStack(spacing: 8) {
                SpeedDisplay(
                    value: inZone.avgSpeed,
                    label: L10n.avgSpeedLabel,
                    statusColor: swiftColor
                )
                Text(String(format: L10n.statusNowSpeed, format(tracking.currentPosition?.speed)))
                    .font(.title3.weight(.semibold))
                    .monospacedDigit()
            }
            .frame(maxWidth: .infinity)

            Spacer()

            HStack {
                infoItem(label: L10n.speedLimit, value: String(inZone.zone.speedLimits.car))
                Spacer()
                infoItem(label: L10n.maxForRemainder,
                         value: String(settings.debugMaxSpeedOverride ?? Int(inZone.speedStatus.maxSpeedForRemainder)))
                Spacer()
                infoItem(label: L10n.remaining, value: String(format: "%.1f km", inZone.distanceRemaining / 1000))
            }

            Text(statusText)
                .font(.title3.weight(.bold))
                .foregroundStyle(swiftColor)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .padding(24)
        .background(swiftColor.opacity(0.15), in: RoundedRectangle(cornerRadius: 20))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("home-in-zone-card")
    }

    private func exitingCard(_ exiting: ZoneState.Exiting) -> some View {
        let isOver = (exiting.finalAvgSpeed ?? 0) > Double(exiting.zone.speedLimits.car)
        let color: Color = isOver ? Theme.statusRed : Theme.statusGreen
        return VStack(spacing: 12) {
            Text(String(format: L10n.statusExiting, exiting.zone.road))
                .font(.headline)
            Spacer()
            Text(String(format: L10n.finalAvgSpeed, format(exiting.finalAvgSpeed)))
                .font(.title.weight(.bold))
                .foregroundStyle(color)
            Spacer()
            Text(String(format: L10n.statusNowSpeed, format(tracking.currentPosition?.speed)))
                .font(.title3.weight(.semibold))
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .background(color.opacity(0.15), in: RoundedRectangle(cornerRadius: 20))
        .accessibilityIdentifier("home-exiting-card")
    }

    private var startStopButton: some View {
        let blocked = !tracking.isTracking
            && (tracking.permission == .denied || tracking.permission == .whenInUse)
        let label = blocked
            ? L10n.permissionTryAgain
            : (tracking.isTracking ? L10n.stopTracking : L10n.startTracking)
        let icon = blocked
            ? "arrow.clockwise"
            : (tracking.isTracking ? "stop.fill" : "play.fill")

        return Button {
            Task {
                if tracking.isTracking {
                    await tracking.stop()
                } else {
                    await tracking.start()
                }
            }
        } label: {
            Label(label, systemImage: icon)
                .font(.title3.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 56)
        }
        .buttonStyle(.borderedProminent)
        .tint(tracking.isTracking ? Theme.statusRed : .accentColor)
        .accessibilityIdentifier("home-start-stop")
    }

    private func infoItem(label: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.title3.weight(.bold))
                .monospacedDigit()
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func format(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "--" }
        return String(Int(value.rounded()))
    }
}
