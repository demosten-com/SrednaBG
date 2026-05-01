// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGData

/// Localized TTS phrases. Mirrors the five hardcoded BG/EN strings in
/// `AudioAlertManager.kt` so iOS sounds identical to Android in the car.
public enum AnnouncementEvent: Sendable, Equatable {
    case entry(road: String, limit: Int)
    case overLimit(avgSpeedKmh: Int)
    case recovered(avgSpeedKmh: Int)
    case withinLimit(avgSpeedKmh: Int)
    case exit(avgSpeedKmh: Int)
}

public enum TtsPhrases {
    public static func phrase(for event: AnnouncementEvent, language: AppLanguage) -> String {
        let lang: AppLanguage
        switch language {
        case .system: lang = .en // safe default; orchestrator should pre-resolve
        case .bg, .en: lang = language
        }
        switch (event, lang) {
        case (.entry(_, let limit), .bg):
            return "Влизате в зона за средна скорост. Ограничение \(limit)."
        case (.entry(_, let limit), .en):
            return "Entering average speed zone. Speed limit \(limit)."
        case (.overLimit(let avg), .bg):
            return "Внимание: средна скорост \(avg). Намалете."
        case (.overLimit(let avg), .en):
            return "Warning: average speed \(avg). Slow down."
        case (.recovered(let avg), .bg):
            return "Средната скорост е отново в норма. \(avg)."
        case (.recovered(let avg), .en):
            return "Back within limit. \(avg)."
        case (.withinLimit(let avg), .bg):
            return "Средна скорост \(avg). В норма."
        case (.withinLimit(let avg), .en):
            return "Average speed \(avg). Within limit."
        case (.exit(let avg), .bg):
            return "Излизате от зоната. Средна скорост \(avg)."
        case (.exit(let avg), .en):
            return "Leaving zone. Average speed was \(avg)."
        case (_, .system):
            // Unreachable — `lang` is normalized above.
            return ""
        }
    }
}
