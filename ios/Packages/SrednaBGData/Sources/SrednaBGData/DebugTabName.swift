// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Shared constants for the QA harness's tab-selection back-channel.
///
/// `DebugActionRouter` accepts `/tab?which=<name>` and posts
/// `selectionNotification` with `userInfo[userInfoKey]` set to the name.
/// `RootView` (under `#if DEBUG`) observes it and drives `TabView`'s
/// selection binding so the screenshot harness can switch tabs over HTTP
/// without needing a mobile-mcp accessibility tap.
public enum DebugTabName {

    public static let home = "home"
    public static let map = "map"
    public static let settings = "settings"

    public static let all: [String] = [home, map, settings]

    public static let selectionNotification = Notification.Name(
        "bg.srednabg.debug.selectTab"
    )
    public static let userInfoKey = "tab"

    public static func isValid(_ which: String) -> Bool {
        all.contains(which)
    }
}
