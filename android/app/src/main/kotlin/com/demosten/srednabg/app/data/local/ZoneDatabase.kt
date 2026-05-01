// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(entities = [ZoneEntity::class], version = 1, exportSchema = false)
abstract class ZoneDatabase : RoomDatabase() {
    abstract fun zoneDao(): ZoneDao
}
