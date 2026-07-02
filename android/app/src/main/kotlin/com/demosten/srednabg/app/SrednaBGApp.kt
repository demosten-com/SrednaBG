// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app

import android.app.Application
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.demosten.srednabg.app.data.HistoryRepository
import com.demosten.srednabg.app.data.HistoryRetention
import com.demosten.srednabg.app.data.MapSyncWorker
import com.demosten.srednabg.app.data.SettingsRepository
import com.demosten.srednabg.app.data.ZoneSyncScheduler
import dagger.hilt.android.HiltAndroidApp
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

@HiltAndroidApp
class SrednaBGApp : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory
    @Inject lateinit var settingsRepository: SettingsRepository
    @Inject lateinit var zoneSyncScheduler: ZoneSyncScheduler
    @Inject lateinit var historyRepository: HistoryRepository

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()
        applyPersistedLocale()
        applyZoneSync()
        applyHistoryRetention()
        if (FeatureFlags.IS_MAP_SYNC_ENABLED) {
            scheduleMapSync()
        }
    }

    private fun applyHistoryRetention() {
        // Prune once on launch, then on every retention-setting change (which
        // includes switching to "none" — that purges everything). The Flow emits
        // the current value immediately, so this covers the launch prune too.
        appScope.launch {
            settingsRepository.historyRetention.distinctUntilChanged().collect { value ->
                historyRepository.prune(HistoryRetention.fromSetting(value))
            }
        }
    }

    private fun applyPersistedLocale() {
        val code = runBlocking { settingsRepository.appLanguage.first() }
        val tags = if (code == SettingsRepository.LANG_SYSTEM) "" else code
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tags))
    }

    private fun applyZoneSync() {
        // The periodic zone sync is a user opt-out ("Automatic zone updates"),
        // default on. Re-apply the persisted choice every launch so a build
        // that previously enqueued it respects a later opt-out. Mirrors the
        // existing runBlocking startup read in applyPersistedLocale().
        if (runBlocking { settingsRepository.zoneSyncEnabled.first() }) {
            zoneSyncScheduler.enable()
        } else {
            zoneSyncScheduler.disable()
        }
    }

    private fun scheduleMapSync() {
        // Map bundle is ~100 MB+ — require unmetered to avoid burning cellular data.
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.UNMETERED)
            .build()
        val syncRequest = PeriodicWorkRequestBuilder<MapSyncWorker>(6, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "map_sync",
            ExistingPeriodicWorkPolicy.KEEP,
            syncRequest,
        )
    }
}
