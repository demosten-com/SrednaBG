// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.auto

import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.view.Surface
import androidx.car.app.AppManager
import androidx.car.app.CarContext
import androidx.car.app.Screen
import androidx.car.app.SurfaceCallback
import androidx.car.app.SurfaceContainer
import androidx.car.app.model.Action
import androidx.car.app.model.ActionStrip
import androidx.car.app.model.CarIcon
import androidx.car.app.model.Distance
import androidx.car.app.model.Template
import androidx.car.app.navigation.NavigationManager
import androidx.car.app.navigation.NavigationManagerCallback
import androidx.car.app.navigation.model.Destination
import androidx.car.app.navigation.model.Maneuver
import androidx.car.app.navigation.model.NavigationTemplate
import androidx.car.app.navigation.model.RoutingInfo
import androidx.car.app.navigation.model.Step
import androidx.car.app.navigation.model.TravelEstimate
import androidx.car.app.navigation.model.Trip
import androidx.core.graphics.drawable.IconCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.demosten.srednabg.R
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneRepository
import com.demosten.srednabg.app.service.LocationTrackingService
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.snapToZone
import dagger.hilt.android.EntryPointAccessors
import java.time.ZonedDateTime
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

private const val BEARING_MIN_SPEED_KMH = 5.0

private fun normalizeBearing(value: Double): Double {
    if (!value.isFinite()) return 0.0
    val mod = value.mod(360.0)
    return if (mod < 0.0) mod + 360.0 else mod
}

class NavigationScreen(carContext: CarContext) : Screen(carContext) {

    private val entryPoint = EntryPointAccessors.fromApplication(
        carContext.applicationContext,
        AutoEntryPoint::class.java,
    )
    private val zoneRepository: ZoneRepository = entryPoint.zoneRepository()
    private val settingsRepository: SettingsRepository = entryPoint.settingsRepository()

    private val navigationManager: NavigationManager =
        carContext.getCarService(NavigationManager::class.java)

    private val mapRenderer = MapRenderer()
    private val speedOverlay = SpeedOverlay()

    private val overlayLabels: OverlayLabels by lazy {
        OverlayLabels(
            overLimit = carContext.getString(R.string.status_over_limit),
            withinLimit = carContext.getString(R.string.status_within_limit),
            monitoringHint = carContext.getString(R.string.auto_monitoring_hint),
            nowSpeedFormat = carContext.getString(R.string.status_now_speed),
            kmhLabel = carContext.getString(R.string.current_speed_label),
            zoneComplete = carContext.getString(R.string.zone_complete),
            maxForRemainderFormat = carContext.getString(R.string.max_for_remainder_format),
        )
    }

    private var surface: Surface? = null
    private var surfaceWidth = 0
    private var surfaceHeight = 0
    private var visibleArea: Rect? = null
    private var stableArea: Rect? = null

    private var zones: List<Zone> = emptyList()
    private var currentZoneState: ZoneState = ZoneState.Outside
    private var currentPosition: GpsPoint? = null
    private var isMuted = false
    private var isNavigating = false
    private var userZoomOverride: Double? = null
    private var isHeadingUp = false
    // Last bearing seen while moving; held while stopped so the map doesn't slam
    // back to north at traffic lights.
    private var effectiveBearing = 0.0

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private val mainHandler = Handler(Looper.getMainLooper())

    private fun safeInvalidate() {
        mainHandler.post {
            try {
                invalidate()
            } catch (_: Exception) {}
        }
    }

    private val surfaceCallback = object : SurfaceCallback {
        override fun onSurfaceAvailable(surfaceContainer: SurfaceContainer) {
            surface = surfaceContainer.surface
            surfaceWidth = surfaceContainer.width
            surfaceHeight = surfaceContainer.height
            surfaceCallbackActive = true
            renderFrame()
        }

        override fun onVisibleAreaChanged(visibleArea: Rect) {
            this@NavigationScreen.visibleArea = visibleArea
            renderFrame()
        }

        override fun onStableAreaChanged(stableArea: Rect) {
            this@NavigationScreen.stableArea = stableArea
            renderFrame()
        }

        override fun onSurfaceDestroyed(surfaceContainer: SurfaceContainer) {
            surface = null
        }

        override fun onScroll(distanceX: Float, distanceY: Float) {}

        override fun onScale(focusX: Float, focusY: Float, scaleFactor: Float) {}
    }

    // Flipped to true only when the host actually calls onSurfaceAvailable.
    // The Car App library logs "Could not retrieve host while dispatching call
    // setSurfaceListener" without throwing, so we can't trust a bare
    // setSurfaceCallback() call to have landed — we have to retry until the
    // host calls us back.
    private var surfaceCallbackActive = false

    private val registrationRetries = floatArrayOf(150f, 400f, 900f, 1800f, 3500f)
    private var retryIndex = 0

    private fun scheduleSurfaceCallbackRegistration() {
        if (surfaceCallbackActive) return
        try {
            carContext.getCarService(AppManager::class.java)
                .setSurfaceCallback(surfaceCallback)
        } catch (_: Exception) {}
        if (retryIndex < registrationRetries.size) {
            val delay = registrationRetries[retryIndex].toLong()
            retryIndex++
            mainHandler.postDelayed({ scheduleSurfaceCallbackRegistration() }, delay)
        }
    }

    init {
        lifecycle.addObserver(LifecycleEventObserver { _, event ->
            when (event) {
                // ON_CREATE fires before the host IPC is ready on some AA
                // hosts (DHU especially) and setSurfaceCallback silently fails
                // with "Could not retrieve host while dispatching call
                // setSurfaceListener". Kick off a retry chain at ON_START; the
                // chain stops once onSurfaceAvailable actually fires.
                Lifecycle.Event.ON_START -> {
                    retryIndex = 0
                    scheduleSurfaceCallbackRegistration()
                }
                Lifecycle.Event.ON_DESTROY -> {
                    scope.cancel()
                    try {
                        navigationManager.clearNavigationManagerCallback()
                        if (isNavigating) {
                            navigationManager.navigationEnded()
                        }
                    } catch (_: Exception) {}
                }
                else -> {}
            }
        })

        navigationManager.setNavigationManagerCallback(object : NavigationManagerCallback {
            override fun onStopNavigation() {
                isNavigating = false
            }

            override fun onAutoDriveEnabled() {}
        })

        scope.launch {
            LocationTrackingService.zoneState.collect { state ->
                val previous = currentZoneState
                currentZoneState = state
                if (previous::class != state::class) {
                    userZoomOverride = null
                }
                handleStateTransition(previous, state)
                renderFrame()
                safeInvalidate()
            }
        }

        scope.launch {
            LocationTrackingService.currentPosition.collect { position ->
                currentPosition = position
                if (position != null && position.speed > BEARING_MIN_SPEED_KMH && position.bearing.isFinite()) {
                    effectiveBearing = normalizeBearing(position.bearing)
                }
                renderFrame()
            }
        }

        scope.launch {
            settingsRepository.mapHeadingUp.collect { headingUp ->
                if (headingUp != isHeadingUp) {
                    isHeadingUp = headingUp
                    renderFrame()
                    safeInvalidate()
                }
            }
        }

        scope.launch {
            zoneRepository.ensureLoaded()
            zoneRepository.zones.collect { zoneList ->
                zones = zoneList
                renderFrame()
            }
        }

        scope.launch {
            isMuted = !settingsRepository.voiceEnabled.first()
        }
    }

    override fun onGetTemplate(): Template {
        val builder = NavigationTemplate.Builder()
            .setActionStrip(buildActionStrip())
            .setMapActionStrip(buildMapActionStrip())

        when (val state = currentZoneState) {
            is ZoneState.Outside -> {
                // No navigation info — just show the map
            }
            is ZoneState.InZone -> {
                val speedLimit = getSpeedLimit(state.zone)
                val step = Step.Builder(state.zone.road)
                    .setManeuver(Maneuver.Builder(Maneuver.TYPE_STRAIGHT).build())
                    .setCue(carContext.getString(R.string.auto_routing_cue, state.avgSpeed.orDash(), speedLimit))
                    .build()
                val distance = Distance.create(state.distanceRemaining, Distance.UNIT_METERS)
                builder.setNavigationInfo(
                    RoutingInfo.Builder()
                        .setCurrentStep(step, distance)
                        .build(),
                )
            }
            is ZoneState.Exiting -> {
                val step = Step.Builder(state.zone.road)
                    .setManeuver(Maneuver.Builder(Maneuver.TYPE_DESTINATION).build())
                    .setCue(carContext.getString(R.string.auto_final_speed, state.finalAvgSpeed.orDash()))
                    .build()
                builder.setNavigationInfo(
                    RoutingInfo.Builder()
                        .setCurrentStep(step, Distance.create(0.0, Distance.UNIT_METERS))
                        .build(),
                )
            }
        }

        return builder.build()
    }

    fun cleanup() {
        scope.cancel()
    }

    private fun handleStateTransition(previous: ZoneState, current: ZoneState) {
        try {
            when {
                previous is ZoneState.Outside && current is ZoneState.InZone -> {
                    navigationManager.navigationStarted()
                    isNavigating = true
                    updateTrip(current)
                }
                current is ZoneState.InZone -> {
                    if (isNavigating) updateTrip(current)
                }
                current is ZoneState.Exiting -> {
                    if (isNavigating) {
                        navigationManager.navigationEnded()
                        isNavigating = false
                    }
                }
            }
        } catch (_: Exception) {
            // NavigationManager calls may fail if another app is navigating
        }
    }

    private fun updateTrip(state: ZoneState.InZone) {
        try {
            val distance = Distance.create(state.distanceRemaining, Distance.UNIT_METERS)
            val remainingSec = state.speedStatus.timeRemaining.toLong().coerceAtLeast(0)
            val eta = ZonedDateTime.now().plusSeconds(remainingSec)
            val travelEstimate = TravelEstimate.Builder(distance, eta)
                .setRemainingTimeSeconds(remainingSec)
                .build()
            val step = Step.Builder(state.zone.road)
                .setManeuver(Maneuver.Builder(Maneuver.TYPE_STRAIGHT).build())
                .build()
            val destination = Destination.Builder()
                .setName(carContext.getString(R.string.auto_zone_end))
                .setAddress(state.zone.road)
                .build()
            val trip = Trip.Builder()
                .addDestination(destination, travelEstimate)
                .addStep(step, travelEstimate)
                .setLoading(false)
                .build()
            navigationManager.updateTrip(trip)
        } catch (_: Exception) {}
    }

    private fun renderFrame() {
        val currentSurface = surface ?: return
        if (!currentSurface.isValid) return

        val canvas = try {
            currentSurface.lockHardwareCanvas()
        } catch (_: Exception) {
            try { currentSurface.lockCanvas(null) } catch (_: Exception) { return }
        } ?: return

        try {
            val safeArea = stableArea ?: visibleArea ?: Rect(0, 0, canvas.width, canvas.height)
            val activeZone = (currentZoneState as? ZoneState.InZone)?.zone
            val displayPosition = snapToZone(currentPosition, currentZoneState)

            mapRenderer.draw(
                canvas = canvas,
                zones = zones,
                activeZone = activeZone,
                position = displayPosition,
                zoneState = currentZoneState,
                zoomOverride = userZoomOverride,
                headingUp = isHeadingUp,
                bearing = effectiveBearing,
            )

            speedOverlay.draw(
                canvas = canvas,
                stableArea = safeArea,
                zoneState = currentZoneState,
                speedLimit = activeZone?.let { getSpeedLimit(it) } ?: 0,
                currentSpeedKmh = currentPosition?.speed,
                labels = overlayLabels,
            )
        } finally {
            try {
                currentSurface.unlockCanvasAndPost(canvas)
            } catch (_: Exception) {
                // Surface may have been torn down mid-draw; swallow so we don't
                // propagate into the coroutine that triggered this render.
            }
        }
    }

    private fun getSpeedLimit(zone: Zone): Int {
        val vehicleType = runBlocking { settingsRepository.vehicleType.first() }
        return when (vehicleType) {
            "truck" -> zone.speedLimits.truck
            "bus" -> zone.speedLimits.bus
            else -> zone.speedLimits.car
        }
    }

    private fun buildMapActionStrip(): ActionStrip {
        val orientationIconRes = if (isHeadingUp) {
            R.drawable.ic_map_orientation_heading
        } else {
            R.drawable.ic_map_orientation_north
        }
        return ActionStrip.Builder()
            .addAction(
                Action.Builder()
                    .setIcon(
                        CarIcon.Builder(
                            IconCompat.createWithResource(carContext, orientationIconRes),
                        ).build(),
                    )
                    .setOnClickListener {
                        scope.launch {
                            settingsRepository.setMapHeadingUp(!isHeadingUp)
                        }
                    }
                    .build(),
            )
            .addAction(
                Action.Builder()
                    .setIcon(
                        CarIcon.Builder(
                            IconCompat.createWithResource(carContext, R.drawable.ic_add),
                        ).build(),
                    )
                    .setOnClickListener { adjustZoom(1.0) }
                    .build(),
            )
            .addAction(
                Action.Builder()
                    .setIcon(
                        CarIcon.Builder(
                            IconCompat.createWithResource(carContext, R.drawable.ic_remove),
                        ).build(),
                    )
                    .setOnClickListener { adjustZoom(-1.0) }
                    .build(),
            )
            .build()
    }

    private fun adjustZoom(delta: Double) {
        val activeZone = (currentZoneState as? ZoneState.InZone)?.zone
        val width = surfaceWidth.coerceAtLeast(1)
        val height = surfaceHeight.coerceAtLeast(1)
        val base = userZoomOverride ?: if (activeZone != null) {
            MercatorProjection().computeZoomToFit(activeZone.centerline, width, height, 100)
        } else {
            12.0
        }
        userZoomOverride = (base + delta).coerceIn(4.0, 18.0)
        renderFrame()
    }

    private fun buildActionStrip(): ActionStrip {
        val muteIconRes = if (isMuted) R.drawable.ic_volume_off else R.drawable.ic_volume_up
        return ActionStrip.Builder()
            .addAction(
                Action.Builder()
                    .setIcon(
                        CarIcon.Builder(
                            IconCompat.createWithResource(carContext, muteIconRes),
                        ).build(),
                    )
                    .setOnClickListener {
                        isMuted = !isMuted
                        scope.launch {
                            settingsRepository.setVoiceEnabled(!isMuted)
                        }
                        safeInvalidate()
                    }
                    .build(),
            )
            .addAction(
                Action.Builder()
                    .setTitle(carContext.getString(R.string.auto_settings))
                    .setOnClickListener {
                        try {
                            carContext.startCarApp(
                                carContext.packageManager.getLaunchIntentForPackage(carContext.packageName)!!,
                            )
                        } catch (_: Exception) {}
                    }
                    .build(),
            )
            .build()
    }
}
