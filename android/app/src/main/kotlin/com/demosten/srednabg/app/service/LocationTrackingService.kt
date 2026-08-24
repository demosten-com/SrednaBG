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
import android.provider.Settings
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.demosten.srednabg.R
import com.demosten.srednabg.app.auto.SrednaBGSession
import com.demosten.srednabg.app.data.MapHighlightStore
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.overlay.OverlayController
import com.demosten.srednabg.app.overlay.shouldShowOverlay
import com.demosten.srednabg.app.ui.MainActivity
import com.demosten.srednabg.core.GpsFilter
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.PendingEntryInfo
import com.demosten.srednabg.core.RoadMatcher
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneDetector
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.bearingBetween
import com.demosten.srednabg.core.haversineDistance
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
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
        // Defense-in-depth accuracy gate. Even with GPS-only sources, a single
        // coarse fix (multipath / urban canyon, the gms FLP momentarily falling
        // back to a coarse fix, or the gms SystemLocationSource fallback) would
        // corrupt the position baseline, speed inference, and zone state. Real
        // highway GPS is typically <20 m; we drop fixes worse than this so junk
        // never reaches the pipeline (cell/wifi-grade 100 m–2 km is rejected,
        // while 50 m still admits first-fix cold-start convergence). This brings
        // Android closer to CoreLocation's internal quality filtering on iOS.
        private const val MAX_ACCURACY_M = 50.0
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
    @Inject lateinit var historyRecorder: HistoryRecorder
    @Inject lateinit var mapHighlightStore: MapHighlightStore

    private var zoneDetector: ZoneDetector? = null
    private lateinit var overlayController: OverlayController
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

    // The zone we last spoke a provisional entry for, and when, pending an
    // outcome. Read by trackProvisionalOutcome only — the announcement's own
    // repeat window lives in AudioAlertManager.
    private var provisionallyAnnouncedZoneId: String? = null
    private var provisionallyAnnouncedAtMs: Long = 0L

    // Driver-selected vehicle type, mirrored from SettingsRepository.vehicleType
    // (the same Flow AudioAlertManager reads) and threaded into the detector so
    // the average-speed limit reflects truck/bus/motorcycle, not just car.
    // Defaults to CAR until the first emission, so there's no null/race window.
    @Volatile
    private var currentVehicleType: VehicleType = VehicleType.CAR

    // onStartCommand can fire more than once per service instance (START_STICKY
    // null-intent redelivery after a kill, a repeated START_TRACKING broadcast,
    // a re-tapped start). The auto-stop timer and the zone collector below are
    // one-time setup — relaunching them stacks duplicate timers / detectors /
    // startLocationUpdates. Guard them so they launch only on the first call;
    // the per-call work (startForeground, isTracking, lastActivityMs) still runs
    // every time.
    private var setupStarted = false

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
        // Drop coarse fixes before they touch the position baseline / speed
        // inference / detector. An imprecise fix is worse than none here.
        if (location.hasAccuracy() && location.accuracy > MAX_ACCURACY_M) {
            Log.d(TAG, "Dropping low-accuracy fix: accuracy=${location.accuracy}m > $MAX_ACCURACY_M")
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
        val previousCandidateId = detector.pendingEntryInfo?.zone?.id
        val newState = detector.update(point, currentVehicleType)
        _zoneState.value = newState
        if (previousState::class != newState::class) {
            lastActivityMs = android.os.SystemClock.elapsedRealtime()
        }
        announceProvisionalEntry(previousCandidateId, detector.pendingEntryInfo, newState, point.speed)
        audioAlertManager.onZoneStateChanged(previousState, newState, point.speed)
        val limitKmh = when (newState) {
            is ZoneState.InZone -> currentVehicleType.limit(newState.zone.speedLimits)
            is ZoneState.Exiting -> currentVehicleType.limit(newState.zone.speedLimits)
            // The limit is a fact about the road, known even when the traversal
            // isn't measurable. HistoryRecorder ignores it for Unmeasured (it
            // records nothing), but reporting 0 here would be simply wrong.
            is ZoneState.Unmeasured -> currentVehicleType.limit(newState.zone.speedLimits)
            else -> 0
        }
        historyRecorder.onZoneStateChanged(point, previousState, newState, currentVehicleType, limitKmh)
        adjustGpsInterval(newState, point)
    }

    /**
     * Speak the entry as soon as we are *on* the zone, rather than waiting the
     * [ZoneDetector.ENTRY_CONFIRM_DISTANCE_M] the traversal needs to be
     * confirmed. The measurement is unaffected either way (a confirmed
     * traversal is back-dated to this same candidate's first fix); this only
     * moves the voice to where the driver expects it — the candidate opens up
     * to `RoadMatcher.maxOnRoadDistanceM` *before* the entry camera, because a
     * pre-camera fix's projection clamps to the polyline start.
     *
     * Three conditions, each load-bearing:
     *
     * 1. The candidate is **new** (none before, or a different zone). Extending
     *    an existing candidate must stay silent.
     * 2. [newState] is still `Outside`, i.e. this fix did not itself open the
     *    traversal. A co-located handover bypasses confirmation and confirms on
     *    its first fix, so this leaves that chained `Exiting -> InZone`
     *    announcement — QUEUE_ADD after the exit line — exactly as it was.
     * 3. The candidate's first fix projected within
     *    [ZoneDetector.START_WITNESS_ARC_M] of the start. This is the guard that
     *    keeps the A3/Кочериново phantom silent (its first match projects to arc
     *    282 m in the `parallel_motorway` replay; 289 m on iOS) and makes the promise honest: anything announced here can only
     *    graduate into a *measured* traversal, never a silent
     *    [ZoneState.Unmeasured], because that threshold is exactly what
     *    `witnessedStart` tests.
     */
    private fun announceProvisionalEntry(
        previousCandidateId: String?,
        candidate: PendingEntryInfo?,
        newState: ZoneState,
        speedKmh: Double,
    ) {
        trackProvisionalOutcome(candidate, newState)
        if (candidate == null) return
        if (!isNewProvisionalCandidate(previousCandidateId, candidate, newState)) return
        if (candidate.entryArcM > ZoneDetector.START_WITNESS_ARC_M) {
            Log.d(
                TAG,
                "provisional entry suppressed zone=${candidate.zone.id} " +
                    "arcM=${candidate.entryArcM.toInt()} > ${ZoneDetector.START_WITNESS_ARC_M.toInt()}",
            )
            return
        }
        provisionallyAnnouncedZoneId = candidate.zone.id
        provisionallyAnnouncedAtMs = System.currentTimeMillis()
        audioAlertManager.onProvisionalEntry(candidate.zone, speedKmh)
    }

    /**
     * Close the loop on a provisional announcement: it either graduated into a
     * traversal, or the candidate was dropped and the driver heard an entry
     * that will never appear in History.
     *
     * Only the QA channel cares — nothing is spoken either way (a retraction the
     * driver did not ask for is more confusing than silence). The line exists so
     * `qa/validate-zones.sh` can *count* abandonments across all zones, which is
     * the number that says whether announcing on the candidate was the right
     * trade. Note it counts *attempts*: the announcement itself can still be
     * suppressed downstream (voice off, below MIN_ANNOUNCE_SPEED_KMH), so a
     * scenario that cares about what was actually spoken correlates these with
     * the `speak:` lines.
     */
    private fun trackProvisionalOutcome(candidate: PendingEntryInfo?, newState: ZoneState) {
        val announced = provisionallyAnnouncedZoneId ?: return
        val zoneNow = when (newState) {
            is ZoneState.InZone -> newState.zone.id
            is ZoneState.Unmeasured -> newState.zone.id
            is ZoneState.Exiting -> newState.zone.id
            is ZoneState.Outside -> null
        }
        if (zoneNow == announced) {
            Log.d(TAG, "provisional entry confirmed zone=$announced")
            provisionallyAnnouncedZoneId = null
            return
        }
        // Still pending. A missing or restarted candidate is NOT yet an
        // abandonment: a single fix that falls outside the band or fails the
        // heading test drops the candidate, and the very next fix opens a fresh
        // one for the same zone — seen on a real approach to trakiya-01-east,
        // which restarted once and then confirmed 11 s later. Reporting that as
        // abandoned would inflate the count this line exists to measure.
        //
        // So wait out ZoneDetector.ENTRY_CONFIRM_TIMEOUT_MS, which is the
        // detector's own "this candidate is no longer continuous evidence"
        // deadline — the same clock, rather than a second one invented here.
        // Anything that has not entered by then never will.
        if (candidate?.zone?.id == announced) return
        val elapsed = System.currentTimeMillis() - provisionallyAnnouncedAtMs
        val takenOver = candidate != null || zoneNow != null
        if (!takenOver && elapsed < ZoneDetector.ENTRY_CONFIRM_TIMEOUT_MS) return
        Log.d(TAG, "provisional entry abandoned zone=$announced afterMs=$elapsed")
        provisionallyAnnouncedZoneId = null
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        locationSource = createLocationSource(this, locationListener)
        debugInjector = { loc -> locationListener.onLocation(loc) }
        overlayController = OverlayController(this, lifecycleScope, settingsRepository)
        startOverlayVisibilityWatcher()
        lifecycleScope.launch {
            settingsRepository.vehicleType.collect { v ->
                currentVehicleType = VehicleType.fromSetting(v)
            }
        }
    }

    /**
     * Show the floating overlay only while it's enabled, the special permission
     * is granted, a tracking session is live, and our own UI is backgrounded
     * (chat-head convention). Runs once per service instance; `lifecycleScope`
     * is Main, so the WindowManager calls happen on the main thread.
     */
    private fun startOverlayVisibilityWatcher() {
        val foreground = ProcessLifecycleOwner.get().lifecycle.currentStateFlow
            .map { it.isAtLeast(Lifecycle.State.STARTED) }
        lifecycleScope.launch {
            combine(
                settingsRepository.overlayEnabled,
                isTracking,
                foreground,
            ) { enabled, tracking, appForeground ->
                shouldShowOverlay(
                    enabled = enabled,
                    canDrawOverlays = Settings.canDrawOverlays(this@LocationTrackingService),
                    tracking = tracking,
                    appInBackground = !appForeground,
                )
            }.distinctUntilChanged().collect { visible ->
                if (visible) overlayController.show() else overlayController.hide()
            }
        }
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
        // Tracking owns the map from here on — drop any History "Show on map"
        // highlight so the two features never drive the map at the same time.
        // Single choke point: covers the Home button, the debug receiver's
        // START_TRACKING, and sticky restarts alike.
        mapHighlightStore.clear()
        lastActivityMs = android.os.SystemClock.elapsedRealtime()

        if (setupStarted) return START_STICKY
        setupStarted = true

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
                .distinctZoneCatalog()
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
        overlayController.hide()
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
            // Unmeasured polls at the in-zone rate too. No averaging is happening,
            // but we still want a prompt drop to Outside at the zone end and a
            // prompt open of a co-located successor — whose entry camera *is*
            // crossed, so that next zone is genuinely measurable and must not be
            // missed by a coarse fix.
            state is ZoneState.InZone ||
                state is ZoneState.Unmeasured ||
                state is ZoneState.Exiting -> INTERVAL_IN_ZONE_MS
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
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }
}

/**
 * Gate for detector re-initialization on zone-catalog updates. Full-content
 * comparison, not just IDs: a zone whose limit or centerline moved under a
 * stable ID must still reach the running detector — parity with iOS
 * `ZoneTrackingService.updateZones`.
 */
internal fun Flow<List<Zone>>.distinctZoneCatalog(): Flow<List<Zone>> = distinctUntilChanged()

/**
 * Is this fix the one that should speak a provisional entry for [candidate]?
 *
 * The arc guard is deliberately *not* here — it needs no state and is asserted
 * directly at the call site — but these two clauses do need the previous fix's
 * candidate and the state this fix produced, which is exactly the kind of thing
 * that rots silently inside a service. Lifted out so the rule is named and
 * testable without a location provider, in the same spirit as
 * `shouldShowOverlay` and `isUnmeasuredTransition`.
 *
 * - A candidate that is merely being *extended* must stay silent: it was already
 *   announced on the fix that opened it.
 * - A fix that itself opened the traversal must stay silent here, because the
 *   normal `Outside -> InZone` / `Exiting -> InZone` announcement covers it. The
 *   second case is the co-located handover, which bypasses entry confirmation
 *   entirely and so confirms on the candidate's very first fix — announcing here
 *   as well would speak the next zone's entry twice, and would do it with
 *   QUEUE_FLUSH, cutting off the previous zone's exit-with-average.
 */
internal fun isNewProvisionalCandidate(
    previousCandidateId: String?,
    candidate: PendingEntryInfo,
    newState: ZoneState,
): Boolean = candidate.zone.id != previousCandidateId && newState is ZoneState.Outside
