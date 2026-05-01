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
                isInitialized = true
                languageJob?.cancel()
                languageJob = scope.launch {
                    settingsRepository.voiceLanguage.collect { lang ->
                        val locale = if (lang == "bg") Locale("bg", "BG") else Locale.ENGLISH
                        tts?.language = locale
                        Log.d(TAG, "tts language set: $lang → $locale")
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
            }
        }
    }

    private suspend fun getSpeedLimit(state: ZoneState.InZone): Int {
        return when (settingsRepository.vehicleType.first()) {
            "truck" -> state.zone.speedLimits.truck
            "bus" -> state.zone.speedLimits.bus
            else -> state.zone.speedLimits.car
        }
    }

    private suspend fun getEntryMessage(road: String, limit: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Влизате в зона за средна скорост. Ограничение $limit."
        } else {
            "Entering average speed zone. Speed limit $limit."
        }
    }

    private suspend fun getWithinLimitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Средна скорост $avgSpeed. В норма."
        } else {
            "Average speed $avgSpeed. Within limit."
        }
    }

    private suspend fun getOverLimitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Внимание: средна скорост $avgSpeed. Намалете."
        } else {
            "Warning: average speed $avgSpeed. Slow down."
        }
    }

    private suspend fun getRecoveredMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Средната скорост е отново в норма. $avgSpeed."
        } else {
            "Back within limit. $avgSpeed."
        }
    }

    private suspend fun getExitMessage(avgSpeed: Int): String {
        return if (settingsRepository.voiceLanguage.first() == "bg") {
            "Излизате от зоната. Средна скорост $avgSpeed."
        } else {
            "Leaving zone. Average speed was $avgSpeed."
        }
    }

    private fun speak(text: String) {
        if (!isInitialized) {
            Log.d(TAG, "speak: TTS not initialized, dropping: \"$text\"")
            return
        }
        Log.d(TAG, "speak: \"$text\"")
        audioManager.requestAudioFocus(audioFocusRequest)
        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            override fun onDone(utteranceId: String?) {
                audioManager.abandonAudioFocusRequest(audioFocusRequest)
            }
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                audioManager.abandonAudioFocusRequest(audioFocusRequest)
            }
        })
        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "srednabg_alert")
    }
}
