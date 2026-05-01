// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGMapCore

#if canImport(UIKit)
import UIKit
import SrednaBGCore

/// UIKit peer for the MapLibre line-color expressions — `NSExpression`
/// can't consume a SwiftUI `Color`, so the map layer code (and the
/// CarPlay UIKit overlay) goes through this. Keeps the same bit-pattern
/// as the SwiftUI `Color` variants in `SrednaBGUI.Theme`; must stay in
/// visual lock-step with them.
public func statusUIColor(_ packed: Int32) -> UIColor {
    switch packed {
    case zoneColorGreen:  return UIColor(red: 102 / 255, green: 187 / 255, blue: 106 / 255, alpha: 1)
    case zoneColorYellow: return UIColor(red: 253 / 255, green: 216 / 255, blue: 53 / 255, alpha: 1)
    case zoneColorRed:    return UIColor(red: 239 / 255, green: 83 / 255, blue: 80 / 255, alpha: 1)
    default:              return .label
    }
}
#endif
