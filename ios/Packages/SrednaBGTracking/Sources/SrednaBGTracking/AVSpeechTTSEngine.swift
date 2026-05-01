// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — ios / SrednaBGTracking

#if canImport(AVFoundation)
import Foundation
@preconcurrency import AVFoundation
import SrednaBGData

/// Production `TTSEngine` backed by `AVSpeechSynthesizer`. Configures the
/// shared `AVAudioSession` (iOS only) for navigation guidance:
///   * `.playback` category so we keep speaking with the screen locked.
///   * `.duckOthers` so Apple Maps / Spotify stay audible at reduced volume.
///   * `.voicePrompt` mode so iOS knows this is short, time-sensitive speech.
///
/// `@MainActor` rather than `actor` is deliberate: `AVSpeechSynthesizer` and
/// the `AVAudioSession` setup are main-thread-only, and driving them from a
/// custom actor's executor leaves AVFoundation to bridge back via
/// `dispatch_sync`, which trips the runtime's "unsafeForcedSync called from
/// Swift Concurrent context." warning (paired with `AVAudioBuffer.mm:281
/// mBuffers[0].mDataByteSize (0) should be non-zero` on the same line).
@MainActor
public final class AVSpeechTTSEngine: TTSEngine {

    private let synthesizer = AVSpeechSynthesizer()
    private var didConfigureSession = false

    public init() {}

    public func speak(_ phrase: String, language: AppLanguage) async {
        configureSessionIfNeeded()
        let bcp47: String
        switch language {
        case .bg: bcp47 = "bg-BG"
        case .en, .system: bcp47 = "en-US"
        }
        // Defer the entire utterance build + `speak` to a fresh
        // main-runloop tick so it executes outside any Swift Task
        // back-stack. `AVSpeechSynthesisVoice(language:)` triggers the
        // voice-catalog loader on first use and AVSpeechSynthesizer +
        // CoreAudio do internal `dispatch_sync` calls during speech;
        // when the call originates inside an awaited Task the runtime
        // emits "Potential Structural Swift Concurrency Issue:
        // unsafeForcedSync called from Swift Concurrent context."
        // (paired with `AVAudioBuffer.mm:281` / `Error fetching voices`
        // on the same line). Hopping through DispatchQueue.main.async
        // strips the Task context and silences the spam without
        // changing semantics — `speak` is a non-blocking enqueue either
        // way.
        let synth = synthesizer
        DispatchQueue.main.async {
            let utterance = AVSpeechUtterance(string: phrase)
            utterance.voice = AVSpeechSynthesisVoice(language: bcp47)
            synth.speak(utterance)
        }
    }

    public func stop() async {
        let synth = synthesizer
        DispatchQueue.main.async {
            synth.stopSpeaking(at: .immediate)
        }
    }

    private func configureSessionIfNeeded() {
        guard !didConfigureSession else { return }
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(
                .playback,
                mode: .voicePrompt,
                options: [.duckOthers, .interruptSpokenAudioAndMixWithOthers]
            )
            try session.setActive(true, options: [])
            didConfigureSession = true
        } catch {
            // Audio session failures are non-fatal — speak() still attempts to
            // play, possibly without ducking.
        }
        #else
        didConfigureSession = true
        #endif
    }
}
#endif
