// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.demosten.srednabg.app.FeatureFlags
import com.demosten.srednabg.app.data.MapRepository
import com.demosten.srednabg.app.data.SyncResult
import com.demosten.srednabg.app.data.ZoneRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Debug-only: fire a map or zone sync from `adb shell am broadcast`.
 *
 *   adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver \
 *       -a com.demosten.srednabg.debug.SYNC_MAP
 *   adb shell am broadcast -n com.demosten.srednabg/com.demosten.srednabg.app.debug.DebugSyncReceiver \
 *       -a com.demosten.srednabg.debug.SYNC_ZONES
 *
 * Logs the SyncResult under tag DebugSync.
 */
@AndroidEntryPoint
class DebugSyncReceiver : BroadcastReceiver() {

    @Inject lateinit var mapRepository: MapRepository
    @Inject lateinit var zoneRepository: ZoneRepository

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onReceive(context: Context, intent: Intent) {
        val pendingResult = goAsync()
        scope.launch {
            try {
                val result: SyncResult = when (intent.action) {
                    ACTION_SYNC_MAP -> {
                        // Map sync is gated on FeatureFlags.IS_MAP_SYNC_ENABLED
                        // (off until the production backend serves the bundle).
                        // The QA harness talks to prod, so a debug-triggered
                        // sync against a backend that can't fulfill it would
                        // only generate failure noise.
                        if (!FeatureFlags.IS_MAP_SYNC_ENABLED) {
                            Log.i(TAG, "${intent.action} -> Skipped (feature disabled)")
                            return@launch
                        }
                        mapRepository.syncFromServer()
                    }
                    ACTION_SYNC_ZONES -> zoneRepository.syncFromServer()
                    else -> {
                        Log.w(TAG, "Unknown action: ${intent.action}")
                        return@launch
                    }
                }
                Log.i(TAG, "${intent.action} -> $result")
            } finally {
                pendingResult.finish()
            }
        }
    }

    companion object {
        private const val TAG = "DebugSync"
        const val ACTION_SYNC_MAP = "com.demosten.srednabg.debug.SYNC_MAP"
        const val ACTION_SYNC_ZONES = "com.demosten.srednabg.debug.SYNC_ZONES"
    }
}
