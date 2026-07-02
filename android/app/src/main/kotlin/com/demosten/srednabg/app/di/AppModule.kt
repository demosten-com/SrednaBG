// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStoreFile
import androidx.room.Room
import com.demosten.srednabg.app.data.local.ZoneDao
import com.demosten.srednabg.app.data.local.ZoneDatabase
import com.demosten.srednabg.app.data.local.ZoneTraversalDao
import com.demosten.srednabg.app.data.remote.MapApi
import com.demosten.srednabg.app.data.remote.ZoneApi
import com.google.gson.FieldNamingPolicy
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideGson(): Gson = GsonBuilder()
        .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create()

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Provides
    @Singleton
    fun provideZoneDatabase(@ApplicationContext context: Context): ZoneDatabase =
        Room.databaseBuilder(context, ZoneDatabase::class.java, "srednabg.db")
            // v1 → v2 adds the History `zone_traversals` table additively so the
            // re-syncable zone cache survives the upgrade (see MIGRATION_1_2).
            .addMigrations(ZoneDatabase.MIGRATION_1_2)
            // Backstop for any unforeseen path: zones are fully re-syncable
            // (bundled asset + server sync), so a schema bump with no migration
            // can safely drop and rebuild rather than crash on launch. History is
            // best-effort local data, acceptable to lose in that edge case.
            .fallbackToDestructiveMigration(dropAllTables = true)
            .build()

    @Provides
    fun provideZoneDao(db: ZoneDatabase): ZoneDao = db.zoneDao()

    @Provides
    fun provideZoneTraversalDao(db: ZoneDatabase): ZoneTraversalDao = db.zoneTraversalDao()

    @Provides
    @Singleton
    fun provideZoneApi(client: OkHttpClient, gson: Gson): ZoneApi = ZoneApi(client, gson)

    @Provides
    @Singleton
    fun provideMapApi(client: OkHttpClient): MapApi = MapApi(client)

    // The FusedLocationProviderClient provider used to live here. It moved out
    // of DI when the location source became flavor-specific: the gms flavor's
    // createLocationSource() builds the client itself, and the aosp flavor has
    // no GMS dependency at all. See src/{aosp,gms}/.../LocationSourceFactory.kt.

    @Provides
    @Singleton
    fun provideDataStore(@ApplicationContext context: Context): DataStore<Preferences> =
        PreferenceDataStoreFactory.create {
            context.preferencesDataStoreFile("settings")
        }
}
