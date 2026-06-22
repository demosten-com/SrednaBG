// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.ui.util.SpeechNumbers
import com.demosten.srednabg.core.VehicleType
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
    }

    private var tts: TextToSpeech? = null
    private var isInitialized = false
    private var lastAnnouncementTime = 0L
    private var lastEntryTime = 0L
    private var languageJob: Job? = null
    // Outstanding TTS utterances. A chained pair (exit-with-average then
    // next-zone entry at co-located cameras) shares one audio-focus session;
    // focus is only abandoned when the queue drains, so QUEUE_ADD speech isn't
    // cut off by an early onDone from the first utterance.
    private var pendingUtterances = 0
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    private val audioManager by lazy { context.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    private val audioFocusRequest by lazy {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
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
                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {}
                    override fun onDone(utteranceId: String?) = onUtteranceFinished()
                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) = onUtteranceFinished()
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
                previousState is ZoneState.Outside && newState is ZoneState.InZone -> {
                    val limit = getSpeedLimit(newState)
                    val now = System.currentTimeMillis()
                    lastEntryTime = now
                    lastAnnouncementTime = now
                    speak(getEntryMessage(newState.zone.road, limit))
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
                    speak(getEntryMessage(newState.zone.road, limit), TextToSpeech.QUEUE_ADD)
                }
            }
        }
    }

    private suspend fun getSpeedLimit(state: ZoneState.InZone): Int {
        val vehicleType = VehicleType.fromSetting(settingsRepository.vehicleType.first())
        return vehicleType.limit(state.zone.speedLimits)
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
        Log.d(TAG, "speak: \"$text\"")
        audioManager.requestAudioFocus(audioFocusRequest)
        // QUEUE_FLUSH wipes anything still queued, so reset the outstanding count;
        // QUEUE_ADD appends, so add to it. The shared utterance id is fine — the
        // listener counts onDone/onError callbacks, not ids.
        pendingUtterances = if (queueMode == TextToSpeech.QUEUE_FLUSH) 1 else pendingUtterances + 1
        val result = tts?.speak(text, queueMode, null, "srednabg_alert")
        if (result != TextToSpeech.SUCCESS) {
            // A rejected enqueue never reaches the utterance listener, so undo
            // its count here or the audio focus stays held (other apps ducked).
            Log.w(TAG, "speak: enqueue failed (result=$result)")
            onUtteranceFinished()
        }
    }

    private fun onUtteranceFinished() {
        pendingUtterances = (pendingUtterances - 1).coerceAtLeast(0)
        if (pendingUtterances == 0) {
            audioManager.abandonAudioFocusRequest(audioFocusRequest)
        }
    }
}
