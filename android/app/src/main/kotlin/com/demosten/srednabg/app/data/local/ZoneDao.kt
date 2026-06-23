// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Dao
interface ZoneDao {

    @Query("SELECT * FROM zones")
    fun getAllZones(): Flow<List<ZoneEntity>>

    @Query("SELECT * FROM zones WHERE id = :id")
    suspend fun getZoneById(id: String): ZoneEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(zones: List<ZoneEntity>)

    @Query("DELETE FROM zones")
    suspend fun deleteAll()

    @Transaction
    suspend fun replaceAll(zones: List<ZoneEntity>) {
        deleteAll()
        insertAll(zones)
    }

    @Query("SELECT COUNT(*) FROM zones")
    suspend fun count(): Int
}
