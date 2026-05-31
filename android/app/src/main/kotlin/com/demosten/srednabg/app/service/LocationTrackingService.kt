// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.demosten.srednabg.R
import com.demosten.srednabg.app.auto.SrednaBGSession
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.ui.MainActivity
import com.demosten.srednabg.core.GpsFilter
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.RoadMatcher
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneDetector
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.bearingBetween
import com.demosten.srednabg.core.haversineDistance
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.distinctUntilChangedBy
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class LocationTrackingService : LifecycleService() {

    companion object {
        private const val TAG = "SrednaBG.Loc"
        private const val NOTIFICATION_ID = 1
        private const val CHANNEL_ID = "tracking_channel"
        private const val INTERVAL_IN_ZONE_MS = 1000L
        private const val INTERVAL_NEAR_ZONE_MS = 2000L
        private const val INTERVAL_FAR_MS = 5000L
        private const val NEAR_ZONE_DISTANCE_M = 2000.0
        private const val MIN_BEARING_DELTA_M = 5.0
        private const val MIN_SPEED_INFER_M = 5.0
        private const val MIN_SPEED_INFER_DT_SEC = 0.2
        private const val MAX_INFERRED_SPEED_KMH = 250.0
        // FLP can deliver a cached "last known" fix as the first update —
        // possibly from a wifi/cell-derived position tens to hundreds of
        // meters off from the user's actual location. A stale fix as the
        // seed for lastRawLat/Lng would make the next real fix's deltaM
        // spurious, producing a phantom speed that clamps at
        // MAX_INFERRED_SPEED_KMH and then sticks (the deltaM<5m guard
        // below never clears the stale value on stationary samples).
        // The real cached fixes we want to reject are minutes-to-hours old;
        // 10 s is loose enough that normal FLP delivery (which on real
        // devices can run 3–5 s behind the requested 5 s interval) is not
        // mis-classified, but tight enough that "last known" caches still
        // get caught.
        private const val MAX_FIX_AGE_MS = 10_000L
        private const val DEBUG_PROVIDER = "debug-gpx"
        // Longer than the 5s far-zone FLP interval so one debug point is
        // enough to mask the next real FLP tick. Shorter than a reasonable
        // manual-stop gap so FLP resumes quickly once the feeder stops.
        private const val DEBUG_FEED_SUPPRESS_MS = 15_000L
        private const val AUTO_STOP_CHECK_INTERVAL_MS = 60_000L

        private val _zoneState = MutableStateFlow<ZoneState>(ZoneState.Outside)
        val zoneState: StateFlow<ZoneState> = _zoneState

        private val _isTracking = MutableStateFlow(false)
        val isTracking: StateFlow<Boolean> = _isTracking

        private val _currentPosition = MutableStateFlow<GpsPoint?>(null)
        val currentPosition: StateFlow<GpsPoint?> = _currentPosition

        // Debug-only hook for the GPX feeder. Set while the service is
        // attached so the debug receiver can inject a point without binding.
        @Volatile
        internal var debugInjector: ((android.location.Location) -> Unit)? = null
    }

    @Inject lateinit var zoneRepository: ZoneRepository
    @Inject lateinit var settingsRepository: SettingsRepository
    @Inject lateinit var audioAlertManager: AudioAlertManager

    private var zoneDetector: ZoneDetector? = null
    private val gpsFilter = GpsFilter()
    private var currentZones: List<Zone> = emptyList()
    private var currentIntervalMs = INTERVAL_FAR_MS
    private lateinit var locationSource: LocationSource
    private var lastRawLat: Double = Double.NaN
    private var lastRawLng: Double = Double.NaN
    private var lastRawTimestampMs: Long = 0
    private var lastInferredBearing: Double = Double.NaN
    private var lastInferredSpeedKmh: Double = 0.0
    // Grace window: while a debug GPX feed is flowing, real FLP updates would
    // yank the dot back to the phone's actual location between injected
    // points. When the last point we processed came from the debug provider,
    // suppress real FLP updates for DEBUG_FEED_SUPPRESS_MS; a fresh debug
    // point resets the window, stopping the feeder lets FLP resume.
    private var lastDebugFeedMs: Long = 0

    // Inactivity auto-stop: monotonic ms of the most recent "activity" —
    // tracking start or any zone state transition. Compared against
    // SettingsRepository.autoStopHours on a 60 s timer; when exceeded, the
    // service stops itself so a forgotten-in-background app doesn't drain
    // the battery indefinitely.
    @Volatile
    private var lastActivityMs: Long = 0L

    private val locationListener = LocationUpdateListener { location ->
        val fromDebug = location.provider == DEBUG_PROVIDER
        if (fromDebug) {
            lastDebugFeedMs = android.os.SystemClock.elapsedRealtime()
        } else if (android.os.SystemClock.elapsedRealtime() - lastDebugFeedMs < DEBUG_FEED_SUPPRESS_MS) {
            // Silent drop — logging every suppressed FLP tick would spam.
            return@LocationUpdateListener
        }
        Log.d(
            TAG,
            "onLocation: lat=${location.latitude} lng=${location.longitude} " +
                "speed=${location.speed} accuracy=${location.accuracy} " +
                "provider=${location.provider} mock=${location.isFromMockProvider}",
        )
        val detector = zoneDetector ?: run {
            Log.w(TAG, "onLocation: zoneDetector is null — dropping")
            return@LocationUpdateListener
        }
        val deltaM = if (!lastRawLat.isNaN()) haversineDistance(
            lastRawLat, lastRawLng, location.latitude, location.longitude,
        ) else 0.0
        val bearing: Double = when {
            location.hasBearing() -> location.bearing.toDouble()
            !lastRawLat.isNaN() && deltaM >= MIN_BEARING_DELTA_M -> {
                lastInferredBearing = bearingBetween(
                    lastRawLat, lastRawLng, location.latitude, location.longitude,
                )
                lastInferredBearing
            }
            else -> lastInferredBearing
        }
        val fixAgeMs = (android.os.SystemClock.elapsedRealtimeNanos() - location.elapsedRealtimeNanos) / 1_000_000
        val freshFix = fixAgeMs in 0L..MAX_FIX_AGE_MS
        if (freshFix && lastRawTimestampMs > 0 && location.time > lastRawTimestampMs) {
            val dtSec = (location.time - lastRawTimestampMs) / 1000.0
            if (deltaM >= MIN_SPEED_INFER_M && dtSec >= MIN_SPEED_INFER_DT_SEC && dtSec <= 30.0) {
                val raw = (deltaM / dtSec) * 3.6
                lastInferredSpeedKmh = raw.coerceAtMost(MAX_INFERRED_SPEED_KMH)
            } else if (deltaM < MIN_SPEED_INFER_M) {
                // No motion this sample — don't keep showing the previous
                // inferred reading. Without this, a one-off position-delta
                // spike (e.g. GPS cold-start jump) clamps at 250 and stays
                // pinned because the deltaM>=MIN_SPEED_INFER_M branch never
                // re-fires while the user is stationary.
                lastInferredSpeedKmh = 0.0
            }
        }
        // GPS Doppler-derived speed has its own noise floor — chips report
        // ~0.3–1.5 m/s while sitting still. Android exposes a 68%-confidence
        // accuracy alongside the speed; when the reported value is below
        // that bound, "0" is statistically consistent with the measurement
        // so we suppress it. minSdk=26 so hasSpeedAccuracy() is unconditional.
        val rawSpeedMs = if (location.hasSpeed()) location.speed.toDouble() else 0.0
        val speedAccMs = if (location.hasSpeedAccuracy()) {
            location.speedAccuracyMetersPerSecond.toDouble()
        } else {
            Double.NaN
        }
        val withinNoise = !speedAccMs.isNaN() && rawSpeedMs < speedAccMs
        val reportedSpeedKmh = if (withinNoise) 0.0 else rawSpeedMs * 3.6
        // Prefer whichever is larger — FLP on the emulator stamps a near-zero
        // speed even when positions move, so fall back to the position-delta
        // derivation. Real GPS is consistent between the two, so max() is a
        // no-op there.
        val speedKmh = kotlin.math.max(reportedSpeedKmh, lastInferredSpeedKmh)
        if (freshFix) {
            lastRawLat = location.latitude
            lastRawLng = location.longitude
            lastRawTimestampMs = location.time
        }
        val rawPoint = GpsPoint(
            lat = location.latitude,
            lng = location.longitude,
            speed = speedKmh,
            timestamp = location.time,
            bearing = if (bearing.isNaN()) 0.0 else bearing,
            accuracy = if (location.hasAccuracy()) location.accuracy.toDouble() else null,
        )
        val point = gpsFilter.filter(rawPoint)
        _currentPosition.value = point
        Log.d(
            TAG,
            "displaySpeed: kmh=${point.speed} inferredKmh=$lastInferredSpeedKmh " +
                "reportedKmh=$reportedSpeedKmh rawMs=$rawSpeedMs accMs=$speedAccMs " +
                "fixAgeMs=$fixAgeMs fresh=$freshFix",
        )
        if (bearing.isNaN()) {
            // No bearing yet — publish the position so the map can center on
            // the user, but skip the zone detector so we don't false-match a
            // zone whose polylineBearing happens to be within 45° of the
            // default bearing.
            return@LocationUpdateListener
        }
        val previousState = detector.state
        val newState = detector.update(point)
        _zoneState.value = newState
        if (previousState::class != newState::class) {
            lastActivityMs = android.os.SystemClock.elapsedRealtime()
        }
        audioAlertManager.onZoneStateChanged(previousState, newState, point.speed)
        adjustGpsInterval(newState, point)
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        locationSource = createLocationSource(this, locationListener)
        debugInjector = { loc -> locationListener.onLocation(loc) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        Log.d(TAG, "onStartCommand startId=$startId")
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            createNotification(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
        )
        _isTracking.value = true
        lastActivityMs = android.os.SystemClock.elapsedRealtime()

        lifecycleScope.launch {
            while (isActive) {
                val debugSeconds = settingsRepository.debugAutoStopSeconds.first()
                val checkIntervalMs = if (debugSeconds != null && debugSeconds in 1..60) {
                    1_000L
                } else {
                    AUTO_STOP_CHECK_INTERVAL_MS
                }
                delay(checkIntervalMs)
                val thresholdMs = if (debugSeconds != null && debugSeconds > 0) {
                    debugSeconds * 1_000L
                } else {
                    val hours = settingsRepository.autoStopHours.first()
                    if (hours <= 0) continue
                    hours * 3_600_000L
                }
                val elapsedMs = android.os.SystemClock.elapsedRealtime() - lastActivityMs
                if (elapsedMs > thresholdMs) {
                    val elapsedS = elapsedMs / 1000
                    val thresholdS = thresholdMs / 1000
                    Log.i(TAG, "auto-stop: idle for ${elapsedS}s (threshold=${thresholdS}s) — stopping")
                    stopSelf()
                    break
                }
            }
        }

        lifecycleScope.launch {
            Log.d(TAG, "ensureLoaded start")
            zoneRepository.ensureLoaded()
            Log.d(TAG, "ensureLoaded done; collecting zones")
            var firstInit = true
            zoneRepository.zones
                .distinctUntilChangedBy { zones -> zones.map { it.id }.toSet() }
                .collect { zones ->
                    Log.d(TAG, "zones changed (n=${zones.size}); ${if (firstInit) "initializing" else "re-initializing"} detector")
                    initializeDetector(zones)
                    if (firstInit) {
                        firstInit = false
                        startLocationUpdates()
                    }
                }
        }

        lifecycleScope.launch {
            audioAlertManager.initialize()
        }

        return START_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
        if (SrednaBGSession.isActive) {
            Log.d(TAG, "onTaskRemoved: AA session active, keeping service alive")
            return
        }
        Log.d(TAG, "onTaskRemoved: stopping service")
        stopSelf()
    }

    override fun onDestroy() {
        debugInjector = null
        locationSource.stop()
        _isTracking.value = false
        _zoneState.value = ZoneState.Outside
        _currentPosition.value = null
        zoneDetector?.reset()
        lastRawLat = Double.NaN
        lastRawLng = Double.NaN
        lastRawTimestampMs = 0
        lastInferredBearing = Double.NaN
        lastInferredSpeedKmh = 0.0
        audioAlertManager.shutdown()
        super.onDestroy()
    }

    private fun initializeDetector(zones: List<Zone>) {
        val previousState = zoneDetector?.state
        currentZones = zones
        zoneDetector = ZoneDetector(zones)
        gpsFilter.reset()
        if (previousState != null) {
            _zoneState.value = ZoneState.Outside
        }
    }

    private fun startLocationUpdates() {
        requestLocationWithInterval(INTERVAL_FAR_MS)
    }

    private fun requestLocationWithInterval(intervalMs: Long) {
        Log.d(TAG, "requestLocationWithInterval intervalMs=$intervalMs")
        locationSource.requestUpdates(intervalMs)
        currentIntervalMs = intervalMs
    }

    private fun adjustGpsInterval(state: ZoneState, point: GpsPoint) {
        val desiredInterval = when {
            state is ZoneState.InZone || state is ZoneState.Exiting -> INTERVAL_IN_ZONE_MS
            isNearAnyZone(point) -> INTERVAL_NEAR_ZONE_MS
            else -> INTERVAL_FAR_MS
        }
        if (desiredInterval != currentIntervalMs) {
            requestLocationWithInterval(desiredInterval)
        }
    }

    private fun isNearAnyZone(point: GpsPoint): Boolean {
        return currentZones.any { zone ->
            RoadMatcher.distanceToZoneStart(point, zone) < NEAR_ZONE_DISTANCE_M ||
                RoadMatcher.distanceToZoneEnd(point, zone) < NEAR_ZONE_DISTANCE_M
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_tracking),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notification_channel_tracking_description)
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    private fun createNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_tracking_title))
            .setContentText(getString(R.string.notification_tracking_text))
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }
}
