// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Retention window for the History tab. `none` records nothing and purges
/// what's already stored; the others keep records younger than that many
/// months.
///
/// Mirrors Android's `HistoryRetention` enum (`data/HistoryRepository.kt`):
/// same string tokens, same `months` values (0/1/3/6), same `fromSetting`
/// unknown → default (`threeMonths`) fallback, and the same flat 30-day-month
/// pruning approximation so both platforms prune identically.
public enum HistoryRetention: String, Sendable, CaseIterable {
    case none = "none"
    case oneMonth = "1month"
    case threeMonths = "3months"
    case sixMonths = "6months"

    /// Number of months kept (`0` for `none`). Pruning drops records older than
    /// `now − months × APPROX_MONTH_MS`.
    public var months: Int {
        switch self {
        case .none: return 0
        case .oneMonth: return 1
        case .threeMonths: return 3
        case .sixMonths: return 6
        }
    }

    /// Default when a stored / QA value is unrecognized. Matches Android
    /// `HistoryRetention.DEFAULT`.
    public static let `default`: HistoryRetention = .threeMonths

    /// Map a `SettingsStore.historyRetention` string token; unknown → `default`.
    public static func fromSetting(_ setting: String) -> HistoryRetention {
        HistoryRetention(rawValue: setting) ?? `default`
    }

    /// Whether this window records anything at all.
    public var isRecording: Bool { self != .none }

    /// One flat month for retention math — a coarse "how long to keep"
    /// preference, not a calendar computation. Matches Android
    /// `APPROX_MONTH_MS = 30 days`.
    public static let approxMonthMs: Int64 = 30 * 24 * 60 * 60 * 1000
}
