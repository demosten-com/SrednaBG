// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftUI
import SrednaBGData
import SrednaBGTracking

/// Detail for one completed traversal: a stats card then a graph card, both
/// tinted by the verdict color (green within / red over, ~0.15 alpha over the
/// card surface). Mirrors Android's `HistoryDetailScreen`.
struct HistoryDetailView: View {
    let record: ZoneTraversalRecord
    let locale: Locale
    let tracking: ZoneTrackingService
    let mapSession: MapSessionStore
    let onShowOnMap: () -> Void

    private var verdictColor: Color {
        historyVerdictColor(isOverLimit: record.isOverLimit)
    }

    /// Disabled while tracking (live tracking owns the map) and when the
    /// record's zone no longer exists in the catalog (deleted by a sync).
    private var canShowOnMap: Bool {
        !tracking.isTracking && tracking.zones.contains { $0.id == record.zoneId }
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                statsCard
                graphCard
            }
            .padding(16)
        }
        .navigationTitle(record.roadLatin ?? record.road)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    mapSession.requestHighlight(
                        zoneId: record.zoneId,
                        isOverLimit: record.isOverLimit
                    )
                    mapSession.isFollowing = false
                    onShowOnMap()
                } label: {
                    Label(L10n.historyShowOnMap, systemImage: "map")
                }
                .disabled(!canShowOnMap)
                .accessibilityIdentifier("history-show-on-map")
            }
        }
    }

    private var statsCard: some View {
        verdictCard {
            VStack(spacing: 10) {
                if let direction = L10n.historyDirectionLabel(record.direction) {
                    statRow(L10n.historyDirection, direction)
                }
                statRow(L10n.historyEntered, HistoryFormat.historyDateTime(record.entryTimeMs, locale: locale))
                statRow(L10n.historyExited, HistoryFormat.historyDateTime(record.exitTimeMs, locale: locale))
                statRow(L10n.historyDuration, HistoryFormat.duration(fromMs: record.exitTimeMs - record.entryTimeMs))
                statRow(
                    L10n.historyYourAverage,
                    kmhValue(record.avgSpeedKmh),
                    valueColor: verdictColor,
                    emphasize: true
                )
                statRow(L10n.historyTopSpeed, kmhValue(record.sustainedMaxKmh))
                statRow(L10n.historyLowestSpeed, kmhValue(record.sustainedMinKmh))
                statRow(
                    record.isOverLimit ? L10n.statusOverLimit : L10n.statusWithinLimit,
                    kmhValue(Double(record.speedLimitKmh)),
                    valueColor: verdictColor
                )
            }
            .padding(16)
        }
    }

    private var graphCard: some View {
        verdictCard {
            VStack(alignment: .leading, spacing: 12) {
                Text(L10n.historyGraphTitle)
                    .font(.subheadline.weight(.semibold))
                SpeedGraph(
                    samples: record.speedSamples,
                    limitKmh: record.speedLimitKmh,
                    avgSpeedKmh: record.avgSpeedKmh
                )
                SpeedGraphLegend()
            }
            .padding(16)
        }
    }

    private func statRow(
        _ label: String,
        _ value: String,
        valueColor: Color = .primary,
        emphasize: Bool = false
    ) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(emphasize ? .title3.weight(.bold) : .body.weight(.medium))
                .foregroundStyle(valueColor)
                .monospacedDigit()
        }
    }

    /// `%@ km/h` with the value rounded, or `--` when nil (shared dash helper).
    private func kmhValue(_ value: Double?) -> String {
        String(format: L10n.historyKmhValue, HistoryFormat.speedOrDash(value))
    }

    @ViewBuilder
    private func verdictCard<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        content()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Self.cardSurface)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(verdictColor.opacity(0.15))
                    )
            )
    }

    /// Base card surface the verdict tint composites over — the grouped
    /// secondary background on iOS, a neutral fill elsewhere (macOS tests).
    private static var cardSurface: Color {
        #if os(iOS)
        Color(.secondarySystemGroupedBackground)
        #else
        Color.gray.opacity(0.12)
        #endif
    }
}
