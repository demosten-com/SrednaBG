# SrednaBG ProGuard/R8 rules

# Keep Gson-serialized data classes (uses reflection)
-keep class com.demosten.srednabg.core.Zone { *; }
-keep class com.demosten.srednabg.core.ZoneEndpoint { *; }
-keep class com.demosten.srednabg.core.SpeedLimits { *; }
-keep class com.demosten.srednabg.app.data.remote.VersionResponse { *; }
-keep class com.demosten.srednabg.app.data.remote.ZonesResponse { *; }

# Keep Room entities
-keep class com.demosten.srednabg.app.data.local.ZoneEntity { *; }

# Gson TypeToken requires generic signatures
-keepattributes Signature
-keepattributes *Annotation*

# Android Auto CarAppService (keep entry point for manifest-reflected classes)
-keep class com.demosten.srednabg.app.auto.SrednaBGCarAppService { *; }
-keep class com.demosten.srednabg.app.auto.SrednaBGSession { *; }
-keep class com.demosten.srednabg.app.auto.NavigationScreen { *; }
-keep class com.demosten.srednabg.app.auto.AutoEntryPoint { *; }

# OkHttp
-dontwarn okhttp3.internal.platform.**
-dontwarn org.bouncycastle.**
-dontwarn org.conscrypt.**
-dontwarn org.openjsse.**
