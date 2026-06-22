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
        // Spell the number into words so `AVSpeechSynthesizer` never reads it
        // digit-by-digit ("one one two" instead of "one hundred twelve"). Mirrors
        // Android's `SpeechNumbers.kt`.
        let bg = lang == .bg
        switch (event, lang) {
        case (.entry(_, let limit), .bg):
            return "Влизате в зона за средна скорост. Ограничение \(SpeechNumbers.words(limit, bulgarian: bg))."
        case (.entry(_, let limit), .en):
            return "Entering average speed zone. Speed limit \(SpeechNumbers.words(limit, bulgarian: bg))."
        case (.overLimit(let avg), .bg):
            return "Внимание: средна скорост \(SpeechNumbers.words(avg, bulgarian: bg)). Намалете."
        case (.overLimit(let avg), .en):
            return "Warning: average speed \(SpeechNumbers.words(avg, bulgarian: bg)). Slow down."
        case (.recovered(let avg), .bg):
            return "Средната скорост е отново в норма. \(SpeechNumbers.words(avg, bulgarian: bg))."
        case (.recovered(let avg), .en):
            return "Back within limit. \(SpeechNumbers.words(avg, bulgarian: bg))."
        case (.withinLimit(let avg), .bg):
            return "Средна скорост \(SpeechNumbers.words(avg, bulgarian: bg)). В норма."
        case (.withinLimit(let avg), .en):
            return "Average speed \(SpeechNumbers.words(avg, bulgarian: bg)). Within limit."
        case (.exit(let avg), .bg):
            return "Излизате от зоната. Средна скорост \(SpeechNumbers.words(avg, bulgarian: bg))."
        case (.exit(let avg), .en):
            return "Leaving zone. Average speed was \(SpeechNumbers.words(avg, bulgarian: bg))."
        case (_, .system):
            // Unreachable — `lang` is normalized above.
            return ""
        }
    }
}
