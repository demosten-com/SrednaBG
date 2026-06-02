// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first

@HiltWorker
class ZoneSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val zoneRepository: ZoneRepository,
    private val settingsRepository: SettingsRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        // Defensive: WorkManager persists periodic work across upgrades, so a
        // worker can still fire after SrednaBGApp or the Settings toggle
        // cancelled it (e.g. the user disabled "Automatic zone updates" in a
        // prior session). Short-circuit here too.
        if (!settingsRepository.zoneSyncEnabled.first()) return Result.success()
        return when (zoneRepository.syncFromServer()) {
            is SyncResult.Updated, SyncResult.UpToDate -> Result.success()
            is SyncResult.Failed -> Result.retry()
        }
    }
}
