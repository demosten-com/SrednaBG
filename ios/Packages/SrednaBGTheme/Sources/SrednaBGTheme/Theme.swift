// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTheme

import SwiftUI
import SrednaBGCore

/// Status traffic-light colors. Match the Android `SpeedGreen / Amber / Red`
/// constants so screenshots in the Play / App Store listings stay consistent.
/// UIKit peers live in `SrednaBGMapCore.statusUIColor(_:)` and must stay in
/// visual lock-step with these values.
public enum Theme {
    public static let statusGreen = Color(red: 102 / 255, green: 187 / 255, blue: 106 / 255)
    public static let statusAmber = Color(red: 253 / 255, green: 216 / 255, blue: 53 / 255)
    public static let statusRed   = Color(red: 239 / 255, green: 83 / 255, blue: 80 / 255)
}

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
