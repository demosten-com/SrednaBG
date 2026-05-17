// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTheme

import SwiftUI
import SrednaBGCore
#if canImport(UIKit)
import UIKit
#endif

/// Status traffic-light colors. Match the Android `SpeedGreen / Amber / Red`
/// constants so screenshots in the Play / App Store listings stay consistent.
/// UIKit peers live in `SrednaBGMapCore.statusUIColor(_:)`; the map-line and
/// CarPlay-HUD peers stay on the lighter yellow (#FDD835) because they render
/// over dark/map surfaces — only the SwiftUI `statusAmber` adapts per appearance
/// to mirror Android's `warningAmber()` (HomeScreen cards + StatusChip).
public enum Theme {
    public static let statusGreen = Color(red: 102 / 255, green: 187 / 255, blue: 106 / 255)
    public static let statusAmber = dynamicStatusAmber
    public static let statusRed   = Color(red: 239 / 255, green: 83 / 255, blue: 80 / 255)
}

/// Light: `#B8860B` (DarkGoldenrod) — the lighter `#FDD835` washes out on the
/// pale amber-tinted card / chip backgrounds; the deeper shade hits ~4.4:1
/// contrast against white while staying yellow rather than crossing into orange.
/// Dark: keeps `#FDD835` — already legible against the dark tinted surfaces.
/// Mirrors `warningAmber()` in `android/.../ui/theme/SpeedColors.kt`.
#if canImport(UIKit)
private let dynamicStatusAmber = Color(uiColor: UIColor { trait in
    trait.userInterfaceStyle == .dark
        ? UIColor(red: 253 / 255, green: 216 / 255, blue: 53 / 255, alpha: 1)
        : UIColor(red: 184 / 255, green: 134 / 255, blue: 11 / 255, alpha: 1)
})
#else
private let dynamicStatusAmber = Color(red: 253 / 255, green: 216 / 255, blue: 53 / 255)
#endif

/// Bridge raw `Int32` status colors produced by `SrednaBGCore.zoneStatusColor`
/// to SwiftUI. Kept here (not in `SrednaBGCore`) so `SrednaBGCore` stays free
/// of SwiftUI imports and remains macOS / Linux portable.
public func statusSwiftUIColor(_ packed: Int32) -> Color {
    switch packed {
    case zoneColorGreen:  return Theme.statusGreen
    case zoneColorYellow: return Theme.statusAmber
    case zoneColorRed:    return Theme.statusRed
    default:              return .primary
    }
}
