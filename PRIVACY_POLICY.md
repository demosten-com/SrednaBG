# Privacy Policy — SrednaBG (Средна БГ)

**Effective date:** May 1, 2026

SrednaBG is a free, open-source mobile application for Android and iOS that calculates running average speed within Bulgaria's section control (секционен контрол) camera zones. This policy explains what data the app accesses and how it is handled.

## Data collected

### Location data
- The app uses GPS (fine location) to determine your position, speed, and heading while tracking is active.
- Location data is processed **on-device only** to calculate your average speed within section control zones.
- Location data is **never transmitted** to any server, third party, or analytics service.
- No location history is stored after a tracking session ends.

### Background location
- The app may continue to access location while it is in the background — for example, when your screen is off, or when another navigation app (e.g., Waze, Google Maps, Apple Maps) is in the foreground — so it can keep tracking your position within a section-control zone.
- Background location data is processed identically to foreground data — on-device only, never transmitted.

### Zone data
- The app periodically downloads section control zone definitions (road names, GPS coordinates of zone boundaries, speed limits) and offline map tiles from a self-hosted server operated by the developer.
- Network requests necessarily expose your device's IP address to the server, but **the server does not log or store these requests**, and no personally identifiable information is sent.

### Local storage
- Zone data is cached in a local database on your device for offline use.
- User preferences (alert threshold, voice language, vehicle type) are stored in the platform's local key-value preferences (Android DataStore / iOS UserDefaults).
- No personal information is stored.

## Data NOT collected
- No personal information (name, email, phone number)
- No device identifiers or advertising IDs
- No analytics, crash reports, or telemetry
- No location data is transmitted off-device
- No data is shared with third parties

## Third-party services
- **Android — Google Play Services (Fused Location Provider)** — used to obtain GPS location. Subject to [Google's Privacy Policy](https://policies.google.com/privacy).
- **iOS — Apple Core Location** — used to obtain GPS location. Subject to [Apple's Privacy Policy](https://www.apple.com/legal/privacy/).
- **MapLibre Native** (Android and iOS) — used for map rendering. Map tiles are bundled with the app for offline use and otherwise served from the developer's self-hosted server; no data is sent to MapLibre or any third-party tile provider.

## Open source
SrednaBG is open source. You can review the complete source code to verify these claims at the project's repository.

## Children's privacy
This app is not directed at children under 13 and does not knowingly collect data from children.

## Changes to this policy
Updates to this policy will be reflected in the app's repository and the effective date above will be updated accordingly.

## Contact
For questions about this privacy policy, please open an issue in the project's GitHub repository.
