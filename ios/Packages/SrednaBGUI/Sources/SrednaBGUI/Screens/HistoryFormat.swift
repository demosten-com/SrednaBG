// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation

/// Date / duration / dash formatting for the History tab. Mirrors Android's
/// `HistoryFormat.kt` (`formatHistoryDay` = medium date, short time, short
/// date+time, and a locale-neutral `M:SS` / `H:MM:SS` duration).
enum HistoryFormat {

    /// Local calendar day (midnight) of an epoch-ms instant — the list's
    /// grouping key.
    static func day(_ epochMs: Int64, calendar: Calendar = .current) -> Date {
        calendar.startOfDay(for: date(epochMs))
    }

    static func date(_ epochMs: Int64) -> Date {
        Date(timeIntervalSince1970: Double(epochMs) / 1000)
    }

    /// Medium localized date for a day-group header (e.g. "1 Jul 2026").
    static func historyDay(_ epochMs: Int64, locale: Locale) -> String {
        date(epochMs).formatted(
            Date.FormatStyle(date: .abbreviated, time: .omitted).locale(locale)
        )
    }

    /// Short localized time for a list row (e.g. "14:32").
    static func historyTime(_ epochMs: Int64, locale: Locale) -> String {
        date(epochMs).formatted(
            Date.FormatStyle(date: .omitted, time: .shortened).locale(locale)
        )
    }

    /// Short localized date + time for the detail entry / exit labels.
    static func historyDateTime(_ epochMs: Int64, locale: Locale) -> String {
        date(epochMs).formatted(
            Date.FormatStyle(date: .numeric, time: .shortened).locale(locale)
        )
    }

    /// Clock-style duration: `M:SS`, or `H:MM:SS` past an hour. Locale-neutral
    /// (digits + colons), so no per-language string — matches Android.
    static func duration(fromMs durationMs: Int64) -> String {
        let totalSec = max(0, durationMs / 1000)
        let h = totalSec / 3600
        let m = (totalSec % 3600) / 60
        let s = totalSec % 60
        return h > 0
            ? String(format: "%d:%02d:%02d", h, m, s)
            : String(format: "%d:%02d", m, s)
    }

    /// Render a nullable km/h value as a rounded integer, or the shared dash
    /// placeholder when nil / non-finite.
    static func speedOrDash(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "--" }
        return String(Int(value.rounded()))
    }
}
