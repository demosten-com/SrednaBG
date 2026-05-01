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

@HiltWorker
class ZoneSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val zoneRepository: ZoneRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = when (zoneRepository.syncFromServer()) {
        is SyncResult.Updated, SyncResult.UpToDate -> Result.success()
        is SyncResult.Failed -> Result.retry()
    }
}
