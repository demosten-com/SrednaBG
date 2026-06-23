// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data.remote

import com.demosten.srednabg.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okio.buffer
import okio.sink
import java.io.File
import java.io.IOException

class MapApi(
    private val client: OkHttpClient,
) {
    companion object {
        val BASE_URL: String = BuildConfig.ZONE_API_BASE_URL

        // The real bundle is tens of MB. Reject a download advertising far more
        // (mis-served or MITM'd) before streaming it to disk and exhausting
        // storage. Extraction is separately capped in MapRepository.unzip.
        private const val MAX_DOWNLOAD_BYTES = 512L * 1024 * 1024
    }

    suspend fun downloadBundle(destination: File): Unit = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$BASE_URL/api/map/bundle.zip")
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Map bundle API returned ${response.code}")
            val body = response.body ?: throw IOException("Empty map bundle response")
            val declaredLength = response.header("Content-Length")?.toLongOrNull()
            if (declaredLength != null && declaredLength > MAX_DOWNLOAD_BYTES) {
                throw IOException(
                    "Map bundle too large: $declaredLength bytes (max $MAX_DOWNLOAD_BYTES)",
                )
            }
            destination.sink().buffer().use { sink ->
                sink.writeAll(body.source())
            }
        }
    }
}
