// swift-tools-version: 6.0
import PackageDescription

// SrednaBG iOS — Phase 8 monorepo of SwiftPM packages.
//
// Layered modules, lowest-dependency-first:
//   SrednaBGCore       pure-Swift port of the Kotlin android/core/ algorithms
//   SrednaBGData       sync, persistence, settings  (depends on Core)
//   SrednaBGTracking   CoreLocation + AVSpeechSynthesizer + ActivityKit (depends on Core, Data)
//   SrednaBGMapCore    UIKit+MapLibre plumbing shared by SrednaBGUI and SrednaBGCarPlay
//   SrednaBGUI         SwiftUI screens (depends on Tracking, Data, Core, MapCore)
//   SrednaBGCarPlay    CPTemplateApplicationSceneDelegate + CarPlay map/overlay (depends on MapCore, Tracking, Data, Core)
//
// Targets are added alongside their first source files so `swift build` stays
// green at every commit.

let package = Package(
    name: "SrednaBG",
    defaultLocalization: "bg",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "SrednaBGCore", targets: ["SrednaBGCore"]),
        .library(name: "SrednaBGData", targets: ["SrednaBGData"]),
        .library(name: "SrednaBGTracking", targets: ["SrednaBGTracking"]),
        .library(name: "SrednaBGMapCore", targets: ["SrednaBGMapCore"]),
        .library(name: "SrednaBGTheme", targets: ["SrednaBGTheme"]),
        .library(name: "SrednaBGUI", targets: ["SrednaBGUI"]),
        .library(name: "SrednaBGCarPlay", targets: ["SrednaBGCarPlay"]),
    ],
    dependencies: [
        // Standard zip library — Apple's Compression/AppleArchive don't read .zip,
        // and the offline map bundle ships as map-bundle.zip from the backend.
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", from: "0.9.19"),
        // MapLibre Native iOS — xcframework distribution, iOS-only slice.
        // Gated to iOS on the SrednaBGUI target so macOS `swift test` still links.
        .package(url: "https://github.com/maplibre/maplibre-gl-native-distribution", from: "6.9.0"),
    ],
    targets: [
        .target(
            name: "SrednaBGCore",
            path: "Packages/SrednaBGCore/Sources/SrednaBGCore",
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGCoreTests",
            dependencies: ["SrednaBGCore"],
            path: "Packages/SrednaBGCore/Tests/SrednaBGCoreTests",
            resources: [.copy("Resources")],
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGData",
            dependencies: [
                "SrednaBGCore",
                .product(name: "ZIPFoundation", package: "ZIPFoundation"),
            ],
            path: "Packages/SrednaBGData/Sources/SrednaBGData",
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGDataTests",
            dependencies: ["SrednaBGData", "SrednaBGCore"],
            path: "Packages/SrednaBGData/Tests/SrednaBGDataTests",
            resources: [.copy("Resources")],
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGTracking",
            dependencies: ["SrednaBGCore", "SrednaBGData"],
            path: "Packages/SrednaBGTracking/Sources/SrednaBGTracking",
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGTrackingTests",
            dependencies: ["SrednaBGTracking", "SrednaBGCore", "SrednaBGData"],
            path: "Packages/SrednaBGTracking/Tests/SrednaBGTrackingTests",
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGMapCore",
            dependencies: [
                "SrednaBGCore",
                .product(
                    name: "MapLibre",
                    package: "maplibre-gl-native-distribution",
                    condition: .when(platforms: [.iOS])
                ),
            ],
            path: "Packages/SrednaBGMapCore/Sources/SrednaBGMapCore",
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGMapCoreTests",
            dependencies: ["SrednaBGMapCore", "SrednaBGCore"],
            path: "Packages/SrednaBGMapCore/Tests/SrednaBGMapCoreTests",
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGTheme",
            dependencies: ["SrednaBGCore"],
            path: "Packages/SrednaBGTheme/Sources/SrednaBGTheme",
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGUI",
            dependencies: [
                "SrednaBGCore",
                "SrednaBGData",
                "SrednaBGTracking",
                "SrednaBGMapCore",
                "SrednaBGTheme",
            ],
            path: "Packages/SrednaBGUI/Sources/SrednaBGUI",
            resources: [.process("Resources")],
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGUITests",
            dependencies: ["SrednaBGUI", "SrednaBGCore", "SrednaBGData"],
            path: "Packages/SrednaBGUI/Tests/SrednaBGUITests",
            swiftSettings: strictConcurrencySettings
        ),
        .target(
            name: "SrednaBGCarPlay",
            dependencies: [
                "SrednaBGCore",
                "SrednaBGData",
                "SrednaBGTracking",
                "SrednaBGMapCore",
            ],
            path: "Packages/SrednaBGCarPlay/Sources/SrednaBGCarPlay",
            swiftSettings: strictConcurrencySettings
        ),
        .testTarget(
            name: "SrednaBGCarPlayTests",
            dependencies: ["SrednaBGCarPlay", "SrednaBGCore", "SrednaBGTracking", "SrednaBGData"],
            path: "Packages/SrednaBGCarPlay/Tests/SrednaBGCarPlayTests",
            swiftSettings: strictConcurrencySettings
        ),
    ]
)

var strictConcurrencySettings: [SwiftSetting] {
    [
        .swiftLanguageMode(.v6),
    ]
}
