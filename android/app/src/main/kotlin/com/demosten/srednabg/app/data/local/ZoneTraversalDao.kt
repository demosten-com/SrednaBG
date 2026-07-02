// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ZoneTraversalDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(traversal: ZoneTraversalEntity)

    /** All records, most-recently-exited first — drives the History list. */
    @Query("SELECT * FROM zone_traversals ORDER BY exitTimeMs DESC")
    fun getAll(): Flow<List<ZoneTraversalEntity>>

    @Query("SELECT * FROM zone_traversals WHERE id = :id")
    suspend fun getById(id: String): ZoneTraversalEntity?

    /** Most-recently-exited record — QA `DUMP_HISTORY` summary. */
    @Query("SELECT * FROM zone_traversals ORDER BY exitTimeMs DESC LIMIT 1")
    suspend fun latest(): ZoneTraversalEntity?

    /** Retention pruning: drop everything that exited before [cutoffMs]. */
    @Query("DELETE FROM zone_traversals WHERE exitTimeMs < :cutoffMs")
    suspend fun deleteOlderThan(cutoffMs: Long)

    @Query("DELETE FROM zone_traversals")
    suspend fun deleteAll()

    @Query("SELECT COUNT(*) FROM zone_traversals")
    suspend fun count(): Int
}
