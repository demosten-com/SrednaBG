import java.time.Duration
import java.time.Instant

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "com.demosten.srednabg"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.demosten.srednabg"
        minSdk = 26
        targetSdk = 36
        // Literal defaults so F-Droid's checkupdates can statically parse the
        // version (a computed expression yields "no version information"). The
        // android-release.yml workflow overrides these from the git tag for
        // GitHub/Play builds; F-Droid builds use the literals as-is.
        versionCode = 20000
        versionName = "2.0.0"
        (project.findProperty("SREDNABG_VERSION_CODE") as String?)?.let { versionCode = it.toInt() }
        (project.findProperty("SREDNABG_VERSION_NAME") as String?)?.let { versionName = it }
        resourceConfigurations += listOf("bg", "en")

        // Both debug and release hit the production Namecheap host so dev
        // builds always test against real zone data.
        buildConfigField("String", "ZONE_API_BASE_URL", "\"https://srednabg.com\"")
        buildConfigField("String", "MAP_STYLE_URL", "\"https://srednabg.com/tiles/styles/basic-preview/style.json\"")
    }

    // Two distribution flavors differing only in the location provider:
    //   aosp — LocationManager only, zero Google dependencies. Ships to
    //          F-Droid (which rejects proprietary GMS libs) and GitHub
    //          Releases (works on every phone, incl. de-Googled).
    //   gms  — adds FusedLocationProviderClient (better fused/batched fixes
    //          where Play Services exists), with a runtime fallback to the
    //          AOSP path. Ships to the Play Store. Default.
    // The provider-specific code lives in src/{aosp,gms}/; src/main/ never
    // references a GMS type, so the aosp variant compiles without
    // play-services-location and passes F-Droid's source scanner.
    flavorDimensions += "distribution"
    productFlavors {
        create("aosp") {
            dimension = "distribution"
        }
        create("gms") {
            dimension = "distribution"
            isDefault = true
        }
    }

    val hasReleaseKeystore = project.hasProperty("SREDNABG_RELEASE_STORE_FILE")

    signingConfigs {
        create("release") {
            if (hasReleaseKeystore) {
                storeFile = file(project.property("SREDNABG_RELEASE_STORE_FILE") as String)
                storePassword = project.property("SREDNABG_RELEASE_STORE_PASSWORD") as String
                keyAlias = project.property("SREDNABG_RELEASE_KEY_ALIAS") as String
                keyPassword = project.property("SREDNABG_RELEASE_KEY_PASSWORD") as String
                enableV1Signing = false
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            if (hasReleaseKeystore) {
                signingConfig = signingConfigs.getByName("release")
            }
            // Bundle a symbol table for native libs (MapLibre's libmapbox-gl.so) into the
            // AAB so Play Console can symbolicate native crashes/ANRs. Without this, Play
            // warns about missing debug symbols on every upload. SYMBOL_TABLE keeps the
            // size hit small (vs. FULL, which also embeds line numbers).
            ndk {
                debugSymbolLevel = "SYMBOL_TABLE"
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    testOptions {
        // Return defaults (0/false/null) from un-stubbed android.* calls (e.g.
        // android.util.Log) in JVM unit tests instead of throwing, so tests don't
        // each have to mockkStatic(Log).
        unitTests.isReturnDefaultValues = true
    }

    lint {
        // CI runs `./gradlew lint`. Freeze the current state in a baseline so only
        // newly-introduced issues fail the build, not the pre-existing backlog.
        abortOnError = true
        baseline = file("lint-baseline.xml")
    }
}

dependencies {
    implementation(project(":core"))

    // AndroidX Core
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.appcompat)

    // Compose
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    // Lifecycle
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.service)
    implementation(libs.lifecycle.process)

    // Car App Library
    implementation(libs.car.app)
    implementation(libs.car.app.projected)

    // Room
    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)

    // Hilt
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)
    implementation(libs.hilt.work)
    ksp(libs.hilt.work.compiler)

    // WorkManager
    implementation(libs.work.runtime.ktx)

    // Navigation
    implementation(libs.navigation.compose)

    // DataStore
    implementation(libs.datastore.preferences)

    // Google Play Services — gms flavor only. Declared with the
    // `gmsImplementation` configuration so it's absent from the aosp variant's
    // dependency graph (and from F-Droid's flavor-aware source scanner, which
    // keys off the metadata `gradle: [aosp]` compile commands).
    "gmsImplementation"(libs.play.services.location)

    // Network / JSON
    implementation(libs.okhttp)
    implementation(libs.gson)

    // Coroutines
    implementation(libs.coroutines.core)
    implementation(libs.coroutines.android)

    // MapLibre
    implementation(libs.maplibre.android)

    // Compose extras
    implementation(libs.compose.material.icons.extended)

    // Testing
    testImplementation(libs.junit5.api)
    testRuntimeOnly(libs.junit5.engine)
    testImplementation(libs.junit5.params)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// Stages the generated map bundle (from backend/data/map-bundle/) into the APK's
// assets/map/ directory. The bundle is produced by `backend/scripts/build-map-bundle.sh`
// and intentionally kept out of git. The build FAILS if the bundle is missing or
// incomplete — the app is designed offline-first and shipping without the bundle
// would hand users a blank map on first launch.
val mapBundleSource = rootProject.file("../backend/data/map-bundle")
val mapAssetsDest = layout.projectDirectory.dir("src/main/assets/map")
val requiredMapFiles = listOf("style-light.json", "style-dark.json", "bulgaria.mbtiles")

// Separate validation task — Gradle's Copy short-circuits with NO-SOURCE when
// `from()` resolves to an empty collection, which skips any `doFirst`. Running
// the check in a plain task ahead of the Copy guarantees it always fires.
val validateMapBundle by tasks.registering {
    group = "build"
    description = "Fail the build when the offline map bundle is missing or incomplete"
    outputs.upToDateWhen { false }
    doLast {
        if (!mapBundleSource.exists()) {
            throw GradleException(
                "[validateMapBundle] offline map bundle not found at $mapBundleSource. " +
                    "Run `bash backend/scripts/build-map-bundle.sh` to generate it."
            )
        }
        val missing = requiredMapFiles.filterNot { File(mapBundleSource, it).exists() }
        if (missing.isNotEmpty()) {
            throw GradleException(
                "[validateMapBundle] offline map bundle at $mapBundleSource is missing: " +
                    missing.joinToString(", ") +
                    ". Regenerate it with `bash backend/scripts/build-map-bundle.sh`."
            )
        }
    }
}

val prepareMapAssets by tasks.registering(Copy::class) {
    group = "build"
    description = "Stage generated map bundle into assets/map/"
    dependsOn(validateMapBundle)
    from(mapBundleSource)
    into(mapAssetsDest)
    doFirst {
        mapAssetsDest.asFile.deleteRecursively()
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Single source of truth for bundled zone data: backend/data/zones.json — the
// SAME file iOS bundles via its `Bundled Zones` Run Script phase. The Android
// asset (src/main/assets/zones.json) is GENERATED from it at build time and is
// gitignored (NOT committed), so the two platforms can never ship different
// zone data for the same release. The build FAILS if the source is missing —
// offline-first means shipping without zones would break the app.
val zonesSource = rootProject.file("../backend/data/zones.json")
val zonesAssetDest = layout.projectDirectory.file("src/main/assets/zones.json")
val zoneRefreshCmd = "bash scrapers/scripts/refresh-zones.sh"

val prepareZonesAsset by tasks.registering {
    group = "build"
    description = "Stage backend/data/zones.json into assets/zones.json (single source of truth, shared with iOS)"
    inputs.file(zonesSource)
    outputs.file(zonesAssetDest)
    doLast {
        if (!zonesSource.exists()) {
            throw GradleException(
                "[prepareZonesAsset] bundled zones JSON not found at $zonesSource. " +
                    "Regenerate it with `$zoneRefreshCmd`."
            )
        }
        zonesSource.copyTo(zonesAssetDest.asFile, overwrite = true)
    }
}

// Zone-data freshness check. zones.json is a point-in-time scrape (its top-level
// `version` field is the scrape timestamp, ISO-8601 UTC). Zone data older than
// this many days may ship outdated camera zones / speed limits, so warn at build
// time and print the exact refresh command. This only WARNS — it never fails the
// build — so a machine without Python / network can still build. Reads the
// shared source directly (mirrors the iOS `Bundled Zones` Run Script phase).
val zoneDataMaxAgeDays = 10L

val checkZoneDataFreshness by tasks.registering {
    group = "verification"
    description = "Warn when backend/data/zones.json is older than $zoneDataMaxAgeDays days"
    outputs.upToDateWhen { false }
    doLast {
        if (!zonesSource.exists()) return@doLast
        // Read only the head — `version` is the first key and the file is ~1.4 MB.
        val head = zonesSource.bufferedReader().use { reader ->
            val buf = CharArray(8192)
            val n = reader.read(buf)
            if (n > 0) String(buf, 0, n) else ""
        }
        val version = Regex("\"version\"\\s*:\\s*\"([^\"]+)\"").find(head)?.groupValues?.get(1)
        if (version == null) {
            logger.warn("[checkZoneDataFreshness] could not find \"version\" in ${zonesSource.path}; skipping freshness check.")
            return@doLast
        }
        val scraped = try {
            Instant.parse(version)
        } catch (e: Exception) {
            logger.warn("[checkZoneDataFreshness] unparseable version \"$version\" in ${zonesSource.path}; skipping freshness check.")
            return@doLast
        }
        val ageDays = Duration.between(scraped, Instant.now()).toDays()
        if (ageDays > zoneDataMaxAgeDays) {
            logger.warn(
                "\nwarning: Bundled zone data is $ageDays days old (scraped $version; " +
                    "threshold $zoneDataMaxAgeDays days). Camera zones / speed limits may be stale.\n" +
                    "         Refresh it with:\n" +
                    "             $zoneRefreshCmd\n"
            )
        }
    }
}

tasks.named("preBuild") {
    dependsOn(prepareMapAssets)
    dependsOn(prepareZonesAsset)
    dependsOn(checkZoneDataFreshness)
}
