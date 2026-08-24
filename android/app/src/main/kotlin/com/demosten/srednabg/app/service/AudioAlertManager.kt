// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.ui.util.SpeechNumbers
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneState
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AudioAlertManager @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository,
) {
    private companion object {
        const val TAG = "SrednaBG.TTS"
        const val MIN_ANNOUNCE_SPEED_KMH = 10.0
        const val TRANSIENT_EXIT_WINDOW_MS = 5_000L
        const val PERIODIC_INTERVAL_MS = 30_000L
        // Cold-start lead-in: after a fresh audio-focus grant the output route
        // (Android Auto / Bluetooth) needs a moment to duck the other app and
        // open our stream — speech synthesized in that window is swallowed, so
        // messages started with their first words clipped. Lead with this much
        // silence in the same TTS queue before the first words.
        const val ROUTE_WARMUP_SILENCE_MS = 400L
    }

    // Written on Main, read in the TTS init binder callback; @Volatile gives the
    // happens-before that callback relies on to see a non-null engine.
    @Volatile private var tts: TextToSpeech? = null
    private var isInitialized = false
    private var lastAnnouncementTime = 0L
    private var lastEntryTime = 0L
    // The zone whose entry we already spoke provisionally, and when. Consumed
    // by the Outside -> InZone branch to avoid announcing the same entry twice;
    // see [onProvisionalEntry].
    private var provisionalZoneId: String? = null
    private var provisionalTime = 0L
    private var languageJob: Job? = null
    // Outstanding TTS utterances. A chained pair (exit-with-average then
    // next-zone entry at co-located cameras) shares one audio-focus session;
    // focus is only abandoned when the queue drains, so QUEUE_ADD speech isn't
    // cut off by an early onDone from the first utterance.
    //
    // Only ever touched on the Main thread: speak() runs on the Main scope and
    // the UtteranceProgressListener's onDone/onError (which arrive on a TTS
    // binder thread) bounce onUtteranceFinished() back to Main via mainHandler.
    // That serialization is the whole thread-safety story — no atomics needed.
    private var pendingUtterances = 0
    private val mainHandler = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val audioManager by lazy { context.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    // Shared by the focus request AND the TTS engine itself: without
    // setAudioAttributes the engine speaks as default USAGE_MEDIA while our
    // focus claims navigation guidance — over Android Auto the media route is
    // the slower one to open, which clipped message starts alongside Waze.
    private val speechAudioAttributes by lazy {
        AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
    }
    private val audioFocusRequest by lazy {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(speechAudioAttributes)
            .build()
    }

    fun initialize() {
        if (tts != null) return
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                // shutdown() may have raced this async callback; a dead engine
                // must not be marked initialized or speak() would request audio
                // focus that no utterance callback ever releases.
                if (tts == null) return@TextToSpeech
                tts?.setAudioAttributes(speechAudioAttributes)
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    // These callbacks arrive on a TTS binder thread; hop to Main
                    // so pendingUtterances is only ever mutated on one thread.
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) = postUtteranceFinished()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = postUtteranceFinished()
                })
                languageJob?.cancel()
                languageJob = scope.launch {
                    settingsRepository.voiceLanguage.collect { lang ->
                        val locale = if (lang == "bg") Locale("bg", "BG") else Locale.ENGLISH
                        val res = tts?.setLanguage(locale)
                        if (res == TextToSpeech.LANG_MISSING_DATA || res == TextToSpeech.LANG_NOT_SUPPORTED) {
                            Log.w(TAG, "tts language $locale unavailable (res=$res); falling back to English")
                            tts?.setLanguage(Locale.ENGLISH)
                        }
                        // Mark ready only AFTER the locale is applied: otherwise the first
                        // announcement could speak on the device default locale, whose number
                        // normalization sometimes reads digits one-by-one ("one one two").
                        isInitialized = true
                        Log.d(TAG, "tts language set: $lang → $locale (res=$res)")
                    }
                }
            }
        }
    }

    fun shutdown() {
        languageJob?.cancel()
        languageJob = null
        tts?.stop()
        tts?.shutdown()
        tts = null
        isInitialized = false
        // stop() does not deliver onDone for the flushed in-flight utterance
        // (no onStop override), so the counter would never drain and audio focus
        // would stay held until process death — other apps stuck ducked. Reset
        // and abandon explicitly. Drop any queued onUtteranceFinished bounce so
        // it can't resurrect the counter after this reset. Idempotent: abandoning
        // focus we never requested is a no-op.
        mainHandler.removeCallbacksAndMessages(null)
        provisionalZoneId = null
        provisionalTime = 0L
        pendingUtterances = 0
        audioManager.abandonAudioFocusRequest(audioFocusRequest)
    }

    /**
     * Announce an entry the moment the detector opens a candidate for [zone],
     * rather than when the traversal is confirmed
     * [ZoneDetector.ENTRY_CONFIRM_DISTANCE_M] later.
     *
     * The measurement is untouched — a confirmed traversal is back-dated to
     * this same candidate's first fix — so this only moves the *voice* to where
     * the driver expects it. Before this, the entry was spoken ~300 m past the
     * camera and the driver, who cannot know the average was back-dated, read
     * that as the app being slow.
     *
     * Speaks the **same** message as the confirmed path ([getEntryMessage]), so
     * there is no second phrasing to localize and nothing signals "provisional"
     * to the driver — from the road, we *are* on the zone.
     *
     * The caller applies the `START_WITNESS_ARC_M` guard (see
     * `LocationTrackingService.announceProvisionalEntry`); this method only owns
     * the repeat window. If the candidate is later abandoned the entry simply
     * goes unrecorded — no retraction is spoken, because a correction the
     * driver did not ask for is more confusing than the silence.
     */
    fun onProvisionalEntry(zone: Zone, currentSpeedKmh: Double?) {
        scope.launch {
            val now = System.currentTimeMillis()
            if (isAlreadyAnnouncedProvisionally(zone.id, now)) {
                Log.d(TAG, "provisional entry repeat suppressed zone=${zone.id}")
                return@launch
            }
            if (!settingsRepository.voiceEnabled.first()) return@launch
            if ((currentSpeedKmh ?: 0.0) < MIN_ANNOUNCE_SPEED_KMH) return@launch

            // QA harness tripwire: line shape must match `qa/parsers.py`
            // PROVISIONAL_SPOKEN_RE (the iOS twin logs the same body). Emitted
            // only once the announcement is actually going out, so the harness
            // can read it as "the driver heard this".
            Log.d(TAG, "onProvisionalEntry zone=${zone.id} speed=$currentSpeedKmh")
            provisionalZoneId = zone.id
            provisionalTime = now
            lastEntryTime = now
            lastAnnouncementTime = now
            speak(getEntryMessage(zone.road, getSpeedLimit(zone)))
        }
    }

    fun onZoneStateChanged(
        previousState: ZoneState,
        newState: ZoneState,
        currentSpeedKmh: Double?,
    ) {
        scope.launch {
            val zoneId = when (newState) {
                is ZoneState.InZone -> newState.zone.id
                is ZoneState.Exiting -> newState.zone.id
                // We know which zone it is even when we can't measure it, and the
                // QA harness reads this line — don't report "-" for it.
                is ZoneState.Unmeasured -> newState.zone.id
                else -> "-"
            }
            Log.d(
                TAG,
                "onZoneStateChanged prev=${previousState::class.simpleName} " +
                    "new=${newState::class.simpleName} zone=$zoneId speed=$currentSpeedKmh",
            )

            if (!settingsRepository.voiceEnabled.first()) return@launch
            if ((currentSpeedKmh ?: 0.0) < MIN_ANNOUNCE_SPEED_KMH) return@launch

            when {
                // Every transition into or out of Unmeasured is silent, and that
                // is a decision rather than an unmatched pair falling off the end
                // of this `when` — see [isUnmeasuredTransition]. Placed first so
                // no later branch can accidentally claim one of these pairs.
                //
                // "First" is about this `when` only — it is not coupled to the
                // MIN_ANNOUNCE_SPEED_KMH guard above. A stopped driver is already
                // silent by suppression, so neither moving that guard below this
                // branch nor moving this branch below it would break the contract;
                // the silence holds either way.
                isUnmeasuredTransition(previousState, newState) -> Unit
                previousState is ZoneState.Outside && newState is ZoneState.InZone -> {
                    val limit = getSpeedLimit(newState)
                    val now = System.currentTimeMillis()
                    lastEntryTime = now
                    lastAnnouncementTime = now
                    // Already spoken when the candidate opened, a few hundred
                    // metres back — see [onProvisionalEntry]. Skip only the
                    // entry line: the over-limit warning below needs a real
                    // average, which did not exist yet at candidate time, so it
                    // must still fire from this confirmed transition.
                    if (isAlreadyAnnouncedProvisionally(newState.zone.id, now)) {
                        Log.d(TAG, "entry already announced provisionally zone=${newState.zone.id}")
                    } else {
                        speak(getEntryMessage(newState.zone.road, limit))
                    }
                    provisionalZoneId = null
                    // A traversal can now open *already* over the limit: entry is
                    // confirmed over ENTRY_CONFIRM_DISTANCE_M and then back-dated to
                    // the first confirming fix, so the very first InZone state can
                    // carry a few hundred metres of speeding. The over-limit branch
                    // below only fires on a false -> true flip between two InZone
                    // states, so without this the warning is silently dropped for
                    // exactly the driver who most needs it. QUEUE_ADD (see the
                    // co-located branch) so it plays after the entry line rather
                    // than cutting it off.
                    announceEntryOverLimit(newState)
                }
                previousState is ZoneState.InZone && newState is ZoneState.InZone -> {
                    val isOver = newState.speedStatus.isOverLimit
                    val wasOver = previousState.speedStatus.isOverLimit
                    val now = System.currentTimeMillis()
                    val avgSpeed = newState.avgSpeed?.toInt() ?: return@launch
                    when {
                        !wasOver && isOver -> {
                            lastAnnouncementTime = now
                            speak(getOverLimitMessage(avgSpeed))
                        }
                        wasOver && !isOver -> {
                            lastAnnouncementTime = now
                            speak(getRecoveredMessage(avgSpeed))
                        }
                        else -> {
                            val periodicEnabled = settingsRepository.periodicVoiceUpdates.first()
                            if (periodicEnabled && now - lastAnnouncementTime > PERIODIC_INTERVAL_MS) {
                                val onlyWhenOver = settingsRepository.announceOnlyWhenOver.first()
                                if (isOver) {
                                    lastAnnouncementTime = now
                                    speak(getOverLimitMessage(avgSpeed))
                                } else if (!onlyWhenOver) {
                                    lastAnnouncementTime = now
                                    speak(getWithinLimitMessage(avgSpeed))
                                }
                                // in-limit + only-when-over: suppressed. Don't touch
                                // lastAnnouncementTime so the next over-limit tick
                                // can fire without another 30s wait.
                            }
                        }
                    }
                }
                previousState is ZoneState.InZone && newState is ZoneState.Exiting -> {
                    val now = System.currentTimeMillis()
                    if (now - lastEntryTime < TRANSIENT_EXIT_WINDOW_MS) {
                        // Transient GPS glitch / very short zone — we just announced entry;
                        // announcing an exit a moment later would confuse the driver.
                        Log.d(TAG, "suppressing exit TTS — entry was ${now - lastEntryTime}ms ago")
                        lastAnnouncementTime = 0
                        return@launch
                    }
                    val avgSpeed = newState.finalAvgSpeed?.toInt() ?: return@launch
                    speak(getExitMessage(avgSpeed))
                    lastAnnouncementTime = 0
                }
                previousState is ZoneState.Exiting && newState is ZoneState.InZone -> {
                    // Co-located cameras: one camera ends zone A and begins zone B, so the
                    // state machine steps InZone(A) → Exiting(A) → InZone(B) on consecutive
                    // fixes (24 such pairs in the data, mostly Trakiya). The exit-with-average
                    // for A already announced on the prior InZone→Exiting transition; here we
                    // must announce ENTERING B. Without this branch entry into the next zone
                    // is silent. QUEUE_ADD so this plays AFTER A's still-speaking exit line
                    // instead of QUEUE_FLUSH cutting it off ~1 s in.
                    if (previousState.zone.id == newState.zone.id) {
                        // Same zone re-admitted (off-road blip / hooked-tail flap recovered),
                        // not a new zone — no entry announcement.
                        return@launch
                    }
                    val limit = getSpeedLimit(newState)
                    val now = System.currentTimeMillis()
                    lastEntryTime = now
                    lastAnnouncementTime = now
                    provisionalZoneId = null
                    speak(getEntryMessage(newState.zone.road, limit), TextToSpeech.QUEUE_ADD)
                    announceEntryOverLimit(newState)
                }
            }
        }
    }

    /**
     * Warn when a traversal *opens* already over the limit.
     *
     * The InZone→InZone branch only reacts to a false→true flip in
     * [SpeedStatus.isOverLimit], which assumed a traversal always starts at ~0
     * average and climbs. That stopped being true once entry gained a
     * confirmation window (ZoneDetector.ENTRY_CONFIRM_DISTANCE_M) that is
     * back-dated to the first confirming fix: the first InZone state now carries
     * a few hundred metres of real driving, so a driver who was already speeding
     * enters *over* the limit and would never produce a flip to react to.
     * Regression: qa/scenarios/edge/vehicle_type_limit_badge.py.
     */
    private suspend fun announceEntryOverLimit(state: ZoneState.InZone) {
        if (!state.speedStatus.isOverLimit) return
        val avgSpeed = state.avgSpeed?.toInt() ?: return
        lastAnnouncementTime = System.currentTimeMillis()
        speak(getOverLimitMessage(avgSpeed), TextToSpeech.QUEUE_ADD)
    }

    /**
     * Was this entry already spoken by [onProvisionalEntry]? See
     * [isProvisionalStillFresh].
     *
     */
    private fun isAlreadyAnnouncedProvisionally(zoneId: String, now: Long): Boolean =
        isProvisionalStillFresh(zoneId, provisionalZoneId, provisionalTime, now)

    private suspend fun getSpeedLimit(state: ZoneState.InZone): Int = getSpeedLimit(state.zone)

    private suspend fun getSpeedLimit(zone: Zone): Int {
        val vehicleType = VehicleType.fromSetting(settingsRepository.vehicleType.first())
        return vehicleType.limit(zone.speedLimits)
    }

    private suspend fun getEntryMessage(road: String, limit: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Влизате в зона за средна скорост. Ограничение ${SpeechNumbers.toWords(limit, bulgarian = true)}."
        } else {
            "Entering average speed zone. Speed limit ${SpeechNumbers.toWords(limit, bulgarian = false)}."
        }
    }

    private suspend fun getWithinLimitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Средна скорост ${SpeechNumbers.toWords(avgSpeed, bulgarian = true)}. В норма."
        } else {
            "Average speed ${SpeechNumbers.toWords(avgSpeed, bulgarian = false)}. Within limit."
        }
    }

    private suspend fun getOverLimitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Внимание: средна скорост ${SpeechNumbers.toWords(avgSpeed, bulgarian = true)}. Намалете."
        } else {
            "Warning: average speed ${SpeechNumbers.toWords(avgSpeed, bulgarian = false)}. Slow down."
        }
    }

    private suspend fun getRecoveredMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Средната скорост е отново в норма. ${SpeechNumbers.toWords(avgSpeed, bulgarian = true)}."
        } else {
            "Back within limit. ${SpeechNumbers.toWords(avgSpeed, bulgarian = false)}."
        }
    }

    private suspend fun getExitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Излизате от зоната. Средна скорост ${SpeechNumbers.toWords(avgSpeed, bulgarian = true)}."
        } else {
            "Leaving zone. Average speed was ${SpeechNumbers.toWords(avgSpeed, bulgarian = false)}."
        }
    }

    private fun speak(text: String, queueMode: Int = TextToSpeech.QUEUE_FLUSH) {
        if (!isInitialized) {
            Log.d(TAG, "speak: TTS not initialized, dropping: \"$text\"")
            return
        }
        audioManager.requestAudioFocus(audioFocusRequest)
        // A cold focus session (nothing queued or speaking) needs the
        // ROUTE_WARMUP_SILENCE_MS lead-in before the words, or the route-open
        // delay clips the message start. A warm queue is already routed — no
        // lead-in, and the silence must not apply when queueMode is QUEUE_ADD
        // chaining onto live speech.
        val coldStart = pendingUtterances == 0
        // QUEUE_FLUSH wipes anything still queued, so reset the outstanding count;
        // QUEUE_ADD appends, so add to it. The shared utterance id is fine — the
        // listener counts onDone/onError callbacks, not ids.
        if (queueMode == TextToSpeech.QUEUE_FLUSH) pendingUtterances = 0
        pendingUtterances += if (coldStart) 2 else 1
        // Log order mirrors enqueue order (lead-in, then words) — the QA
        // parser orders TtsLeadIn before TtsSpeak on it.
        if (coldStart) {
            Log.d(TAG, "speak: cold start, ${ROUTE_WARMUP_SILENCE_MS}ms lead-in")
            val silence = tts?.playSilentUtterance(ROUTE_WARMUP_SILENCE_MS, queueMode, "srednabg_lead_in")
            if (silence != TextToSpeech.SUCCESS) {
                Log.w(TAG, "speak: lead-in enqueue failed (result=$silence)")
                onUtteranceFinished()
            }
        }
        Log.d(TAG, "speak: \"$text\"")
        // On a cold start the lead-in already carried the caller's queueMode
        // (flushing if asked to); the speech itself must chain after it.
        val speechMode = if (coldStart) TextToSpeech.QUEUE_ADD else queueMode
        val result = tts?.speak(text, speechMode, null, "srednabg_alert")
        if (result != TextToSpeech.SUCCESS) {
            // A rejected enqueue never reaches the utterance listener, so undo
            // its count here or the audio focus stays held (other apps ducked).
            Log.w(TAG, "speak: enqueue failed (result=$result)")
            onUtteranceFinished()
        }
    }

    // Bounce a binder-thread utterance callback onto Main. On Main already
    // (the enqueue-failed path in speak()), run inline to keep ordering tight.
    private fun postUtteranceFinished() {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            onUtteranceFinished()
        } else {
            mainHandler.post(::onUtteranceFinished)
        }
    }

    // Main-thread only.
    private fun onUtteranceFinished() {
        pendingUtterances = (pendingUtterances - 1).coerceAtLeast(0)
        if (pendingUtterances == 0) {
            audioManager.abandonAudioFocusRequest(audioFocusRequest)
        }
    }
}

/**
 * Is this a transition into or out of [ZoneState.Unmeasured]?
 *
 * Every such pair is announced as **nothing**, and that is a decision rather
 * than an unmatched pair falling off the end of the `when` in
 * [AudioAlertManager.onZoneStateChanged]. We never saw the entry camera, so
 * there is no entry to announce, no average to warn about and no exit to sum up
 * — saying anything would imply we are measuring. See
 * `ZoneDetector.START_WITNESS_ARC_M`.
 *
 * Lifted out of the `when` head so the rule is named and assertable without a
 * TTS engine; pinned by `AudioAlertSilenceTest`. iOS peer: the guard above the
 * pair switch in `AnnouncementPolicy.decide`.
 */
internal fun isUnmeasuredTransition(previousState: ZoneState, newState: ZoneState): Boolean =
    previousState is ZoneState.Unmeasured || newState is ZoneState.Unmeasured

/**
 * How long a spoken provisional entry suppresses another one for the same zone.
 *
 * A candidate that goes quiet for `ZoneDetector.ENTRY_CONFIRM_TIMEOUT_MS` (30 s)
 * and then re-opens is a brand-new candidate as far as the detector is
 * concerned, but the driver does not need to hear the same zone announced twice
 * inside a minute.
 */
internal const val PROVISIONAL_REPEAT_WINDOW_MS = 60_000L

/**
 * Has [zoneId] already been announced provisionally, recently enough that the
 * driver still remembers hearing it?
 *
 * Both halves of the provisional flow ask this: [AudioAlertManager.onProvisionalEntry]
 * to suppress a repeat, and the confirmed `Outside -> InZone` branch to skip the
 * entry line it would otherwise duplicate.
 *
 * The recency clause is not decoration. A candidate that is announced and then
 * abandoned leaves the id set with nothing to clear it, so without the window a
 * genuine entry into that same zone half an hour later would be silently
 * swallowed — the driver would drive a real zone with no announcement at all.
 * Bounding both halves by the same window keeps them in agreement: inside it the
 * driver has heard this zone (whether or not a repeat was suppressed), outside
 * it they have not.
 */
internal fun isProvisionalStillFresh(
    zoneId: String,
    provisionalZoneId: String?,
    provisionalTime: Long,
    now: Long,
    windowMs: Long = PROVISIONAL_REPEAT_WINDOW_MS,
): Boolean = zoneId == provisionalZoneId && now - provisionalTime < windowMs
