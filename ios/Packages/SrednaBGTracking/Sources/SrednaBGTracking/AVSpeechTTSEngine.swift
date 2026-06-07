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
///   * `.duckOthers` (alone) so music *and* podcasts duck uniformly while we
///     speak — Apple Maps / Spotify drop to reduced volume, not silenced.
///   * `.voicePrompt` mode so iOS knows this is short, time-sensitive speech.
///   * The session is activated before each utterance and deactivated on
///     completion (`.notifyOthersOnDeactivation`), so other audio ducks only
///     for the ~2s announcement, not the whole drive.
///
/// `@MainActor` rather than `actor` is deliberate: `AVSpeechSynthesizer` and
/// the `AVAudioSession` setup are main-thread-only, and driving them from a
/// custom actor's executor leaves AVFoundation to bridge back via
/// `dispatch_sync`, which trips the runtime's "unsafeForcedSync called from
/// Swift Concurrent context." warning (paired with `AVAudioBuffer.mm:281
/// mBuffers[0].mDataByteSize (0) should be non-zero` on the same line).
@MainActor
public final class AVSpeechTTSEngine: NSObject, TTSEngine, AVSpeechSynthesizerDelegate {

    private let synthesizer = AVSpeechSynthesizer()
    private var didConfigureCategory = false
    /// Set by `stop()`, cleared by `speak()`. Guards the deferred enqueue in
    /// `speak` so an utterance whose dispatch block was scheduled just before a
    /// stop can't start speaking *after* tracking stopped.
    private var stopped = false

    public override init() {
        super.init()
        // Observe utterance completion so we can relinquish the audio session
        // (un-duck other apps) as soon as each announcement finishes.
        synthesizer.delegate = self
    }

    public func speak(_ phrase: String, language: AppLanguage) async {
        // QA mute: parser self-test still sees the `speak:` log line emitted
        // by `AudioAlertManager`, but no audio plays. Used by the harness to
        // silence the simulator without breaking the tripwire.
        if QAFlags.ttsMuted { return }
        // Configure the category once, then re-assert `setActive(true)` on
        // EVERY utterance. The system deactivates our session when the app
        // backgrounds or after an audio interruption (call / Siri); a non-active
        // session means the enqueued utterance never starts — and because
        // AVSpeechSynthesizer plays serially, that stuck utterance blocks the
        // queue head so nothing speaks again, even back in the foreground.
        // (Why `audio` must stay in UIBackgroundModes: see ios/CLAUDE.md.)
        configureCategoryIfNeeded()
        activateSession()
        // A genuine speak request re-arms the engine after any prior stop.
        stopped = false
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
        DispatchQueue.main.async { [weak self] in
            // Bail if a stop landed between this block being enqueued and run —
            // otherwise a late announcement would start speaking after the user
            // already stopped tracking. (The block runs on the main queue, so
            // reading the MainActor-isolated flag via `assumeIsolated` is safe.)
            guard let self, !MainActor.assumeIsolated({ self.stopped }) else { return }
            // Clear ONLY a paused/interrupted utterance (e.g. left over after a
            // Siri or call interruption) so a fresh announcement isn't blocked
            // behind stale, non-progressing speech. Deliberately do NOT clear an
            // actively-speaking one: closely-spaced announcements — an over-limit
            // warning moments after the zone-entry line, common on short zones
            // entered while already speeding — must serialize (queue), not
            // clobber each other mid-sentence. The background-deactivation wedge
            // is handled by `activateSession()` above, not by force-stopping.
            if synth.isPaused {
                synth.stopSpeaking(at: .immediate)
            }
            let utterance = AVSpeechUtterance(string: phrase)
            utterance.voice = AVSpeechSynthesisVoice(language: bcp47)
            synth.speak(utterance)
        }
    }

    public func stop() async {
        stopped = true
        // We're already on the MainActor, so cancel synchronously: the current
        // utterance is cut off in this turn of the runloop rather than a tick
        // later via DispatchQueue.main.async (which let a syllable leak out
        // after the user tapped Stop). `.immediate` cuts mid-word and also
        // clears any queued utterances.
        synthesizer.stopSpeaking(at: .immediate)
        // Tracking stopped — relinquish so other audio returns to full volume.
        // (stopSpeaking fires didCancel, which we deliberately ignore.)
        Self.relinquishSession()
    }

    /// Sets the audio-session category once (it's sticky across activation
    /// cycles). `.duckOthers` alone — NOT `.interruptSpokenAudioAndMixWithOthers`
    /// — so EVERYTHING (music *and* podcasts) ducks uniformly while we speak.
    /// The earlier mix directive let music play on top at full volume, which is
    /// why announcements didn't lower Spotify. Ducking is scoped to each
    /// utterance by the activate / `relinquishSession`-on-`didFinish` pair.
    private func configureCategoryIfNeeded() {
        guard !didConfigureCategory else { return }
        #if os(iOS)
        do {
            try AVAudioSession.sharedInstance().setCategory(
                .playback,
                mode: .voicePrompt,
                options: [.duckOthers]
            )
            didConfigureCategory = true
        } catch {
            // Non-fatal — leave the flag false so the next utterance retries.
        }
        #else
        didConfigureCategory = true
        #endif
    }

    /// Re-asserts an active session before every utterance so a session the
    /// system deactivated on background / interruption can't permanently wedge
    /// the synthesizer (see `speak`). `try?` — a transient activation failure
    /// must never block the next announcement.
    private func activateSession() {
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(true, options: [])
        #endif
    }

    /// Hands other audio back to full volume once our announcement finishes.
    /// `.notifyOthersOnDeactivation` asks the system to un-duck immediately;
    /// `try?` because deactivation can fail harmlessly if the system already
    /// tore the session down (e.g. an interruption cancelled the utterance).
    nonisolated private static func relinquishSession() {
        #if os(iOS)
        DispatchQueue.main.async {
            try? AVAudioSession.sharedInstance().setActive(
                false,
                options: [.notifyOthersOnDeactivation]
            )
        }
        #endif
    }

    // MARK: AVSpeechSynthesizerDelegate

    /// Release the session on normal completion only — NOT on `didCancel`. The
    /// paused-clear path in `speak` cancels a stale utterance immediately before
    /// starting a fresh one; deactivating there would un-duck mid-announcement.
    /// The replacement utterance's own `didFinish` performs the release.
    ///
    /// Only relinquish once the WHOLE batch is done. When announcements queue
    /// back-to-back (zone-entry line + an immediate over-limit warning),
    /// `isSpeaking` stays true while the next utterance is still pending —
    /// deactivating between them churns the session and produces an audible
    /// "cough" at the boundary. Releasing only when nothing is left to speak
    /// keeps the session active across the run, then un-ducks cleanly.
    nonisolated public func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didFinish utterance: AVSpeechUtterance
    ) {
        guard !synthesizer.isSpeaking else { return }
        Self.relinquishSession()
    }
}
#endif
