// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOff
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.R
import com.demosten.srednabg.app.permissions.PermissionState
import com.demosten.srednabg.app.ui.theme.warningAmber
import com.demosten.srednabg.app.ui.theme.SpeedRedLight
import com.demosten.srednabg.app.ui.theme.speedGreen
import com.demosten.srednabg.app.ui.theme.speedRed
import com.demosten.srednabg.app.ui.util.orDash
import com.demosten.srednabg.app.ui.components.exitVerdictOverLimit
import com.demosten.srednabg.app.ui.viewmodel.HomeViewModel
import com.demosten.srednabg.core.VehicleType
import com.demosten.srednabg.core.ZoneState
import java.util.Locale

// Hero speed readout (Outside "now" speed, InZone running average). Oversized on
// purpose for at-a-glance reading while driving; sp so it still honors the
// system accessibility font scale.
private val HeroSpeedFontSize = 128.sp

@Composable
fun HomeScreen(viewModel: HomeViewModel = hiltViewModel()) {
    val zoneState by viewModel.zoneState.collectAsStateWithLifecycle()
    val isTracking by viewModel.isTracking.collectAsStateWithLifecycle()
    val zoneCount by viewModel.zoneCount.collectAsStateWithLifecycle()
    val currentSpeedKmh by viewModel.currentSpeedKmh.collectAsStateWithLifecycle()
    val permissionState by viewModel.permissionState.collectAsStateWithLifecycle()
    val debugMaxSpeedOverride by viewModel.debugMaxSpeedOverride.collectAsStateWithLifecycle()
    val vehicleType by viewModel.vehicleType.collectAsStateWithLifecycle()
    val context = LocalContext.current

    // Notification permission is requested from inside the NotificationCard
    // (not the global permission handler) so the user sees the in-app rationale
    // before the system dialog appears.
    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { viewModel.refreshPermissions() }
    // remember the action lambdas so StateContent gets stable identities and can
    // skip recomposition (this screen recomposes ~1 Hz from the live GPS feed).
    val onRequestNotification: () -> Unit = remember(notificationLauncher) {
        {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }
    val onOpenAppSettings: () -> Unit = remember(context) { { openAppSettings(context) } }
    val onRequestBatteryOptOut: () -> Unit =
        remember(context) { { requestIgnoreBatteryOptimizations(context) } }

    // Pick up changes the user made in app-Settings while we were
    // backgrounded — flipping a permission or whitelisting battery
    // optimization should clear the relevant card the moment they return.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) viewModel.refreshPermissions()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            StateContent(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                zoneState = zoneState,
                isTracking = isTracking,
                zoneCount = zoneCount,
                currentSpeedKmh = currentSpeedKmh,
                permissionState = permissionState,
                debugMaxSpeedOverride = debugMaxSpeedOverride,
                vehicleType = vehicleType,
                onOpenAppSettings = onOpenAppSettings,
                onRequestNotification = onRequestNotification,
                onRequestBatteryOptOut = onRequestBatteryOptOut,
            )

            // Hide the Start button while the location-permission card is up —
            // it has its own primary action (Open Settings). The notification
            // and battery-opt cards are advisory, so the Start button stays
            // visible alongside them. Stop button is always available so an
            // active session can be ended.
            val showStartStop = isTracking || permissionState.canStartTracking
            if (showStartStop) {
                StartStopButton(
                    isTracking = isTracking,
                    onStart = { viewModel.startTracking() },
                    onStop = { viewModel.stopTracking() },
                )
            }
        }
    }
}

@Composable
private fun StartStopButton(isTracking: Boolean, onStart: () -> Unit, onStop: () -> Unit) {
    val buttonLabel = if (isTracking) {
        stringResource(R.string.stop_tracking)
    } else {
        stringResource(R.string.start_tracking)
    }
    Button(
        onClick = { if (isTracking) onStop() else onStart() },
        modifier = Modifier
            .fillMaxWidth()
            .height(72.dp),
        colors = if (isTracking) {
            // Solid red fill with white content, matching the iOS Stop button
            // (`.borderedProminent` tinted `Theme.statusRed`) instead of the pale
            // Material errorContainer.
            ButtonDefaults.buttonColors(
                containerColor = SpeedRedLight,
                contentColor = Color.White,
            )
        } else {
            ButtonDefaults.buttonColors()
        },
    ) {
        Icon(
            imageVector = if (isTracking) Icons.Default.Stop else Icons.Default.PlayArrow,
            contentDescription = null,
            // Match the iOS button, where the SF Symbol scales with the
            // `.title3` label font; the Compose default (24dp) reads small next
            // to the 20sp label.
            modifier = Modifier.size(28.dp),
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = buttonLabel,
            // Match the iOS Start/Stop button (`.title3.weight(.semibold)` ≈
            // 20pt SemiBold); the Material `titleMedium` default (16sp) read too
            // small next to it.
            style = MaterialTheme.typography.titleMedium,
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun StateContent(
    modifier: Modifier,
    zoneState: ZoneState,
    isTracking: Boolean,
    zoneCount: Int,
    currentSpeedKmh: Double?,
    permissionState: PermissionState,
    debugMaxSpeedOverride: Int?,
    vehicleType: VehicleType,
    onOpenAppSettings: () -> Unit,
    onRequestNotification: () -> Unit,
    onRequestBatteryOptOut: () -> Unit,
) {
    when {
        // Active tracking always wins — never gate the live display on
        // permission state changes mid-trip.
        isTracking && zoneState is ZoneState.InZone ->
            InZoneCard(modifier, zoneState, currentSpeedKmh, vehicleType, debugMaxSpeedOverride)
        isTracking && zoneState is ZoneState.Exiting ->
            ExitingCard(modifier, zoneState, currentSpeedKmh, vehicleType)
        isTracking ->
            OutsideCard(modifier, currentSpeedKmh, zoneCount)
        !permissionState.canStartTracking ->
            PermissionCard(modifier, permissionState, onOpenAppSettings)
        !permissionState.notificationGranted ->
            NotificationCard(modifier, onRequestNotification, onOpenAppSettings)
        !permissionState.ignoringBatteryOptimizations ->
            BatteryOptimizationCard(modifier, onRequestBatteryOptOut)
        else ->
            NotTrackingCard(modifier)
    }
}

@Composable
private fun PermissionCard(
    modifier: Modifier,
    state: PermissionState,
    onOpenAppSettings: () -> Unit,
) {
    val title = if (!state.fineLocationGranted) {
        stringResource(R.string.permission_denied_title)
    } else {
        stringResource(R.string.permission_required_title)
    }
    val body = if (!state.fineLocationGranted) {
        stringResource(R.string.permission_denied_body)
    } else {
        stringResource(R.string.permission_required_body)
    }

    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = speedRed().copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Text scrolls inside the weighted region so the action button below
            // stays visible even at large accessibility font scales.
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(
                        imageVector = Icons.Default.LocationOff,
                        contentDescription = null,
                        tint = speedRed(),
                    )
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    text = body,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Button(
                onClick = onOpenAppSettings,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Icon(imageVector = Icons.Default.Settings, contentDescription = null)
                Spacer(modifier = Modifier.width(12.dp))
                Text(
                    text = stringResource(R.string.permission_open_settings),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }
    }
}

@Composable
private fun NotificationCard(
    modifier: Modifier,
    onAllow: () -> Unit,
    onOpenAppSettings: () -> Unit,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = warningAmber().copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Text scrolls inside the weighted region so the action buttons below
            // stay visible even at large accessibility font scales.
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(
                        imageVector = Icons.Default.Notifications,
                        contentDescription = null,
                        tint = warningAmber(),
                    )
                    Text(
                        text = stringResource(R.string.notification_recommended_title),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    text = stringResource(R.string.notification_recommended_body),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Button(
                onClick = onAllow,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = warningAmber()),
            ) {
                Text(
                    text = stringResource(R.string.notification_recommended_allow),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            // Fallback when the system suppresses the dialog (user previously
            // chose "Don't ask again" — `RequestPermission` returns denied
            // immediately and the card stays put). Open Settings is the only
            // recovery path in that case.
            TextButton(
                onClick = onOpenAppSettings,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    text = stringResource(R.string.permission_open_settings),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun BatteryOptimizationCard(modifier: Modifier, onRequestOptOut: () -> Unit) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = warningAmber().copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // Text scrolls inside the weighted region so the action button below
            // stays visible even at large accessibility font scales.
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Text(
                    text = stringResource(R.string.battery_opt_title),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = warningAmber(),
                )
                Text(
                    text = stringResource(R.string.battery_opt_body),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Button(
                onClick = onRequestOptOut,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(containerColor = warningAmber()),
            ) {
                Text(
                    text = stringResource(R.string.battery_opt_action),
                    style = MaterialTheme.typography.titleMedium,
                )
            }
        }
    }
}

@Composable
private fun NotTrackingCard(modifier: Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = stringResource(R.string.status_not_tracking),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = stringResource(R.string.tap_to_start_hint),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    // Center the wrapped hint, matching iOS's
                    // `.multilineTextAlignment(.center)`.
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun OutsideCard(modifier: Modifier, currentSpeedKmh: Double?, zoneCount: Int) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f),
        ),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.status_tracking_outside),
                style = MaterialTheme.typography.titleMedium,
            )
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = currentSpeedKmh.orDash(),
                        fontSize = HeroSpeedFontSize,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = stringResource(R.string.current_speed_label),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Text(
                text = stringResource(R.string.zones_loaded, zoneCount),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun InZoneCard(
    modifier: Modifier,
    state: ZoneState.InZone,
    currentSpeedKmh: Double?,
    vehicleType: VehicleType,
    debugMaxSpeedOverride: Int? = null,
) {
    // Vehicle-type-resolved limit — the engine's over-limit verdict uses it,
    // so the badge must show the same number, not the car default.
    val limit = vehicleType.limit(state.zone.speedLimits)
    val statusColor = when {
        state.speedStatus.isOverLimit -> speedRed()
        // Amber tier is deliberately car-relative (matches core zoneStatusColor
        // and the iOS surfaces); red comes from the vehicle-aware isOverLimit.
        currentSpeedKmh != null && currentSpeedKmh > state.zone.speedLimits.car -> warningAmber()
        else -> speedGreen()
    }
    val statusText = if (state.speedStatus.isOverLimit) {
        stringResource(R.string.status_over_limit)
    } else {
        stringResource(R.string.status_within_limit)
    }
    val semanticDescription = stringResource(
        R.string.accessibility_in_zone,
        state.avgSpeed.orDash(),
        limit,
        statusText,
    )

    Card(
        // clearAndSetSemantics (not semantics): the description is a full spoken
        // summary of the card, so suppress the child Text nodes' own semantics to
        // stop TalkBack reading the summary AND each value a second time.
        modifier = modifier.clearAndSetSemantics { contentDescription = semanticDescription },
        colors = CardDefaults.cardColors(containerColor = statusColor.copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
        ) {
            Text(
                text = stringResource(R.string.status_in_zone, state.zone.road),
                style = MaterialTheme.typography.titleMedium,
            )

            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = state.avgSpeed.orDash(),
                        fontSize = HeroSpeedFontSize,
                        fontWeight = FontWeight.Bold,
                        color = statusColor,
                    )
                    Text(
                        text = stringResource(R.string.avg_speed_label),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    // Extra gap so the current-speed line reads as a separate
                    // value, not part of the average block above it.
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = stringResource(R.string.status_now_speed, currentSpeedKmh.orDash()),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                InfoItem(
                    label = stringResource(R.string.speed_limit),
                    value = "$limit",
                )
                InfoItem(
                    label = stringResource(R.string.max_for_remainder),
                    value = "${debugMaxSpeedOverride ?: state.speedStatus.maxSpeedForRemainder.toInt()}",
                )
                InfoItem(
                    label = stringResource(R.string.remaining),
                    value = String.format(Locale.US, "%.1f km", state.distanceRemaining / 1000.0),
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = statusText,
                style = MaterialTheme.typography.titleMedium,
                color = statusColor,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ExitingCard(
    modifier: Modifier,
    state: ZoneState.Exiting,
    currentSpeedKmh: Double?,
    vehicleType: VehicleType,
) {
    val color = if (exitVerdictOverLimit(state, vehicleType)) speedRed() else speedGreen()
    val semanticDescription = stringResource(
        R.string.accessibility_exiting,
        state.finalAvgSpeed.orDash(),
        state.zone.road,
    )

    Card(
        // See InZoneCard: clear child semantics so the summary isn't double-read.
        modifier = modifier.clearAndSetSemantics { contentDescription = semanticDescription },
        colors = CardDefaults.cardColors(containerColor = color.copy(alpha = 0.15f)),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.status_exiting, state.zone.road),
                style = MaterialTheme.typography.titleMedium,
            )
            Box(
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = stringResource(R.string.final_avg_speed, state.finalAvgSpeed.orDash()),
                        style = MaterialTheme.typography.headlineLarge,
                        color = color,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            Text(
                text = stringResource(R.string.status_now_speed, currentSpeedKmh.orDash()),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun InfoItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(text = label, style = MaterialTheme.typography.bodySmall)
    }
}

private fun openAppSettings(context: Context) {
    val intent = Intent(
        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
        Uri.fromParts("package", context.packageName, null),
    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
}

// `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` opens a confirmation dialog
// inline (no Settings excursion) when the manifest declares the matching
// permission. The lint warning is benign here — declaring this permission is
// documented as acceptable for active GPS-tracking apps. Falling back to the
// generic battery-opt list keeps the older API path open if the targeted
// dialog isn't available.
@SuppressLint("BatteryLife")
private fun requestIgnoreBatteryOptimizations(context: Context) {
    val pkg = context.packageName
    val direct = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
        data = Uri.parse("package:$pkg")
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    val resolved = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        direct.resolveActivity(context.packageManager)
    } else {
        @Suppress("DEPRECATION") direct.resolveActivity(context.packageManager)
    }
    if (resolved != null) {
        context.startActivity(direct)
        return
    }
    context.startActivity(
        Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
    )
}
