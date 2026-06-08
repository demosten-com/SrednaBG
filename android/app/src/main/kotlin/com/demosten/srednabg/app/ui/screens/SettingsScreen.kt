// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.ui.screens

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.core.os.LocaleListCompat
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.demosten.srednabg.BuildConfig
import com.demosten.srednabg.R
import com.demosten.srednabg.app.data.SyncResult
import com.demosten.srednabg.app.ui.viewmodel.SettingsViewModel
import com.demosten.srednabg.core.MapThemeMode

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: SettingsViewModel = hiltViewModel()) {
    val alertThreshold by viewModel.alertThreshold.collectAsStateWithLifecycle()
    val voiceEnabled by viewModel.voiceEnabled.collectAsStateWithLifecycle()
    val periodicVoiceUpdates by viewModel.periodicVoiceUpdates.collectAsStateWithLifecycle()
    val announceOnlyWhenOver by viewModel.announceOnlyWhenOver.collectAsStateWithLifecycle()
    val appLanguage by viewModel.appLanguage.collectAsStateWithLifecycle()
    val vehicleType by viewModel.vehicleType.collectAsStateWithLifecycle()
    val autoStopHours by viewModel.autoStopHours.collectAsStateWithLifecycle()
    val mapThemeMode by viewModel.mapThemeMode.collectAsStateWithLifecycle()
    val zoneSyncEnabled by viewModel.zoneSyncEnabled.collectAsStateWithLifecycle()
    val overlayEnabled by viewModel.overlayEnabled.collectAsStateWithLifecycle()
    val isSyncing by viewModel.isSyncing.collectAsStateWithLifecycle()

    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current
    LaunchedEffect(viewModel) {
        viewModel.syncEvents.collect { result ->
            val messageRes = when (result) {
                is SyncResult.Updated -> R.string.sync_updated
                is SyncResult.UpToDate -> R.string.sync_up_to_date
                is SyncResult.Failed -> R.string.sync_failed
            }
            snackbarHostState.showSnackbar(context.getString(messageRes))
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        ) {
        Text(
            text = stringResource(R.string.nav_settings),
            style = MaterialTheme.typography.headlineMedium,
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Alert threshold
        Text(
            text = stringResource(R.string.setting_alert_threshold),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text = stringResource(R.string.setting_alert_threshold_desc, alertThreshold),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Slider(
            value = alertThreshold.toFloat(),
            onValueChange = { viewModel.setAlertThreshold(it.toInt()) },
            valueRange = 0f..20f,
            steps = 19,
            modifier = Modifier.fillMaxWidth(),
        )

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Voice alerts
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = stringResource(R.string.setting_voice_alerts),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(R.string.setting_voice_alerts_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(
                checked = voiceEnabled,
                onCheckedChange = { viewModel.setVoiceEnabled(it) },
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Periodic voice updates — sub-toggle under Voice alerts
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = stringResource(R.string.setting_periodic_updates),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(R.string.setting_periodic_updates_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(
                checked = periodicVoiceUpdates,
                onCheckedChange = { viewModel.setPeriodicVoiceUpdates(it) },
                enabled = voiceEnabled,
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Only-when-over-limit — nested under Periodic voice updates
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = stringResource(R.string.setting_overspeed_only),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(R.string.setting_overspeed_only_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(
                checked = announceOnlyWhenOver,
                onCheckedChange = { viewModel.setAnnounceOnlyWhenOver(it) },
                enabled = voiceEnabled && periodicVoiceUpdates,
            )
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // App language (controls both UI locale and voice)
        Text(
            text = stringResource(R.string.setting_language),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text = stringResource(R.string.setting_language_desc),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(8.dp))

        var langExpanded by remember { mutableStateOf(false) }
        val langOptions = listOf(
            "system" to stringResource(R.string.language_system),
            "bg" to stringResource(R.string.language_bg),
            "en" to stringResource(R.string.language_en),
        )
        val currentLangLabel = langOptions.firstOrNull { it.first == appLanguage }?.second ?: appLanguage

        ExposedDropdownMenuBox(
            expanded = langExpanded,
            onExpandedChange = { langExpanded = it },
        ) {
            OutlinedTextField(
                value = currentLangLabel,
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = langExpanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            ExposedDropdownMenu(
                expanded = langExpanded,
                onDismissRequest = { langExpanded = false },
            ) {
                langOptions.forEach { (code, label) ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            viewModel.setAppLanguage(code)
                            val tags = if (code == "system") "" else code
                            AppCompatDelegate.setApplicationLocales(
                                LocaleListCompat.forLanguageTags(tags),
                            )
                            langExpanded = false
                        },
                    )
                }
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Vehicle type
        Text(
            text = stringResource(R.string.setting_vehicle_type),
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(modifier = Modifier.height(8.dp))

        var typeExpanded by remember { mutableStateOf(false) }
        val typeOptions = listOf(
            "car" to stringResource(R.string.vehicle_car),
            "truck" to stringResource(R.string.vehicle_truck),
            "bus" to stringResource(R.string.vehicle_bus),
        )
        val currentTypeLabel = typeOptions.firstOrNull { it.first == vehicleType }?.second ?: vehicleType

        ExposedDropdownMenuBox(
            expanded = typeExpanded,
            onExpandedChange = { typeExpanded = it },
        ) {
            OutlinedTextField(
                value = currentTypeLabel,
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            ExposedDropdownMenu(
                expanded = typeExpanded,
                onDismissRequest = { typeExpanded = false },
            ) {
                typeOptions.forEach { (code, label) ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            viewModel.setVehicleType(code)
                            typeExpanded = false
                        },
                    )
                }
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Auto-stop after inactivity
        Text(
            text = stringResource(R.string.setting_auto_stop),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text = stringResource(R.string.setting_auto_stop_desc),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(8.dp))

        var autoStopExpanded by remember { mutableStateOf(false) }
        val autoStopOptions = listOf(
            3 to stringResource(R.string.auto_stop_3h),
            6 to stringResource(R.string.auto_stop_6h),
            0 to stringResource(R.string.auto_stop_never),
        )
        val currentAutoStopLabel =
            autoStopOptions.firstOrNull { it.first == autoStopHours }?.second ?: ""

        ExposedDropdownMenuBox(
            expanded = autoStopExpanded,
            onExpandedChange = { autoStopExpanded = it },
        ) {
            OutlinedTextField(
                value = currentAutoStopLabel,
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = autoStopExpanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            ExposedDropdownMenu(
                expanded = autoStopExpanded,
                onDismissRequest = { autoStopExpanded = false },
            ) {
                autoStopOptions.forEach { (hours, label) ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            viewModel.setAutoStopHours(hours)
                            autoStopExpanded = false
                        },
                    )
                }
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Map theme — Auto / Light / Dark
        Text(
            text = stringResource(R.string.setting_map_theme),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text = stringResource(R.string.setting_map_theme_desc),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(8.dp))

        var themeExpanded by remember { mutableStateOf(false) }
        val themeOptions = listOf(
            MapThemeMode.AUTO to stringResource(R.string.map_theme_auto),
            MapThemeMode.LIGHT to stringResource(R.string.map_theme_light),
            MapThemeMode.DARK to stringResource(R.string.map_theme_dark),
        )
        val currentThemeLabel = themeOptions.firstOrNull { it.first == mapThemeMode }?.second ?: ""

        ExposedDropdownMenuBox(
            expanded = themeExpanded,
            onExpandedChange = { themeExpanded = it },
        ) {
            OutlinedTextField(
                value = currentThemeLabel,
                onValueChange = {},
                readOnly = true,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = themeExpanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryNotEditable),
            )
            ExposedDropdownMenu(
                expanded = themeExpanded,
                onDismissRequest = { themeExpanded = false },
            ) {
                themeOptions.forEach { (mode, label) ->
                    DropdownMenuItem(
                        text = { Text(label) },
                        onClick = {
                            viewModel.setMapThemeMode(mode)
                            themeExpanded = false
                        },
                    )
                }
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Floating overlay over other apps (Waze/Maps). Special permission —
        // toggling on without it sends the user to the system grant screen; the
        // service's visibility gate picks up the grant on return.
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = stringResource(R.string.setting_overlay),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(R.string.setting_overlay_desc),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(
                checked = overlayEnabled,
                onCheckedChange = { enabled ->
                    viewModel.setOverlayEnabled(enabled)
                    if (enabled && !Settings.canDrawOverlays(context)) {
                        requestOverlayPermission(context)
                    }
                },
            )
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 16.dp))

        // Automatic zone updates — opt-out for the periodic background sync.
        // The "Sync zones now" button below stays available regardless.
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.setting_zone_sync),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
            Switch(
                checked = zoneSyncEnabled,
                onCheckedChange = { viewModel.setZoneSyncEnabled(it) },
            )
        }
        Text(
            text = stringResource(R.string.setting_zone_sync_desc),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(modifier = Modifier.height(12.dp))

        // Sync
        Button(
            onClick = { viewModel.syncNow() },
            enabled = !isSyncing,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (isSyncing) {
                CircularProgressIndicator(
                    modifier = Modifier.size(18.dp),
                    strokeWidth = 2.dp,
                    color = LocalContentColor.current,
                )
                Spacer(modifier = Modifier.width(8.dp))
            }
            Text(stringResource(R.string.setting_sync_now))
        }

        Spacer(modifier = Modifier.height(24.dp))

        // About
        Text(
            text = stringResource(R.string.about_title),
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Image(
            painter = painterResource(R.drawable.ic_logo_horizontal),
            contentDescription = "SrednaBG",
            modifier = Modifier
                .fillMaxWidth()
                .height(80.dp),
            contentScale = ContentScale.Fit,
            colorFilter = ColorFilter.tint(MaterialTheme.colorScheme.primary),
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.about_version, BuildConfig.VERSION_NAME),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = stringResource(R.string.about_license),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = stringResource(R.string.about_attribution),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = stringResource(R.string.about_zone_data),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        }
    }
}

// SYSTEM_ALERT_WINDOW is a special permission: it can't be requested with a
// runtime dialog, only granted from the per-app "Display over other apps"
// system Settings screen. We keep the toggle on and let the service's
// visibility gate activate the overlay once the user returns with it granted.
private fun requestOverlayPermission(context: Context) {
    val intent = Intent(
        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
        Uri.fromParts("package", context.packageName, null),
    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    context.startActivity(intent)
}
