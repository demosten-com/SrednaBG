plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    // Target JVM 17 without pinning a Gradle *toolchain*: a strict toolchain
    // forces JDK-17 discovery, which fails in F-Droid's build sandbox (no
    // matching toolchain + auto-provisioning disabled). compilerOptions targets
    // the bytecode level using whichever JDK (>= 17) runs Gradle instead.
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

dependencies {
    testImplementation(libs.junit5.api)
    testImplementation(libs.junit5.params)
    testImplementation(libs.kotlinx.serialization.json)
    testRuntimeOnly(libs.junit5.engine)
}

tasks.withType<Test> {
    useJUnitPlatform()
}
