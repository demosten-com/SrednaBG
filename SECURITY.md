# Security Policy

SrednaBG is a small, free, open-source project. Security reports are taken
seriously and handled on a best-effort basis by the maintainers.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security problems.**

The preferred way to report is GitHub's **private vulnerability reporting**:
go to the repository's [**Security** tab → **Report a vulnerability**](https://github.com/demosten-com/SrednaBG/security/advisories/new),
or use the button at <https://github.com/demosten-com/SrednaBG/security/advisories>.
This keeps the report private to the maintainers and lets us coordinate a fix
and advisory in one place.

If you'd rather use email, that works too: write to **demosten@gmail.com** with
`SrednaBG security` in the subject line. If you'd like to encrypt or verify
before sending sensitive details, say so in a first short email and we'll
arrange a channel.

Please include, where you can:

- A description of the issue and why you believe it's a security problem.
- Steps to reproduce, or a proof of concept.
- The affected area — Android phone app, iOS phone app, the backend tile/API
  server, the scraper pipeline, or the zone data — and the app version
  (Settings → About) or commit SHA.
- The impact you think it has.

You can expect an acknowledgement within about a week. Because this is a
volunteer project, please allow reasonable time for a fix before any public
disclosure — we'll keep you updated and credit you (if you want) once a fix
ships.

## Supported versions

Only the latest released version receives security fixes. Fixes ship in the
next release on [GitHub Releases](https://github.com/demosten-com/SrednaBG/releases)
and F-Droid; there are no backports to older versions.

| Version        | Supported |
| -------------- | --------- |
| Latest release | ✅        |
| Older releases | ❌        |

## Scope

In scope:

- The Android and iOS phone apps in this repository.
- The backend stack (`backend/` — tileserver-gl + nginx) and the scraper
  pipeline (`scrapers/`) as published here.
- Integrity of the zone data (`zones.json`) and the offline map bundle as
  shipped in releases.

Out of scope / report upstream instead:

- Vulnerabilities in third-party dependencies (MapLibre, tileserver-gl, Gradle
  plugins, Python/Swift packages) — please report those to the respective
  upstream projects. We'll still want to know so we can bump the dependency.
- The author's self-hosted infrastructure (the Mac Mini host, `srednabg.com`
  hosting) beyond what this repository's code and configuration control.
- The Android Auto and CarPlay surfaces, which are work-in-progress and **not**
  part of any shipped release. Reports are welcome but lower priority.

## A note on the app's data handling

SrednaBG is offline-first by design. Location data is processed **on-device
only and is never transmitted** off the device (see
[PRIVACY_POLICY.md](PRIVACY_POLICY.md)). Network use is limited to optional,
read-only fetches of updated zone data and map tiles. Reports that increase the
amount of personal data leaving the device, or that undermine the on-device-only
guarantee, are especially valued.

## Good-faith research

We will not pursue or support legal action against researchers who:

- act in good faith and avoid privacy violations, data destruction, and service
  disruption, and
- give us reasonable time to address an issue before public disclosure.

Thank you for helping keep SrednaBG and its users safe.
