// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

// Debug-only: emitted exclusively from `DebugActionRouter` (also `#if DEBUG`).
// Kept out of release alongside the rest of the QA control surface.
#if DEBUG
import Foundation

/// QA-only sync logger. Emits a `DebugSync` line that matches Android's
/// `DebugSyncReceiver` output, so the parser in `qa/parsers.py` (SYNC_RE)
/// yields the same `SyncResult` event on both platforms.
///
/// Use it like:
///
///     DebugSyncHook.log(action: "SYNC_ZONES", outcome: .updated, detail: nil)
///
/// The action name follows the Android intent format
/// (`com.demosten.srednabg.debug.SYNC_X`) so the same parser regex works
/// unchanged.
public enum DebugSyncOutcome: String, Sendable {
    case updated = "Updated"
    case upToDate = "UpToDate"
    case failed = "Failed"
}

public enum DebugSyncHook {

    public static let actionPrefix = "com.demosten.srednabg.debug."

    /// Emit the QA log line for an already-resolved outcome. `DebugActionRouter`
    /// calls this directly after running the sync handler.
    public static func log(action: String, outcome: DebugSyncOutcome, detail: String?) {
        let detailPart = detail.map { "(\($0))" } ?? ""
        QALog.sync.info(
            "\(actionPrefix, privacy: .public)\(action, privacy: .public) -> SyncResult.\(outcome.rawValue, privacy: .public)\(detailPart, privacy: .public)"
        )
    }
}
#endif
