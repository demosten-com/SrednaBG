// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import SwiftData
import SwiftUI
import SrednaBGData

/// History tab: completed average-speed-zone traversals grouped by local
/// calendar day (most-recent day first, rows within a day most-recent first).
/// Mirrors Android's `TripHistoryScreen`. Reads reactively via `@Query` against
/// the `HistoryStore`'s container (attached with `.modelContainer` on the tab).
public struct HistoryScreen: View {

    /// Retention setting drives the "disabled" empty state.
    public let settings: SettingsStore

    @Query(sort: \ZoneTraversalRecord.exitTimeMs, order: .reverse)
    private var records: [ZoneTraversalRecord]

    public init(settings: SettingsStore) {
        self.settings = settings
    }

    private var recordingDisabled: Bool {
        HistoryRetention.fromSetting(settings.historyRetention) == .none
    }

    private var locale: Locale {
        L10n.locale(for: settings.appLanguage) ?? .current
    }

    public var body: some View {
        Group {
            if records.isEmpty {
                emptyState
            } else {
                list
            }
        }
        .navigationTitle(L10n.navHistory)
    }

    private var list: some View {
        List {
            ForEach(groupedByDay, id: \.day) { group in
                Section(HistoryFormat.historyDay(group.dayMs, locale: locale)) {
                    ForEach(group.records) { record in
                        NavigationLink {
                            HistoryDetailView(record: record, locale: locale)
                        } label: {
                            HistoryRow(record: record, locale: locale)
                        }
                        .listRowBackground(
                            historyVerdictColor(isOverLimit: record.isOverLimit).opacity(0.15)
                        )
                    }
                }
            }
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label(
                recordingDisabled ? L10n.historyDisabledTitle : L10n.historyEmptyTitle,
                systemImage: recordingDisabled ? "clock.badge.xmark" : "clock.arrow.circlepath"
            )
        } description: {
            Text(recordingDisabled ? L10n.historyDisabledBody : L10n.historyEmptyBody)
        }
    }

    // Group the (globally exit-desc-sorted) records by local calendar day.
    private struct DayGroup {
        let day: Date
        let dayMs: Int64
        let records: [ZoneTraversalRecord]
    }

    private var groupedByDay: [DayGroup] {
        var order: [Date] = []
        var buckets: [Date: [ZoneTraversalRecord]] = [:]
        for record in records {
            let day = HistoryFormat.day(record.exitTimeMs)
            if buckets[day] == nil {
                buckets[day] = []
                order.append(day)
            }
            buckets[day]?.append(record)
        }
        return order.map { day in
            DayGroup(
                day: day,
                dayMs: Int64(day.timeIntervalSince1970 * 1000),
                records: buckets[day] ?? []
            )
        }
    }
}

/// A single History row, echoing the in-zone chip's visual language: road +
/// exit time on the left, the posted-limit round badge (white fill, red border,
/// not tinted by verdict), and the driver's average tinted green/red.
private struct HistoryRow: View {
    let record: ZoneTraversalRecord
    let locale: Locale

    /// Exit time, plus the compass direction when it's a known value
    /// (e.g. "14:32 · East") so both directions of a zone are distinguishable.
    private var subtitle: String {
        let time = HistoryFormat.historyTime(record.exitTimeMs, locale: locale)
        if let direction = L10n.historyDirectionLabel(record.direction) {
            return "\(time) · \(direction)"
        }
        return time
    }

    var body: some View {
        let color = historyVerdictColor(isOverLimit: record.isOverLimit)
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(record.roadLatin ?? record.road)
                    .font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            LimitBadge(limit: record.speedLimitKmh, size: 44)
            VStack(alignment: .trailing, spacing: 2) {
                Text(HistoryFormat.speedOrDash(record.avgSpeedKmh))
                    .font(.title2.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(color)
                Text(L10n.avgSpeedLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
