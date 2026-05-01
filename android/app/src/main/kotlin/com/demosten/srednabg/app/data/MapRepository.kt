// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 SrednaBG Contributors
//
// SrednaBG — android / app

package com.demosten.srednabg.app.data

import android.content.Context
import com.demosten.srednabg.BuildConfig
import com.demosten.srednabg.app.data.remote.MapApi
import com.demosten.srednabg.app.data.remote.ZoneApi
import com.demosten.srednabg.core.MapTheme
import com.google.gson.Gson
import com.google.gson.JsonObject
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.util.zip.ZipInputStream
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class MapRepository @Inject constructor(
    private val mapApi: MapApi,
    private val zoneApi: ZoneApi,
    private val settingsRepository: SettingsRepository,
    private val gson: Gson,
    @ApplicationContext private val context: Context,
) {
    /**
     * On first launch (or if the on-disk map dir is missing/incomplete), copy the
     * bundled map assets from `assets/map/` into `filesDir/map/`. SQLite can't mmap
     * APK assets, so MBTiles must live as a real file on the filesystem.
     */
    suspend fun ensureLoaded() = withContext(Dispatchers.IO) {
        val mapDir = mapDir()
        val tiles = File(mapDir, MBTILES_FILE)
        val haveAllStyles = STYLE_FILES.values.all { File(mapDir, it).exists() }
        if (haveAllStyles && tiles.exists()) return@withContext

        if (!hasBundledMap()) return@withContext
        mapDir.mkdirs()
        copyAssetTree(ASSET_ROOT, mapDir)
        rewriteStylePlaceholders(mapDir)
        persistBundledHash(mapDir)
    }

    suspend fun syncFromServer(): SyncResult = withContext(Dispatchers.IO) {
        try {
            val version = zoneApi.fetchVersion()
            val remoteHash = version.mapHash ?: return@withContext SyncResult.UpToDate
            val cachedHash = settingsRepository.cachedMapHash.first()
            if (remoteHash == cachedHash && cachedHash.isNotEmpty()) {
                return@withContext SyncResult.UpToDate
            }

            val zipFile = File(context.cacheDir, "map-bundle.zip")
            val stagingDir = File(context.filesDir, STAGING_DIR)
            try {
                mapApi.downloadBundle(zipFile)
                if (stagingDir.exists()) stagingDir.deleteRecursively()
                stagingDir.mkdirs()
                unzip(zipFile, stagingDir)

                // Sanity check: new bundle must have every required file before we swap
                val newTiles = File(stagingDir, MBTILES_FILE)
                val missing = STYLE_FILES.values.firstOrNull { !File(stagingDir, it).exists() }
                if (!newTiles.exists() || missing != null) {
                    throw IOException(
                        "Downloaded bundle missing ${missing ?: MBTILES_FILE}"
                    )
                }

                swapMapDir(stagingDir)
                rewriteStylePlaceholders(mapDir())
                settingsRepository.setCachedMapHash(remoteHash)
                SyncResult.Updated
            } finally {
                zipFile.delete()
                if (stagingDir.exists()) stagingDir.deleteRecursively()
            }
        } catch (e: Exception) {
            SyncResult.Failed(e)
        }
    }

    /**
     * Returns the style URI MapLibre should load for the requested theme.
     * Prefers the on-disk copy; falls back to the backend URL when the
     * bundle isn't installed (debug-only path — the dark variant only
     * exists in the bundle, so the URL fallback is light for both modes).
     */
    fun localStyleUri(theme: MapTheme): String {
        val fileName = STYLE_FILES.getValue(theme)
        val style = File(mapDir(), fileName)
        return if (style.exists()) "file://${style.absolutePath}" else BuildConfig.MAP_STYLE_URL
    }

    private fun mapDir(): File = File(context.filesDir, MAP_DIR)

    private fun hasBundledMap(): Boolean {
        val entries = context.assets.list(ASSET_ROOT) ?: return false
        return STYLE_FILES.values.all { entries.contains(it) } && entries.contains(MBTILES_FILE)
    }

    private fun copyAssetTree(assetPath: String, destDir: File) {
        val entries = context.assets.list(assetPath) ?: return
        if (entries.isEmpty()) {
            // Leaf: copy the file
            context.assets.open(assetPath).use { input ->
                destDir.outputStream().use { output -> input.copyTo(output) }
            }
            return
        }
        destDir.mkdirs()
        for (entry in entries) {
            val childAssetPath = "$assetPath/$entry"
            val childDest = File(destDir, entry)
            val childEntries = context.assets.list(childAssetPath) ?: emptyArray()
            if (childEntries.isEmpty()) {
                context.assets.open(childAssetPath).use { input ->
                    childDest.outputStream().use { output -> input.copyTo(output) }
                }
            } else {
                copyAssetTree(childAssetPath, childDest)
            }
        }
    }

    /**
     * The shipped style.json carries a `{MBTILES_URI}` placeholder for the vector
     * source's TileJSON `url` so the backend script can stay agnostic to install
     * paths. MapLibre's native MBTilesFileSource expects just `mbtiles://<file-path>`
     * — it opens the path as SQLite, reads the mbtiles metadata, and derives tile
     * URLs internally. Including `{z}/{x}/{y}` in this URI makes SQLite open fail
     * and abort the MBTilesFileSource thread.
     */
    private fun rewriteStylePlaceholders(mapDir: File) {
        val mbtilesUri = "mbtiles://" + File(mapDir, MBTILES_FILE).absolutePath
        val fontsBaseUri = "file://" + File(mapDir, FONTS_DIR).absolutePath
        val spriteUri = "file://" + File(mapDir, SPRITE_BASENAME).absolutePath
        for (fileName in STYLE_FILES.values) {
            val style = File(mapDir, fileName)
            if (!style.exists()) continue
            val patched = style.readText()
                .replace(MBTILES_PLACEHOLDER, mbtilesUri)
                .replace(GLYPHS_PLACEHOLDER, fontsBaseUri)
                .replace(SPRITE_PLACEHOLDER, spriteUri)
            style.writeText(patched)
        }
    }

    private suspend fun persistBundledHash(mapDir: File) {
        val versionFile = File(mapDir, VERSION_FILE)
        if (!versionFile.exists()) return
        val hash = try {
            gson.fromJson(versionFile.readText(), JsonObject::class.java)
                ?.get("map_hash")?.asString
        } catch (_: Exception) {
            null
        }
        if (!hash.isNullOrEmpty()) settingsRepository.setCachedMapHash(hash)
    }

    private fun unzip(zipFile: File, destDir: File) {
        ZipInputStream(zipFile.inputStream().buffered()).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val target = File(destDir, entry.name).canonicalFile
                // Zip-slip guard
                if (!target.absolutePath.startsWith(destDir.canonicalPath + File.separator) &&
                    target.absolutePath != destDir.canonicalPath
                ) {
                    throw IOException("Zip entry escapes destination: ${entry.name}")
                }
                if (entry.isDirectory) {
                    target.mkdirs()
                } else {
                    target.parentFile?.mkdirs()
                    target.outputStream().use { out -> zis.copyTo(out) }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    private fun swapMapDir(stagingDir: File) {
        val finalDir = mapDir()
        val backupDir = File(context.filesDir, BACKUP_DIR)
        if (backupDir.exists()) backupDir.deleteRecursively()
        if (finalDir.exists() && !finalDir.renameTo(backupDir)) {
            throw IOException("Failed to move old map dir aside")
        }
        if (!stagingDir.renameTo(finalDir)) {
            if (backupDir.exists()) backupDir.renameTo(finalDir)
            throw IOException("Failed to install new map dir")
        }
        if (backupDir.exists()) backupDir.deleteRecursively()
    }

    companion object {
        private const val ASSET_ROOT = "map"
        private const val MAP_DIR = "map"
        private const val STAGING_DIR = "map.staging"
        private const val BACKUP_DIR = "map.old"
        private const val MBTILES_FILE = "bulgaria.mbtiles"
        private const val VERSION_FILE = "version.json"
        private const val FONTS_DIR = "fonts"
        private const val SPRITE_BASENAME = "sprite"
        private const val MBTILES_PLACEHOLDER = "{MBTILES_URI}"
        private const val GLYPHS_PLACEHOLDER = "{GLYPHS_URI}"
        private const val SPRITE_PLACEHOLDER = "{SPRITE_URI}"
        private val STYLE_FILES: Map<MapTheme, String> = mapOf(
            MapTheme.LIGHT to "style-light.json",
            MapTheme.DARK to "style-dark.json",
        )
    }
}
