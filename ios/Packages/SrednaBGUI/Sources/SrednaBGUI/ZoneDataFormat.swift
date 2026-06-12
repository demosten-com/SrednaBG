// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation

/// Render helpers for the zone-data fine print under "Sync zones now".
/// Mirrors `ZoneDataFormat.kt` on Android.
enum ZoneDataFormat {

    static let dash = "--"

    /// GitHub-style short form of the zone-data hash: `sha256:` prefix
    /// dropped, first 16 hex chars.
    static func shortHash(_ raw: String) -> String {
        let hex = raw.hasPrefix("sha256:") ? String(raw.dropFirst("sha256:".count)) : raw
        return hex.isEmpty ? dash : String(hex.prefix(16))
    }

    /// Renders the zones.json ISO-8601 `version` timestamp in the locale's
    /// short date+time form (device time zone).
    static func formatVersion(_ iso: String, locale: Locale = .current) -> String {
        guard let date = ISO8601DateFormatter().date(from: iso) else { return dash }
        return date.formatted(Date.FormatStyle(date: .numeric, time: .shortened, locale: locale))
    }
}
