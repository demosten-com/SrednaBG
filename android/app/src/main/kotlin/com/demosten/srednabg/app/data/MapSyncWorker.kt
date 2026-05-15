// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.demosten.srednabg.app.FeatureFlags
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

@HiltWorker
class MapSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val mapRepository: MapRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        // Defensive: WorkManager persists periodic work across upgrades, so a
        // build that previously enqueued map_sync can still wake this worker
        // even after SrednaBGApp.onCreate stops scheduling it. Short-circuit
        // here too. See FeatureFlags.IS_MAP_SYNC_ENABLED.
        if (!FeatureFlags.IS_MAP_SYNC_ENABLED) return Result.success()
        return when (mapRepository.syncFromServer()) {
            is SyncResult.Updated, SyncResult.UpToDate -> Result.success()
            is SyncResult.Failed -> Result.retry()
        }
    }
}
