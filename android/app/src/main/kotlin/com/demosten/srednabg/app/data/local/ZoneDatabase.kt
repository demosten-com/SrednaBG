// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [ZoneEntity::class, ZoneTraversalEntity::class],
    version = 2,
    exportSchema = false,
)
abstract class ZoneDatabase : RoomDatabase() {
    abstract fun zoneDao(): ZoneDao
    abstract fun zoneTraversalDao(): ZoneTraversalDao

    companion object {
        /**
         * v1 → v2: adds the History feature's `zone_traversals` table. Purely
         * additive — it does NOT touch the `zones` table, so the re-syncable
         * zone cache is preserved across the upgrade instead of being wiped by
         * the destructive fallback. The CREATE TABLE must match the schema Room
         * derives from [ZoneTraversalEntity] exactly (column order, types,
         * nullability, PK), or Room's open-time validation throws.
         */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `zone_traversals` (" +
                        "`id` TEXT NOT NULL, " +
                        "`zoneId` TEXT NOT NULL, " +
                        "`road` TEXT NOT NULL, " +
                        "`roadLatin` TEXT, " +
                        "`direction` TEXT NOT NULL, " +
                        "`speedLimitKmh` INTEGER NOT NULL, " +
                        "`vehicleType` TEXT NOT NULL, " +
                        "`entryTimeMs` INTEGER NOT NULL, " +
                        "`exitTimeMs` INTEGER NOT NULL, " +
                        "`avgSpeedKmh` REAL, " +
                        "`sustainedMinKmh` REAL NOT NULL, " +
                        "`sustainedMaxKmh` REAL NOT NULL, " +
                        "`isOverLimit` INTEGER NOT NULL, " +
                        "`distanceM` INTEGER NOT NULL, " +
                        "`samplesJson` TEXT NOT NULL, " +
                        "PRIMARY KEY(`id`))"
                )
            }
        }
    }
}
