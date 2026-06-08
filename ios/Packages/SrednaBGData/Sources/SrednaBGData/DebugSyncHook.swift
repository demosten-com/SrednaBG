// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

// Debug-only: emitted exclusively from `DebugActionRouter` (also `#if DEBUG`).
// Kept out of release alongside the rest of the QA control surface.
#if DEBUG
import Foundation

/// QA-only sync logger. Wraps a sync attempt and emits a `DebugSync` line
/// that matches Android's `DebugSyncReceiver` output, so the parser in
/// `qa/parsers.py` (SYNC_RE) yields the same `SyncResult` event on both
/// platforms.
///
/// Use it like:
///
///     await DebugSyncHook.run("SYNC_ZONES") {
///         _ = try await syncClient.fetchZones()
///         return .updated
///     }
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

    /// Run `body` and emit the QA log line with the resolved outcome.
    /// Re-throws after logging so caller-level error handling is unchanged.
    public static func run(
        _ action: String,
        body: () async throws -> DebugSyncOutcome
    ) async throws -> DebugSyncOutcome {
        do {
            let outcome = try await body()
            log(action: action, outcome: outcome, detail: nil)
            return outcome
        } catch {
            log(action: action, outcome: .failed, detail: String(describing: error))
            throw error
        }
    }

    /// Direct logger when the caller already has an outcome (no closure).
    public static func log(action: String, outcome: DebugSyncOutcome, detail: String?) {
        let detailPart = detail.map { "(\($0))" } ?? ""
        QALog.sync.info(
            "\(actionPrefix, privacy: .public)\(action, privacy: .public) -> SyncResult.\(outcome.rawValue, privacy: .public)\(detailPart, privacy: .public)"
        )
    }
}
#endif
