// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.util.Log
import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.HistoryRetention
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.local.ZoneTraversalEntity
import com.demosten.srednabg.app.data.local.toSamplesJson
import com.demosten.srednabg.core.HistoryStats
import com.demosten.srednabg.core.SpeedSample
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneState
import com.google.gson.Gson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Captures completed average-speed-zone traversals for the History tab. Injected
 * into [LocationTrackingService] and driven from the same site as
 * [AudioAlertManager.onZoneStateChanged], so history mirrors what was (or would
 * have been) announced.
 *
 * Buffering (append while [ZoneState.InZone], finalize on the exit transition)
 * runs entirely on the caller's thread — the location listener — so the buffer
 * needs no synchronization. Only the DB write hops to a background coroutine.
 */
@Singleton
class HistoryRecorder @Inject constructor(
    private val historyRepository: HistoryRepository,
    private val settingsRepository: SettingsRepository,
    private val gson: Gson,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // Mirrored from the retention setting so the hot path never suspends. When
    // retention is "none" we record nothing (the setting-change observer purges
    // existing history separately). Defaults to the setting default's verdict.
    @Volatile
    private var recordingEnabled: Boolean =
        HistoryRetention.fromSetting(SettingsRepository.DEFAULT_HISTORY_RETENTION) != HistoryRetention.NONE

    // The in-progress traversal. Only touched on the location-listener thread.
    private var capture: Capture? = null

    init {
        scope.launch {
            settingsRepository.historyRetention.collect { value ->
                recordingEnabled = HistoryRetention.fromSetting(value) != HistoryRetention.NONE
            }
        }
    }

    private class Capture(
        val zone: Zone,
        val entryTimeMs: Long,
        val samples: MutableList<SpeedSample> = ArrayList(),
    )

    /**
     * @param point the filtered fix that produced [newState].
     * @param limitKmh the vehicle-type-resolved limit for [newState]'s zone, used
     *   for the stored over-limit verdict (matches the exit-chip verdict).
     */
    fun onZoneStateChanged(
        point: com.demosten.srednabg.core.GpsPoint,
        previousState: ZoneState,
        newState: ZoneState,
        vehicleType: VehicleType,
        limitKmh: Int,
    ) {
        if (!recordingEnabled) {
            // Drop any buffer opened before recording was turned off mid-zone.
            capture = null
            return
        }
        when (newState) {
            is ZoneState.InZone -> {
                val open = capture
                if (open == null || open.zone.id != newState.zone.id) {
                    // Starting a fresh traversal. Any still-open buffer for a
                    // different zone means we jumped zones without an Exiting
                    // (not expected — the engine steps through Exiting even at
                    // co-located cameras); drop it rather than mis-attribute it.
                    if (open != null) {
                        Log.w(TAG, "dropping stale buffer for ${open.zone.id}; entered ${newState.zone.id}")
                    }
                    capture = Capture(zone = newState.zone, entryTimeMs = newState.entryTime)
                }
                capture?.samples?.add(SpeedSample(point.timestamp, point.speed))
            }
            is ZoneState.Exiting -> {
                val open = capture
                if (open != null && open.zone.id == newState.zone.id) {
                    finalize(open, exitTimeMs = point.timestamp, finalAvg = newState.finalAvgSpeed, vehicleType, limitKmh)
                }
                capture = null
            }
            is ZoneState.Unmeasured, is ZoneState.Outside -> {
                // The exit is finalized on InZone -> Exiting; by the time Outside
                // arrives the buffer is already closed. Clear defensively.
                //
                // Unmeasured is handled identically and records nothing: we never
                // saw the entry camera, so there is no traversal to attribute
                // samples to. It also cannot reach Exiting (it drops straight to
                // Outside), so no half-open buffer can ever be finalized from it —
                // which is exactly what keeps mid-zone joins out of History.
                capture = null
            }
        }
    }

    private fun finalize(
        capture: Capture,
        exitTimeMs: Long,
        finalAvg: Double?,
        vehicleType: VehicleType,
        limitKmh: Int,
    ) {
        val durationMs = exitTimeMs - capture.entryTimeMs
        if (durationMs < TRANSIENT_EXIT_WINDOW_MS) {
            // Transient blip / very short zone — the same window AudioAlertManager
            // uses to suppress the exit announcement, so history matches the audio.
            Log.d(TAG, "skipping transient traversal ${capture.zone.id} (${durationMs}ms)")
            return
        }
        val samples = capture.samples.toList()
        val (sustainedMin, sustainedMax) = HistoryStats.sustainedExtremes(samples)
        val downsampled = HistoryStats.downsample(samples)
        val entity = ZoneTraversalEntity(
            // Deterministic id (zone + exit ms) mirrors the iOS recorder, so a
            // retried insert REPLACEs the same row instead of duplicating it.
            // Two distinct traversals can't share a zone + exit millisecond.
            id = "${capture.zone.id}-$exitTimeMs",
            zoneId = capture.zone.id,
            road = capture.zone.road,
            roadLatin = capture.zone.roadLatin,
            direction = capture.zone.direction,
            speedLimitKmh = limitKmh,
            vehicleType = vehicleType.name.lowercase(),
            entryTimeMs = capture.entryTimeMs,
            exitTimeMs = exitTimeMs,
            avgSpeedKmh = finalAvg,
            sustainedMinKmh = sustainedMin,
            sustainedMaxKmh = sustainedMax,
            isOverLimit = finalAvg != null && finalAvg > limitKmh,
            distanceM = capture.zone.distanceM,
            samplesJson = downsampled.toSamplesJson(gson),
        )
        scope.launch {
            historyRepository.record(entity)
            Log.i(TAG, "recorded traversal ${entity.zoneId} avg=${entity.avgSpeedKmh} over=${entity.isOverLimit}")
        }
    }

    private companion object {
        const val TAG = "SrednaBG.History"
        // Mirror AudioAlertManager.TRANSIENT_EXIT_WINDOW_MS so a suppressed exit
        // announcement and a skipped history record stay in lock-step.
        const val TRANSIENT_EXIT_WINDOW_MS = 5_000L
    }
}
