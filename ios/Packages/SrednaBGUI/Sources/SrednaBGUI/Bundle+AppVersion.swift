// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGUI

import Foundation

public extension Bundle {
    /// `CFBundleShortVersionString` from the host app bundle (e.g. "1.0.2").
    /// Excludes `CFBundleVersion` (build number) — matches the App Store listing.
    static var appShortVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—"
    }
}
