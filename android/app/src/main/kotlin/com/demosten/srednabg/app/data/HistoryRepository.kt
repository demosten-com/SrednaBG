// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import com.demosten.srednabg.app.data.local.ZoneTraversalDao
import com.demosten.srednabg.app.data.local.ZoneTraversalEntity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Retention window for the History tab. `NONE` records nothing and purges what's
 * already stored; the others keep records younger than that many months.
 */
enum class HistoryRetention(val setting: String, val months: Int) {
    NONE("none", 0),
    ONE_MONTH("1month", 1),
    THREE_MONTHS("3months", 3),
    SIX_MONTHS("6months", 6),
    ;

    companion object {
        val DEFAULT = THREE_MONTHS

        /** Map a `SettingsRepository.historyRetention` string; unknown → [DEFAULT]. */
        fun fromSetting(setting: String): HistoryRetention =
            entries.firstOrNull { it.setting == setting } ?: DEFAULT
    }
}

/**
 * Thin persistence wrapper around [ZoneTraversalDao] for the History feature.
 * Kept separate from [ZoneRepository] because zone traversals and the zone
 * catalog have unrelated lifecycles (one is user-generated and pruned by
 * retention, the other is a re-syncable cache).
 */
@Singleton
class HistoryRepository @Inject constructor(
    private val dao: ZoneTraversalDao,
) {
    fun observeAll(): Flow<List<ZoneTraversalEntity>> = dao.getAll()

    suspend fun record(traversal: ZoneTraversalEntity) = dao.insert(traversal)

    suspend fun getById(id: String): ZoneTraversalEntity? = dao.getById(id)

    suspend fun latest(): ZoneTraversalEntity? = dao.latest()

    suspend fun count(): Int = dao.count()

    /**
     * Apply a retention window: [HistoryRetention.NONE] clears everything, any
     * other keeps records that exited within the last [HistoryRetention.months].
     * [nowMs] is injectable so tests / the recorder can pin a clock.
     */
    suspend fun prune(retention: HistoryRetention, nowMs: Long = System.currentTimeMillis()) {
        if (retention == HistoryRetention.NONE) {
            dao.deleteAll()
            return
        }
        val cutoff = nowMs - retention.months * APPROX_MONTH_MS
        dao.deleteOlderThan(cutoff)
    }

    suspend fun clearAll() = dao.deleteAll()

    private companion object {
        // Retention is a coarse "how long to keep" preference, not a calendar
        // computation — 30 days per month is close enough and avoids dragging a
        // full date library into the pruning path.
        const val APPROX_MONTH_MS = 30L * 24 * 60 * 60 * 1000
    }
}
