// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.remote

import com.demosten.srednabg.BuildConfig
import com.demosten.srednabg.core.Zone
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException

data class VersionResponse(
    val version: String,
    val hash: String,
    @SerializedName("min_app_version") val minAppVersion: String? = null,
    @SerializedName("zone_count") val zoneCount: Int? = null,
    @SerializedName("map_hash") val mapHash: String? = null,
)

data class ZonesResponse(
    val version: String,
    val hash: String,
    val zones: List<Zone>,
)

class ZoneApi(
    private val client: OkHttpClient,
    private val gson: Gson,
) {
    companion object {
        val BASE_URL: String = BuildConfig.ZONE_API_BASE_URL
    }

    suspend fun fetchVersion(): VersionResponse = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$BASE_URL/api/version")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Version API returned ${response.code}")
            val body = response.body?.string() ?: throw IOException("Empty version response")
            gson.fromJson(body, VersionResponse::class.java)
        }
    }

    suspend fun fetchZones(): ZonesResponse = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$BASE_URL/api/zones")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Zones API returned ${response.code}")
            val body = response.body?.string() ?: throw IOException("Empty zones response")
            gson.fromJson(body, object : TypeToken<ZonesResponse>() {}.type)
        }
    }
}
