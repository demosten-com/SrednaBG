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
    /**
     * Set by the backend when this build's data feed is no longer maintained.
     * Any non-zero value means "tell the user to update"; absent is the normal,
     * supported state. Read via [isFeedUnsupported] rather than directly — the
     * field is deliberately an Int so a future `true` decodes as well as `1`.
     */
    val unsupported: Int? = null,
) {
    /** Whether this feed has been retired and stopped receiving fresh data. */
    val isFeedUnsupported: Boolean get() = (unsupported ?: 0) != 0
}

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

        /**
         * Path for [name] on [feed]: `/api/zones` on feed 1, `/api/zones.N`
         * beyond.
         *
         * Feed 1 carrying no suffix is the compatibility promise — every
         * release published so far fetches `/api/zones`, and that URL must keep
         * resolving. Kept a pure function of [feed] rather than reading
         * `BuildConfig` directly so the rule is testable for a feed this build
         * isn't compiled against; pointing a build at the wrong feed is silent,
         * and the data it then syncs looks perfectly valid. Swift twin:
         * `BackendURLs.endpointPath`.
         */
        internal fun endpointPath(name: String, feed: Int): String =
            if (feed == 1) "/api/$name" else "/api/$name.$feed"

        /** [endpointPath] on the feed this build was compiled against. */
        internal fun endpoint(name: String): String =
            BASE_URL + endpointPath(name, BuildConfig.ZONE_FEED_VERSION)
    }

    suspend fun fetchVersion(): VersionResponse = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(endpoint("version"))
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Version API returned ${response.code}")
            val body = response.body?.string() ?: throw IOException("Empty version response")
            gson.fromJson(body, VersionResponse::class.java)
        }
    }

    suspend fun fetchZones(): ZonesResponse = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(endpoint("zones"))
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Zones API returned ${response.code}")
            val body = response.body?.string() ?: throw IOException("Empty zones response")
            gson.fromJson(body, object : TypeToken<ZonesResponse>() {}.type)
        }
    }
}
