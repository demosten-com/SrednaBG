// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Owns the WorkManager plumbing for the periodic zone-data sync so the unique
 * work name and the request shape live in exactly one place. Both
 * [com.demosten.srednabg.app.SrednaBGApp] (at startup) and
 * [com.demosten.srednabg.app.ui.viewmodel.SettingsViewModel] (when the user
 * flips the "Automatic zone updates" toggle) drive scheduling through here.
 *
 * The sync is a user-facing opt-out (default on): [enable] enqueues the 6 h
 * periodic job, [disable] cancels it. [ZoneSyncWorker] additionally
 * short-circuits if the setting is off, since WorkManager persists periodic
 * work across upgrades.
 */
@Singleton
class ZoneSyncScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    fun enable() {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val syncRequest = PeriodicWorkRequestBuilder<ZoneSyncWorker>(6, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            syncRequest,
        )
    }

    fun disable() {
        WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK_NAME)
    }

    companion object {
        const val UNIQUE_WORK_NAME = "zone_sync"
    }
}
