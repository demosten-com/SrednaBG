// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.Gravity
import androidx.annotation.DrawableRes
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CenterFocusStrong
import androidx.compose.material.icons.filled.Explore
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SmallFloatingActionButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.R
import com.demosten.srednabg.app.ui.components.ZoneStatusChip
import com.demosten.srednabg.app.ui.viewmodel.MapCameraSnapshot
import com.demosten.srednabg.app.ui.viewmodel.ZoneMapViewModel
import com.demosten.srednabg.core.GpsPoint
import com.demosten.srednabg.core.MapTheme
import com.demosten.srednabg.core.Zone
import com.demosten.srednabg.core.ZoneState
import com.demosten.srednabg.core.ZONE_COLOR_GREEN
import com.demosten.srednabg.core.ZONE_COLOR_NEUTRAL
import com.demosten.srednabg.core.ZONE_COLOR_RED
import com.demosten.srednabg.core.bearingBetween
import com.demosten.srednabg.core.zoneStatusColor
import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource

private const val ZONES_SOURCE_ID = "zones-source"
private const val ZONES_INACTIVE_LAYER_ID = "zones-inactive-layer"
private const val ZONES_ACTIVE_LAYER_ID = "zones-active-layer"
private const val ZONE_ID_PROP = "id"
private const val ACTIVE_ID_SENTINEL = "__no_active_zone__"
private const val INACTIVE_COLOR = "#1565C0"
private const val ACTIVE_COLOR = "#D32F2F"

private const val USER_SOURCE_ID = "user-position-source"
private const val USER_LAYER_ID = "user-position-layer"
private const val USER_ARROW_ICON = "user-arrow"

private const val ENDPOINTS_SOURCE_ID = "zone-endpoints-source"
private const val ENDPOINTS_START_LAYER_ID = "zone-endpoints-start-layer"
private const val ENDPOINTS_END_LAYER_ID = "zone-endpoints-end-layer"
private const val ENDPOINT_PROP = "endpoint"
private const val ENDPOINT_START = "start"
private const val ENDPOINT_END = "end"
private const val ENDPOINT_START_COLOR = "#66BB6A"
private const val ENDPOINT_END_COLOR = "#EF5350"

// Speeds below this drop bearing rotation so the arrow doesn't spin while idle.
private const val BEARING_MIN_SPEED_KMH = 5.0
private const val ZONE_FIT_PADDING_PX = 128
private const val USER_FOLLOW_ZOOM = 14.0
private const val FOLLOW_EASE_DURATION_MS = 250

@Composable
fun ZoneMapScreen(viewModel: ZoneMapViewModel = hiltViewModel()) {
    val zones by viewModel.zones.collectAsStateWithLifecycle()
    val isSyncing by viewModel.isSyncing.collectAsStateWithLifecycle()
    val currentPosition by viewModel.currentPosition.collectAsStateWithLifecycle()
    val displayPosition by viewModel.displayPosition.collectAsStateWithLifecycle()
    val activeZoneId by viewModel.activeZoneId.collectAsStateWithLifecycle()
    val zoneState by viewModel.zoneState.collectAsStateWithLifecycle()
    val resolvedHighlight by viewModel.resolvedHighlight.collectAsStateWithLifecycle()
    val mapHeadingUp by viewModel.mapHeadingUp.collectAsStateWithLifecycle()
    val mapZoomOverride by viewModel.mapZoomOverride.collectAsStateWithLifecycle()
    val debugMaxSpeedOverride by viewModel.debugMaxSpeedOverride.collectAsStateWithLifecycle()
    val vehicleType by viewModel.vehicleType.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    // Follow mode lives in the VM so it survives leaving the Map tab / app
    // backgrounding (the screen's composition — and any local state — is
    // disposed by the NavHost when another tab is selected).
    val isFollowing by viewModel.isFollowing.collectAsStateWithLifecycle()
    // Last bearing seen while speed was above the noise threshold — held while stopped so
    // the map doesn't snap back to north at traffic lights.
    var effectiveBearing by remember { mutableStateOf(0.0) }

    LaunchedEffect(displayPosition) {
        val point = displayPosition ?: return@LaunchedEffect
        if (point.speed > BEARING_MIN_SPEED_KMH && point.bearing.isFinite()) {
            effectiveBearing = normalizeBearing(point.bearing)
        }
    }

    // Re-engage follow once on (re-)entry if the user previously chose heading-up,
    // so the camera bearing matches the persisted preference instead of the
    // freshly-initialised MapView's default north-up.
    var hasRestoredFollowOnEnter by remember { mutableStateOf(false) }
    LaunchedEffect(mapHeadingUp, displayPosition) {
        if (hasRestoredFollowOnEnter) return@LaunchedEffect
        if (!mapHeadingUp) return@LaunchedEffect
        if (displayPosition == null) return@LaunchedEffect
        viewModel.setFollowing(true)
        hasRestoredFollowOnEnter = true
    }

    val mapTheme by viewModel.mapTheme.collectAsStateWithLifecycle()
    val activity = remember(context) { context.findActivity() }
    if (activity != null) {
        // The activity is edge-to-edge globally (see MainActivity); the only
        // per-screen concern here is keeping the status-bar icon contrast in
        // sync with the resolved MapTheme so they stay legible against the
        // tile colors. Capture the original on enter and restore on dispose.
        DisposableEffect(activity) {
            val window = activity.window
            val controller = WindowCompat.getInsetsController(window, window.decorView)
            val originalLightStatusBars = controller.isAppearanceLightStatusBars
            onDispose {
                controller.isAppearanceLightStatusBars = originalLightStatusBars
            }
        }
        LaunchedEffect(activity, mapTheme) {
            val window = activity.window
            val controller = WindowCompat.getInsetsController(window, window.decorView)
            controller.isAppearanceLightStatusBars = (mapTheme == MapTheme.LIGHT)
        }
    }
    // Bumped after every successful style (re)load so the DisposableEffects
    // that draw zones / endpoints / user arrow re-fire and reapply their
    // GeoJSON state — `setStyle` wipes all sources and layers, so without
    // this the overlays would silently disappear on a theme swap.
    var styleEpoch by remember { mutableStateOf(0) }
    // Snapshot once: if a previous Map session left a camera state in the VM,
    // restore it so tab-switching doesn't yank the user back to the default
    // Bulgaria-wide zoom or a fresh zone-fit.
    val initialCameraSnapshot = remember { viewModel.cameraSnapshot.value }
    val initialZoomOverride = remember { viewModel.mapZoomOverride.value }
    val mapView = remember {
        // getInstance must run once before any MapView is constructed; doing it
        // here (rather than in the composable body) keeps it off the recomposition
        // path and idempotent.
        MapLibre.getInstance(context)
        val seedZoom = initialZoomOverride?.toDouble()
            ?: initialCameraSnapshot?.zoom
            ?: 7.0
        MapView(context).apply {
            getMapAsync { map ->
                map.cameraPosition = CameraPosition.Builder()
                    .target(
                        initialCameraSnapshot
                            ?.let { LatLng(it.lat, it.lng) }
                            ?: LatLng(42.7, 25.5),
                    )
                    .zoom(seedZoom)
                    .bearing(initialCameraSnapshot?.bearing ?: 0.0)
                    .tilt(initialCameraSnapshot?.tilt ?: 0.0)
                    .build()
                // Stack MapLibre chrome above our bottom FAB columns:
                // wordmark at bottom-left, (i) attribution at bottom-right
                // on the same horizontal line, native compass lifted above
                // the (i) so it doesn't sit under the in-zone status chip
                // when heading-up follow rotates the map.
                val density = context.resources.displayMetrics.density
                map.uiSettings.setLogoMargins(
                    (8 * density).toInt(), 0, 0, (120 * density).toInt(),
                )
                map.uiSettings.attributionGravity = Gravity.BOTTOM or Gravity.END
                map.uiSettings.setAttributionMargins(
                    0, 0, (8 * density).toInt(), (120 * density).toInt(),
                )
                map.uiSettings.compassGravity = Gravity.BOTTOM or Gravity.END
                map.uiSettings.setCompassMargins(
                    0, 0, (8 * density).toInt(), (168 * density).toInt(),
                )
                map.addOnMoveListener(object : MapLibreMap.OnMoveListener {
                    override fun onMoveBegin(detector: org.maplibre.android.gestures.MoveGestureDetector) {}
                    override fun onMove(detector: org.maplibre.android.gestures.MoveGestureDetector) {
                        // User-initiated pan disengages follow mode.
                        if (viewModel.isFollowing.value) viewModel.setFollowing(false)
                    }
                    override fun onMoveEnd(detector: org.maplibre.android.gestures.MoveGestureDetector) {}
                })
            }
        }
    }

    LaunchedEffect(mapTheme) {
        val uri = viewModel.styleUriFor(mapTheme)
        mapView.getMapAsync { map ->
            map.setStyle(uri) { style ->
                installSharedStyleLayers(style, context)
                styleEpoch++
            }
        }
    }

    // Push every settled camera position into the VM so the next entry can
    // restore zoom + pan without re-running the auto zone-fit.
    DisposableEffect(mapView) {
        val idleListener = MapLibreMap.OnCameraIdleListener {
            mapView.getMapAsync { map ->
                val pos = map.cameraPosition
                val target = pos.target ?: return@getMapAsync
                viewModel.saveCameraSnapshot(
                    MapCameraSnapshot(
                        lat = target.latitude,
                        lng = target.longitude,
                        zoom = pos.zoom,
                        bearing = pos.bearing,
                        tilt = pos.tilt,
                    ),
                )
            }
        }
        mapView.getMapAsync { map -> map.addOnCameraIdleListener(idleListener) }
        onDispose {
            mapView.getMapAsync { map -> map.removeOnCameraIdleListener(idleListener) }
            // Tie MapView teardown to composition disposal, NOT to the lifecycle
            // observer below. Inside a NavHost, LocalLifecycleOwner is the
            // NavBackStackEntry, which only reaches CREATED (stopped) — never
            // DESTROYED — when another tab is selected under the
            // saveState/restoreState pattern, so an ON_DESTROY branch would never
            // fire and the native GL renderer + map handle would leak on every
            // Map→tab→Map round-trip. onDispose runs exactly when this composable
            // leaves the composition, which is the correct teardown point.
            mapView.onDestroy()
        }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_CREATE -> mapView.onCreate(null)
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                // ON_DESTROY intentionally omitted: the NavBackStackEntry never
                // reaches DESTROYED on a tab switch, so MapView teardown is
                // driven from the DisposableEffect(mapView) onDispose above.
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    // These map-state pushes are fire-and-forget (no resource to release on
    // dispose), so LaunchedEffect is the right tool — DisposableEffect with an
    // empty onDispose just obscures that. They re-fire on styleEpoch because
    // setStyle wipes all sources/layers.
    LaunchedEffect(zones, styleEpoch) {
        mapView.getMapAsync { map ->
            map.getStyle { style ->
                rebuildZoneLayers(style, zones, activeZoneId)
            }
        }
    }

    LaunchedEffect(activeZoneId, styleEpoch) {
        mapView.getMapAsync { map ->
            map.getStyle { style ->
                updateActiveZoneFilter(style, activeZoneId)
            }
        }
    }

    val zonesById = remember(zones) { zones.associateBy { it.id } }

    LaunchedEffect(activeZoneId, zones, styleEpoch) {
        val activeZone = activeZoneId?.let { zonesById[it] }
        mapView.getMapAsync { map ->
            map.getStyle { style ->
                style.getSourceAs<GeoJsonSource>(ENDPOINTS_SOURCE_ID)
                    ?.setGeoJson(endpointsGeoJson(activeZone))
            }
        }
    }

    // The active-zone line color only changes on over/under-limit transitions,
    // not on every 1 Hz fix. Derive it so the style update below re-fires when
    // the color actually changes — not once per GPS update. A History "Show on
    // map" highlight (only possible while tracking is off) paints the trip's
    // binary verdict instead of the live traffic light.
    val zoneLineColor by remember {
        derivedStateOf {
            val highlight = resolvedHighlight?.first
            when {
                highlight != null -> if (highlight.isOverLimit) ZONE_COLOR_RED else ZONE_COLOR_GREEN
                else -> when (val s = zoneState) {
                    is ZoneState.InZone -> zoneStatusColor(s, currentPosition?.speed)
                    is ZoneState.Exiting -> ZONE_COLOR_RED
                    // Neutral: the traffic-light palette is a verdict on the
                    // driver, and an unwitnessed entry earns no verdict.
                    is ZoneState.Unmeasured -> ZONE_COLOR_NEUTRAL
                    ZoneState.Outside -> ZONE_COLOR_RED
                }
            }
        }
    }
    LaunchedEffect(zoneLineColor, styleEpoch) {
        mapView.getMapAsync { map ->
            map.getStyle { style ->
                style.getLayerAs<LineLayer>(ZONES_ACTIVE_LAYER_ID)
                    ?.setProperties(PropertyFactory.lineColor(zoneLineColor))
            }
        }
    }

    // While a History highlight is shown, the arrow marks the traversal's
    // starting point, pointed straight at the zone's end point — the reading
    // is "you drove from here to there", not the instantaneous road heading.
    val highlightArrow = remember(resolvedHighlight) {
        resolvedHighlight?.second?.let { zone ->
            GpsPoint(
                lat = zone.start.lat,
                lng = zone.start.lng,
                speed = 0.0,
                timestamp = 0L,
                bearing = bearingBetween(zone.start.lat, zone.start.lng, zone.end.lat, zone.end.lng),
            )
        }
    }

    LaunchedEffect(displayPosition, effectiveBearing, highlightArrow, styleEpoch) {
        val point = highlightArrow ?: displayPosition
        val rotation = highlightArrow?.bearing ?: effectiveBearing
        mapView.getMapAsync { map ->
            map.getStyle { style ->
                style.getSourceAs<GeoJsonSource>(USER_SOURCE_ID)
                    ?.setGeoJson(userPositionGeoJson(point))
                style.getLayerAs<SymbolLayer>(USER_LAYER_ID)
                    ?.setProperties(PropertyFactory.iconRotate(rotation.toFloat()))
            }
        }
    }

    // Treat the current zone as already-fitted on re-entry if we restored a
    // saved camera, so the user's preferred zoom isn't overwritten.
    var lastFittedZoneId by remember {
        mutableStateOf(if (initialCameraSnapshot != null) activeZoneId else null)
    }
    LaunchedEffect(activeZoneId, zones, isFollowing, mapZoomOverride) {
        if (isFollowing) return@LaunchedEffect
        val id = activeZoneId
        if (id == null) {
            lastFittedZoneId = null
            return@LaunchedEffect
        }
        if (id == lastFittedZoneId) return@LaunchedEffect
        val overrideZoom = mapZoomOverride?.toDouble()
        if (overrideZoom != null) {
            val userPoint = currentPosition
            if (userPoint != null) {
                mapView.getMapAsync { map ->
                    map.animateCamera(
                        CameraUpdateFactory.newLatLngZoom(
                            LatLng(userPoint.lat, userPoint.lng),
                            overrideZoom,
                        ),
                    )
                }
                lastFittedZoneId = id
            }
            return@LaunchedEffect
        }
        val bounds = zonesById[id]?.let(::zoneBounds) ?: return@LaunchedEffect
        mapView.getMapAsync { map ->
            map.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, ZONE_FIT_PADDING_PX))
        }
        lastFittedZoneId = id
    }

    // One-shot camera fit per "Show on map" press, keyed on the requestId so
    // revisiting the Map tab keeps the user's pan/zoom while a fresh press
    // always re-fits — even for the same zone.
    LaunchedEffect(resolvedHighlight, styleEpoch) {
        val (highlight, zone) = resolvedHighlight ?: return@LaunchedEffect
        if (highlight.requestId == viewModel.lastFittedHighlightRequestId) return@LaunchedEffect
        viewModel.setFollowing(false)
        val bounds = zoneBounds(zone) ?: return@LaunchedEffect
        mapView.getMapAsync { map ->
            map.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, ZONE_FIT_PADDING_PX))
        }
        viewModel.lastFittedHighlightRequestId = highlight.requestId
        lastFittedZoneId = zone.id
    }

    var hasCenteredOnUser by remember { mutableStateOf(initialCameraSnapshot != null) }
    LaunchedEffect(currentPosition, activeZoneId, isFollowing, mapZoomOverride) {
        if (isFollowing) return@LaunchedEffect
        if (hasCenteredOnUser) return@LaunchedEffect
        if (activeZoneId != null) return@LaunchedEffect
        val point = currentPosition ?: return@LaunchedEffect
        val targetZoom = mapZoomOverride?.toDouble() ?: USER_FOLLOW_ZOOM
        mapView.getMapAsync { map ->
            map.animateCamera(
                CameraUpdateFactory.newLatLngZoom(LatLng(point.lat, point.lng), targetZoom),
            )
        }
        hasCenteredOnUser = true
    }

    // Zoom override set with no active zone AND no live position: the Bulgaria-
    // wide "map overview" shot. None of the follow / zone-fit / center-on-user
    // effects above fire (they all need a position or an active zone), so the
    // freshly-remembered MapView would keep the seeded snapshot (a zoomed-in,
    // possibly heading-up-rotated camera left by an earlier in-zone session).
    // Pin it to the override zoom over Bulgaria, north-up. Gated on the absence
    // of any position so it never fights the follow camera on in-zone shots.
    LaunchedEffect(mapZoomOverride, activeZoneId, displayPosition, currentPosition, styleEpoch) {
        val overrideZoom = mapZoomOverride?.toDouble() ?: return@LaunchedEffect
        if (activeZoneId != null) return@LaunchedEffect
        if (displayPosition != null || currentPosition != null) return@LaunchedEffect
        mapView.getMapAsync { map ->
            map.animateCamera(
                CameraUpdateFactory.newCameraPosition(
                    CameraPosition.Builder()
                        .target(LatLng(42.7339, 25.4858))
                        .zoom(overrideZoom)
                        .bearing(0.0)
                        .tilt(0.0)
                        .build(),
                ),
            )
        }
    }

    // First follow with no override (and no restored camera) snaps to
    // USER_FOLLOW_ZOOM rather than the Bulgaria-wide seed zoom (~7); afterwards
    // the user's current zoom is preserved. Mirrors iOS applyFollowCamera's
    // `didFollowOnce`. Without this, follow-by-default would center the user but
    // leave the map zoomed out to the seed level.
    var hasFollowedOnce by remember { mutableStateOf(initialCameraSnapshot != null) }
    LaunchedEffect(displayPosition, isFollowing, mapHeadingUp, effectiveBearing, mapZoomOverride) {
        if (!isFollowing) return@LaunchedEffect
        val point = displayPosition ?: return@LaunchedEffect
        val overrideZoom = mapZoomOverride?.toDouble()
        mapView.getMapAsync { map ->
            val bearing = if (mapHeadingUp) normalizeBearing(effectiveBearing) else 0.0
            val zoom = overrideZoom
                ?: if (!hasFollowedOnce) USER_FOLLOW_ZOOM
                else map.cameraPosition.zoom.takeIf { it > 0.0 } ?: USER_FOLLOW_ZOOM
            val target = CameraPosition.Builder()
                .target(LatLng(point.lat, point.lng))
                .zoom(zoom)
                .bearing(bearing)
                .tilt(0.0)
                .build()
            map.moveCamera(CameraUpdateFactory.newCameraPosition(target))
            hasFollowedOnce = true
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        AndroidView(
            factory = { mapView },
            modifier = Modifier.fillMaxSize(),
        )

        // SmallFloatingActionButton keeps Material's 48dp min-interactive touch
        // target around its 40dp visual (a11y: 40dp alone is below the minimum
        // and hard to hit on a bumpy road). The left-side custom FABs match it
        // via their own 48dp clickable box, so the two columns stay aligned.
        Column(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SmallFloatingActionButton(
                onClick = {
                    mapView.getMapAsync { it.animateCamera(CameraUpdateFactory.zoomIn()) }
                },
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = stringResource(R.string.map_zoom_in),
                )
            }
            SmallFloatingActionButton(
                onClick = {
                    mapView.getMapAsync { it.animateCamera(CameraUpdateFactory.zoomOut()) }
                },
            ) {
                Icon(
                    imageVector = Icons.Filled.Remove,
                    contentDescription = stringResource(R.string.map_zoom_out),
                )
            }
        }

        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            MapOrientationFab(
                isHeadingUp = mapHeadingUp,
                onTap = {
                    val turningOn = !mapHeadingUp
                    viewModel.toggleMapHeadingUp()
                    if (turningOn) viewModel.setFollowing(true)
                },
            )
            RecenterFollowFab(
                isFollowing = isFollowing,
                onTap = {
                    val activeZone = activeZoneId?.let { zonesById[it] }
                    val overrideZoom = mapZoomOverride?.toDouble()
                    val zoneFit = if (overrideZoom == null) activeZone?.let(::zoneBounds) else null
                    val point = currentPosition
                    val followZoom = overrideZoom ?: USER_FOLLOW_ZOOM
                    mapView.getMapAsync { map ->
                        when {
                            zoneFit != null ->
                                map.animateCamera(
                                    CameraUpdateFactory.newLatLngBounds(zoneFit, ZONE_FIT_PADDING_PX),
                                )
                            point != null -> {
                                if (mapHeadingUp) {
                                    val target = CameraPosition.Builder()
                                        .target(LatLng(point.lat, point.lng))
                                        .zoom(followZoom)
                                        .bearing(normalizeBearing(effectiveBearing))
                                        .tilt(0.0)
                                        .build()
                                    map.moveCamera(CameraUpdateFactory.newCameraPosition(target))
                                } else {
                                    map.animateCamera(
                                        CameraUpdateFactory.newLatLngZoom(
                                            LatLng(point.lat, point.lng),
                                            followZoom,
                                        ),
                                    )
                                }
                            }
                        }
                    }
                },
                onLongPress = { viewModel.setFollowing(!isFollowing) },
            )
        }

        if (zones.isNotEmpty()) {
            ZoneStatusChip(
                state = zoneState,
                currentSpeedKmh = currentPosition?.speed,
                vehicleType = vehicleType,
                debugMaxSpeedOverride = debugMaxSpeedOverride,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .statusBarsPadding()
                    .padding(horizontal = 12.dp, vertical = 12.dp)
                    .fillMaxWidth(),
            )
        }

        if (zones.isEmpty()) {
            Surface(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .statusBarsPadding()
                    .padding(16.dp),
                color = MaterialTheme.colorScheme.surfaceContainerHigh,
                contentColor = MaterialTheme.colorScheme.onSurface,
                shape = MaterialTheme.shapes.medium,
                tonalElevation = 4.dp,
                shadowElevation = 4.dp,
            ) {
                Column(
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = stringResource(R.string.no_zones_loaded),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    TextButton(
                        onClick = { viewModel.retrySync() },
                        enabled = !isSyncing,
                    ) {
                        if (isSyncing) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp,
                                color = LocalContentColor.current,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        Text(stringResource(R.string.retry_sync))
                    }
                }
            }
        }
    }
}

private fun installSharedStyleLayers(style: Style, context: Context) {
    context.bitmapFromVectorDrawable(R.drawable.ic_nav_arrow)?.let { bitmap ->
        style.addImage(USER_ARROW_ICON, bitmap)
    }
    style.addSource(GeoJsonSource(ENDPOINTS_SOURCE_ID, emptyFeatureCollection()))
    style.addLayer(
        CircleLayer(ENDPOINTS_START_LAYER_ID, ENDPOINTS_SOURCE_ID).apply {
            setFilter(Expression.eq(Expression.get(ENDPOINT_PROP), Expression.literal(ENDPOINT_START)))
            setProperties(
                PropertyFactory.circleRadius(8f),
                PropertyFactory.circleColor(ENDPOINT_START_COLOR),
                PropertyFactory.circleStrokeColor("#FFFFFF"),
                PropertyFactory.circleStrokeWidth(2f),
            )
        },
    )
    style.addLayer(
        CircleLayer(ENDPOINTS_END_LAYER_ID, ENDPOINTS_SOURCE_ID).apply {
            setFilter(Expression.eq(Expression.get(ENDPOINT_PROP), Expression.literal(ENDPOINT_END)))
            setProperties(
                PropertyFactory.circleRadius(8f),
                PropertyFactory.circleColor(ENDPOINT_END_COLOR),
                PropertyFactory.circleStrokeColor("#FFFFFF"),
                PropertyFactory.circleStrokeWidth(2f),
            )
        },
    )
    style.addSource(GeoJsonSource(USER_SOURCE_ID, emptyFeatureCollection()))
    style.addLayer(
        SymbolLayer(USER_LAYER_ID, USER_SOURCE_ID).withProperties(
            PropertyFactory.iconImage(USER_ARROW_ICON),
            PropertyFactory.iconRotationAlignment(Property.ICON_ROTATION_ALIGNMENT_MAP),
            PropertyFactory.iconAllowOverlap(true),
            PropertyFactory.iconIgnorePlacement(true),
            PropertyFactory.iconSize(1f),
        ),
    )
}

private fun rebuildZoneLayers(style: Style, zones: List<Zone>, activeZoneId: String?) {
    style.removeLayer(ZONES_ACTIVE_LAYER_ID)
    style.removeLayer(ZONES_INACTIVE_LAYER_ID)
    style.removeSource(ZONES_SOURCE_ID)

    if (zones.isEmpty()) return

    style.addSource(GeoJsonSource(ZONES_SOURCE_ID, zonesFeatureCollection(zones)))

    val sentinel = activeZoneId ?: ACTIVE_ID_SENTINEL
    val inactiveLayer = LineLayer(ZONES_INACTIVE_LAYER_ID, ZONES_SOURCE_ID).apply {
        setFilter(Expression.neq(Expression.get(ZONE_ID_PROP), Expression.literal(sentinel)))
        setProperties(
            PropertyFactory.lineColor(INACTIVE_COLOR),
            PropertyFactory.lineWidth(4f),
            PropertyFactory.lineOpacity(0.8f),
            PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
            PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
        )
    }
    val activeLayer = LineLayer(ZONES_ACTIVE_LAYER_ID, ZONES_SOURCE_ID).apply {
        setFilter(Expression.eq(Expression.get(ZONE_ID_PROP), Expression.literal(sentinel)))
        setProperties(
            PropertyFactory.lineColor(ACTIVE_COLOR),
            PropertyFactory.lineWidth(6f),
            PropertyFactory.lineOpacity(1f),
            PropertyFactory.lineCap(Property.LINE_CAP_ROUND),
            PropertyFactory.lineJoin(Property.LINE_JOIN_ROUND),
        )
    }

    // Stack: zones (bottom) → endpoints → user arrow (top).
    val anchor = when {
        style.getLayer(ENDPOINTS_START_LAYER_ID) != null -> ENDPOINTS_START_LAYER_ID
        style.getLayer(USER_LAYER_ID) != null -> USER_LAYER_ID
        else -> null
    }
    if (anchor != null) {
        style.addLayerBelow(inactiveLayer, anchor)
        style.addLayerBelow(activeLayer, anchor)
    } else {
        style.addLayer(inactiveLayer)
        style.addLayer(activeLayer)
    }
}

private fun updateActiveZoneFilter(style: Style, activeZoneId: String?) {
    val sentinel = activeZoneId ?: ACTIVE_ID_SENTINEL
    style.getLayerAs<LineLayer>(ZONES_INACTIVE_LAYER_ID)
        ?.setFilter(Expression.neq(Expression.get(ZONE_ID_PROP), Expression.literal(sentinel)))
    style.getLayerAs<LineLayer>(ZONES_ACTIVE_LAYER_ID)
        ?.setFilter(Expression.eq(Expression.get(ZONE_ID_PROP), Expression.literal(sentinel)))
}

private fun zonesFeatureCollection(zones: List<Zone>): String {
    val features = JSONArray()
    for (zone in zones) {
        val coordinates = JSONArray()
        for (point in zone.centerline) {
            if (point.size >= 2) {
                coordinates.put(JSONArray().apply {
                    put(point[1])
                    put(point[0])
                })
            }
        }
        val feature = JSONObject().apply {
            put("type", "Feature")
            put("geometry", JSONObject().apply {
                put("type", "LineString")
                put("coordinates", coordinates)
            })
            put("properties", JSONObject().apply {
                put(ZONE_ID_PROP, zone.id)
                put("road", zone.road)
                put("direction", zone.direction)
            })
        }
        features.put(feature)
    }
    return JSONObject().apply {
        put("type", "FeatureCollection")
        put("features", features)
    }.toString()
}

private fun endpointsGeoJson(zone: Zone?): String {
    if (zone == null) return emptyFeatureCollection()
    val features = JSONArray()
    fun addPoint(lat: Double, lng: Double, kind: String) {
        val feature = JSONObject().apply {
            put("type", "Feature")
            put("geometry", JSONObject().apply {
                put("type", "Point")
                put("coordinates", JSONArray().apply {
                    put(lng)
                    put(lat)
                })
            })
            put("properties", JSONObject().apply {
                put(ENDPOINT_PROP, kind)
            })
        }
        features.put(feature)
    }
    addPoint(zone.start.lat, zone.start.lng, ENDPOINT_START)
    addPoint(zone.end.lat, zone.end.lng, ENDPOINT_END)
    return JSONObject().apply {
        put("type", "FeatureCollection")
        put("features", features)
    }.toString()
}

private fun zoneBounds(zone: Zone): LatLngBounds? {
    if (zone.centerline.size < 2) return null
    val builder = LatLngBounds.Builder()
    var added = 0
    zone.centerline.forEach { point ->
        if (point.size >= 2) {
            builder.include(LatLng(point[0], point[1]))
            added++
        }
    }
    if (added < 2) return null
    return builder.build()
}

private fun normalizeBearing(value: Double): Double {
    if (!value.isFinite()) return 0.0
    val mod = value.mod(360.0)
    return if (mod < 0.0) mod + 360.0 else mod
}

private fun userPositionGeoJson(point: GpsPoint?): String {
    if (point == null) return emptyFeatureCollection()
    val feature = JSONObject().apply {
        put("type", "Feature")
        put("geometry", JSONObject().apply {
            put("type", "Point")
            put("coordinates", JSONArray().apply {
                put(point.lng)
                put(point.lat)
            })
        })
    }
    return JSONObject().apply {
        put("type", "FeatureCollection")
        put("features", JSONArray().apply { put(feature) })
    }.toString()
}

private fun emptyFeatureCollection(): String =
    """{"type":"FeatureCollection","features":[]}"""

@Composable
private fun MapOrientationFab(
    isHeadingUp: Boolean,
    onTap: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val containerColor = if (isHeadingUp) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.surfaceContainerHigh
    }
    val contentColor = if (isHeadingUp) {
        MaterialTheme.colorScheme.onPrimary
    } else {
        MaterialTheme.colorScheme.onSurface
    }
    val icon = if (isHeadingUp) Icons.Filled.Navigation else Icons.Filled.Explore
    val description = stringResource(
        if (isHeadingUp) R.string.map_orientation_heading_up else R.string.map_orientation_north_up,
    )
    // 40dp visual inside a 48dp clickable box so the touch target meets the
    // accessibility minimum while the column stays aligned with the +/- FABs.
    Box(
        modifier = modifier
            .size(48.dp)
            .clip(CircleShape)
            .clickable(onClick = onTap),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .size(40.dp)
                .shadow(6.dp, CircleShape)
                .clip(CircleShape),
            shape = CircleShape,
            color = containerColor,
            contentColor = contentColor,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(imageVector = icon, contentDescription = description)
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun RecenterFollowFab(
    isFollowing: Boolean,
    onTap: () -> Unit,
    onLongPress: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val containerColor = if (isFollowing) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.surfaceContainerHigh
    }
    val contentColor = if (isFollowing) {
        MaterialTheme.colorScheme.onPrimary
    } else {
        MaterialTheme.colorScheme.onSurface
    }
    val icon = if (isFollowing) Icons.Filled.MyLocation else Icons.Filled.CenterFocusStrong
    val description = stringResource(
        if (isFollowing) R.string.map_follow_user_on else R.string.map_follow_user_off,
    )
    // 40dp visual inside a 48dp clickable box so the touch target meets the
    // accessibility minimum while the column stays aligned with the +/- FABs.
    Box(
        modifier = modifier
            .size(48.dp)
            .clip(CircleShape)
            .combinedClickable(onClick = onTap, onLongClick = onLongPress),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .size(40.dp)
                .shadow(6.dp, CircleShape)
                .clip(CircleShape),
            shape = CircleShape,
            color = containerColor,
            contentColor = contentColor,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(imageVector = icon, contentDescription = description)
            }
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

private fun Context.bitmapFromVectorDrawable(@DrawableRes resId: Int): Bitmap? {
    val drawable = ContextCompat.getDrawable(this, resId) ?: return null
    val width = drawable.intrinsicWidth.takeIf { it > 0 } ?: return null
    val height = drawable.intrinsicHeight.takeIf { it > 0 } ?: return null
    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    drawable.setBounds(0, 0, canvas.width, canvas.height)
    drawable.draw(canvas)
    return bitmap
}
