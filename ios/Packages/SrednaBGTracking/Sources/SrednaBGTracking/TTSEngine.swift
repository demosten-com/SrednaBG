// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

import Foundation
import SrednaBGData

/// Abstraction over `AVSpeechSynthesizer` for testability. The real
/// implementation is `AVSpeechTTSEngine` (iOS / macOS). Tests use a recorder
/// that captures every `speak` call.
public protocol TTSEngine: Sendable {
    func speak(_ phrase: String, language: AppLanguage) async
    func stop() async
}
