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
    public static let history = "history"
    public static let settings = "settings"

    public static let all: [String] = [home, map, history, settings]

    public static let selectionNotification = Notification.Name(
        "bg.srednabg.debug.selectTab"
    )
    public static let userInfoKey = "tab"

    public static func isValid(_ which: String) -> Bool {
        all.contains(which)
    }
}

/// Back-channel for opening the History **detail** page of the newest record.
///
/// `DebugActionRouter` accepts `/history?action=open` and posts
/// `openNotification`; `HistoryScreen` (under `#if DEBUG`) observes it and
/// pushes the detail view. Android's screenshot harness taps the `history-row`
/// node instead — the Simulator has no synthetic-tap path, same split as
/// `DebugTabName`.
public enum DebugHistoryOpen {

    public static let openNotification = Notification.Name(
        "bg.srednabg.debug.openHistoryDetail"
    )
    /// `userInfo` key carrying which record to open — see `select`.
    public static let selectUserInfoKey = "select"

    /// Newest record (default).
    public static let newest = "newest"
    /// First record within its limit.
    public static let green = "green"
    /// First record over its limit.
    public static let red = "red"
}
