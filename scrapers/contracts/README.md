# Client wire contracts

What `/api/zones` must look like for the SrednaBG apps **already installed on
people's phones**. Enforced at publish time by `src/client_contract.py`, which
`output.publish_guard_errors` calls before anything is written.

## Why this exists rather than a few `if`s in the scraper

A client-side fix reaches only future installs. The apps in the stores can never
be repaired retroactively, so the wire format is the *only* thing protecting the
existing fleet — and the rules that protect it are a transcription of somebody
else's parser (released Kotlin and Swift models). A transcription nothing checks
is a guess.

In 2026-08 a single zone missing its `truck` key failed the **entire**
`/api/zones` decode on iOS 1.x — every published install lost zone sync for five
days — while a sibling zone with an empty centerline made MapLibre reject the
whole zone layer on Android, blanking the map. Both shipped through a guard that
"looked right".

## Feeds

A **feed** is a served payload variant, named by a positive integer. Feed 1 is
`/api/zones` + `/api/version`; feed N>1 is `/api/zones.N` + `/api/version.N`.
Clients pick their feed at compile time (`BuildConfig.ZONE_FEED_VERSION` /
`BackendURLs.feedVersion`) and never negotiate, so a feed is only ever fetched
by builds made for it.

That is the escape hatch from the constraint this whole directory describes. The
rules below pin the wire to what the 1.x installs can parse, and they must keep
pinning it for as long as those installs exist — which is indefinitely. A new
**contract** describes a shape; only a new **feed** lets you *serve* one the
older clients could not consume, because they will never ask for it. Adding
`wire-v2.json` and pointing feed 1 at it would break exactly the fleet the
contract exists to protect.

`manifest.json` declares the feeds and gives each client entry a `feed`.
`contract_violations(payload, feed=N)` enforces only the clients on feed N, so a
feed with no clients is deliberately unconstrained — that is what a
not-yet-shipped feed is. Feed `status` is `active` (served, maintained),
`unsupported` (still served, and its `version*.json` carries `"unsupported": 1`
so clients can tell the user to update), or `retired` (no longer written).

The projection that produces each feed's payload lives in `src/feeds.py`; feed
1's is the identity, and a test pins its bytes and its hash against the
committed `zones.json` — feed 1 must not move because feeds now exist.

## Layout

| File | What |
|---|---|
| `manifest.json` | Which client versions are in the field, their status, and their feed; which feeds are served |
| `wire-v1.json` | The contract itself — required keys, types, constraints |
| `fixtures/*.json` | One payload per rule, violating exactly that rule |
| `fixtures/expectations.json` | What each fixture does on a *released* client |
| `verify_against_clients.sh` | Decodes every fixture with the models as shipped |

## The rule that keeps this honest

**Every constraint has a fixture, and every fixture has a pinned expectation.**
`tests/test_client_contract.py` fails if a rule is added without a fixture, and
`verify_against_clients.sh` fails if a fixture behaves differently on a released
client than `expectations.json` claims.

That last check is the point of the whole directory. It checks each published
tag out into a git worktree, compiles a decoder from *that tag's*
`Models.swift` + `ApiTypes.swift`, and runs every fixture through it:

```bash
bash scrapers/contracts/verify_against_clients.sh          # all published versions
bash scrapers/contracts/verify_against_clients.sh v1.1.0   # just one
```

Needs macOS with a Swift toolchain, so it runs locally or on the Mac mini
runner — never on the Namecheap host, which has Python only. That split is
deliberate: the *gate* must run where publishing happens, the *proof* must run
where the real compilers are.

Note `swift_decode: "tolerated"` is a legitimate, pinned outcome, not a defect.
An empty centerline decodes perfectly well on iOS — it is the Android map it
destroys. Rules exist for reasons the Swift decoder cannot see, and pinning the
tolerance stops someone "fixing" the check to expect a failure that will never
come.

## Adding a version

Only versions **actually published to a store** belong in `manifest.json`.
v1.0.1–v1.0.3 are tags nobody ever received; listing them would block publishes
to protect no one.

When you ship a release:

1. Add it to `manifest.json` with `status: "live"` and its `feed`, demote the
   previous entry to `"published"`, and add the matching **Feed** cell to the
   `VERSIONS.md` row — `test_client_contract.py` compares the two.
2. If its decode surface changed, add a new `wire-vN.json` and point the new
   version at it. If not, reuse the existing contract — 1.0.4 and 1.1.0 share
   `wire-v1.json` because their decode surface is byte-identical.
3. Run `verify_against_clients.sh` and commit the result.

Every published client is enforced at **ERROR**. A version may be retired to
WARN by adding an explicit `severity` to its manifest entry — deliberately,
never as a side effect of shipping something newer. On the day 2.0.0 goes live,
1.1.0 is still the entire installed base.
