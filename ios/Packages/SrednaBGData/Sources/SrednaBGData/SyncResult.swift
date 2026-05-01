// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGData

import Foundation

/// Outcome of a single sync attempt. Mirrors `SyncResult` from
/// `android/app/.../data/ZoneRepository.kt` so the UI can render the same
/// three-way Snackbar feedback ("Updated" / "Up to date" / "Failed").
public enum SyncResult: Sendable {
    case updated
    case upToDate
    case failed(any Error & Sendable)
}

extension SyncResult: Equatable {
    public static func == (lhs: SyncResult, rhs: SyncResult) -> Bool {
        switch (lhs, rhs) {
        case (.updated, .updated): return true
        case (.upToDate, .upToDate): return true
        case (.failed(let l), .failed(let r)):
            return (l as NSError) == (r as NSError)
        default: return false
        }
    }
}
