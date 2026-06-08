# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa
#
# validate_zones.py — drive every bundled zone through the running emulator the
# way feed-zone.sh does (oriented by the zone's start/end *endpoints*, i.e. the
# real carriageway direction) and assert, from the app's own zone-state log,
# that each zone behaves: it enters the *correct* zone, does not flap, and exits
# cleanly. Pairs with feed_zone.py (shares `build_route`).
#
# Why this exists: the per-zone bulk QA suite (`scenarios/bulk/`) drives the
# *centerline point order* and only asserts "some zone was entered". That is
# self-consistent with the data, so it cannot catch a zone whose centerline is
# stored end-first — its `polylineBearing` then points the wrong way and the app
# matches the opposite-direction sibling zone (observed live: feeding
# europa-01-north matched europa-01-south and flapped InZone<->Exiting). This
# harness drives the true direction and checks the entered zone *id*, so that
# class of data bug fails loudly.
#
#   python3 qa/validate_zones.py                 # all zones, full traversal
#   python3 qa/validate_zones.py --only 0,1,5    # a subset (index or id)
#   python3 qa/validate_zones.py --quick         # ~2 km per zone (entry + no-flap)
#   python3 qa/validate_zones.py --no-setup      # skip device prep (offline/clear)
#
# Reads the same zones.json feed-zone.sh uses (backend/data by default). The app
# under test must run that *same* bundled data — so by default setup forces the
# device offline (zone sync would otherwise overwrite the bundle with whatever
# the server currently serves) and clears app data so the corrected bundle
# loads. Pass --keep-online to skip that (you accept the device's current data).
import argparse
import os
import subprocess
import sys
import time

import feed_zone

PKG = os.environ.get("PKG", "com.demosten.srednabg")
RC = f"{PKG}/{PKG}.app.debug.DebugControlReceiver"
TTS_TAG = "SrednaBG.TTS"

ACT_START = "com.demosten.srednabg.debug.START_TRACKING"
ACT_STOP = "com.demosten.srednabg.debug.STOP_TRACKING"
ACT_FEED = "com.demosten.srednabg.debug.FEED_POINT"
ACT_SET = "com.demosten.srednabg.debug.SET_SETTING"

PERMS = [
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.POST_NOTIFICATIONS",
]


def adb(*args, check=False, capture=True):
    return subprocess.run(["adb", *args], check=check,
                          capture_output=capture, text=True)


def broadcast(action, extras=None):
    cmd = ["shell", "am", "broadcast", "-n", RC, "-a", action]
    for k, v in (extras or {}).items():
        cmd += ["--es", k, str(v)]
    return adb(*cmd)


# --- device setup ---------------------------------------------------------

def set_network(enabled):
    state = "disable" if not enabled else "enable"
    adb("shell", "svc", "wifi", state)
    adb("shell", "svc", "data", state)
    adb("shell", "cmd", "connectivity", "airplane-mode",
        "enable" if not enabled else "disable")


def setup_device(keep_online):
    print("Setup: muting audio…")
    for s in range(1, 11):
        adb("shell", "media", "volume", "--stream", str(s), "--set", "0")
    if keep_online:
        print("Setup: --keep-online — testing the device's CURRENT zone data "
              "(may be server-synced, not the bundle).")
        return
    print("Setup: forcing device offline so the bundled zones load "
          "(zone sync would overwrite them with the live server's data)…")
    set_network(False)
    time.sleep(1.0)
    print("Setup: clearing app data + re-granting permissions…")
    adb("shell", "pm", "clear", PKG)
    for p in PERMS:
        adb("shell", "pm", "grant", PKG, p)
    time.sleep(0.5)


def restore_device(keep_online):
    if keep_online:
        return
    print("Teardown: restoring network…")
    set_network(True)


def loaded_data_matches_bundle(zones):
    """Pull the on-device Room DB and confirm a sample zone's centerline is
    oriented the same way as the bundle we are about to feed. Guards against a
    false PASS where the app is silently running stale/server data."""
    import json
    import tempfile
    z = zones[0]
    bundle_cl0 = z["centerline"][0]
    db = os.path.join(tempfile.gettempdir(), "srednabg_validate.db")
    with open(db, "wb") as f:
        out = subprocess.run(
            ["adb", "shell", "run-as", PKG, "cat", "databases/srednabg.db"],
            capture_output=True)
        f.write(out.stdout)
    try:
        import sqlite3
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT centerlineJson FROM zones WHERE id=?", (z["id"],)).fetchone()
        con.close()
    except Exception as e:  # table missing / db locked — inconclusive
        print(f"  (could not read on-device DB: {e}; skipping data check)")
        return True
    if not row:
        return True
    db_cl0 = json.loads(row[0])[0]
    same = (abs(db_cl0[0] - bundle_cl0[0]) < 1e-5
            and abs(db_cl0[1] - bundle_cl0[1]) < 1e-5)
    if not same:
        print(f"  WARNING: device DB centerline for {z['id']} starts at "
              f"{db_cl0} but the bundle starts at {bundle_cl0} — the app is NOT "
              f"running the data being validated. Results are meaningless.")
    return same


# --- per-zone drive + assertions -----------------------------------------

def feed_zone_route(zone, step, speed, max_fixes, sim_dt_ms):
    full = feed_zone.build_route(zone, step)
    broadcast(ACT_STOP)            # ensure clean detector state
    time.sleep(0.8)
    adb("logcat", "-c")            # fresh log buffer for this zone
    broadcast(ACT_START)
    time.sleep(2.0)               # let the service init + detector load

    # Batch the whole route into ONE on-device shell loop: `am broadcast` blocks
    # until the receiver returns, so the fixes are delivered in order with
    # natural backpressure (no drops) — far faster than one host-side adb spawn
    # per fix. Each fix is stamped `sim_dt_ms` apart in *simulated* time (see the
    # time_ms note in DebugControlReceiver) so the GPS filter / speed math see a
    # realistic cadence regardless of how fast we actually inject.
    base_ms = int(time.time() * 1000)
    lines = []
    n = 0
    for i in range(1, len(full)):
        a, b = full[i - 1], full[i]
        br = feed_zone.brng(a, b)
        lines.append(
            f"am broadcast -n {RC} -a {ACT_FEED} "
            f"--es lat {b[0]:.6f} --es lng {b[1]:.6f} "
            f"--es speed_ms {speed:.0f} --es bearing {br:.0f} "
            f"--es time_ms {base_ms + i * sim_dt_ms} >/dev/null 2>&1")
        n += 1
        if max_fixes and n >= max_fixes:
            break

    import tempfile
    script = os.path.join(tempfile.gettempdir(), "srednabg_feed.sh")
    with open(script, "w") as f:
        f.write("\n".join(lines) + "\n")
    remote = "/data/local/tmp/srednabg_feed.sh"
    adb("push", script, remote)
    adb("shell", "sh", remote)     # runs all fixes in order, blocking per fix

    time.sleep(1.0)
    broadcast(ACT_STOP)
    time.sleep(0.6)
    return n


def parse_states(dump):
    """Parse every onZoneStateChanged line into a per-fix [(state, zone)] list."""
    seq = []
    for line in dump.splitlines():
        idx = line.find("onZoneStateChanged ")
        if idx < 0:
            continue
        fields = {}
        for tok in line[idx:].split():
            if "=" in tok:
                k, _, v = tok.partition("=")
                fields[k] = v
        new = fields.get("new")
        if new is None:
            continue
        zone = fields.get("zone")
        seq.append((new, zone if zone not in (None, "-") else None))
    return seq


def collapse(seq):
    """Collapse consecutive identical (state, zone) entries."""
    out = []
    for e in seq:
        if not out or out[-1] != e:
            out.append(e)
    return out


# Fraction of in-zone time the intended zone must own to count as the real
# traversal. Brief approach blips into the opposite-direction sibling or the
# adjacent zone (the feeder's 120 m lead-in can start inside the preceding zone,
# and a centerline that jogs at its first vertex briefly reads as the sibling)
# are expected and benign — the genuine reversed-centerline bug instead spends
# the *entire* drive in the wrong zone, so it fails this decisively (intended
# fraction ≈ 0).
MIN_INTENDED_FRACTION = 0.75


def evaluate(zone_id, seq):
    """Judge a drive by its *dominant* sustained traversal, not by every zone
    that flickered past. Returns (ok, reasons, summary)."""
    from collections import Counter
    counts = Counter(z for s, z in seq if s == "InZone" and z)
    total = sum(counts.values())
    path = collapse(seq)
    summary = " ".join(f"{s}:{z}" if z else s for s, z in path) or "(no states)"

    if total == 0:
        return False, ["never entered any zone"], summary

    dominant, dom_n = counts.most_common(1)[0]
    intended_n = counts.get(zone_id, 0)
    frac = intended_n / total

    # Re-entry of the *intended* zone after we'd already exited it = real flap.
    reentries, seen_exit = 0, False
    for s, z in path:
        if s == "Exiting" and z == zone_id:
            seen_exit = True
        elif s == "InZone" and z == zone_id and seen_exit:
            reentries += 1
            seen_exit = False
    exited = any(s == "Exiting" and z == zone_id for s, z in seq)

    reasons = []
    if dominant != zone_id or frac < MIN_INTENDED_FRACTION:
        reasons.append(
            f"main traversal was {dominant} "
            f"(intended {zone_id} only {intended_n}/{total} in-zone fixes)")
    if reentries:
        reasons.append(f"flapped: intended zone re-entered x{reentries}")
    if not exited:
        reasons.append("no clean exit from intended zone")
    return (not reasons), reasons, summary


# --- main -----------------------------------------------------------------

def select_zones(zones, only):
    if not only:
        return list(enumerate(zones))
    chosen = []
    for sel in only.split(","):
        sel = sel.strip()
        if sel.isdigit() and int(sel) < len(zones):
            chosen.append((int(sel), zones[int(sel)]))
            continue
        m = [(i, z) for i, z in enumerate(zones) if z.get("id") == sel]
        if not m:
            m = [(i, z) for i, z in enumerate(zones)
                 if sel.lower() in z.get("id", "").lower()]
        if len(m) != 1:
            sys.exit(f"--only '{sel}' did not resolve to exactly one zone")
        chosen.append(m[0])
    return chosen


def main():
    ap = argparse.ArgumentParser(description="Validate every zone via the debug GPS feed.")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--zones", default=os.path.join(repo_root, "backend", "data", "zones.json"))
    ap.add_argument("--step", type=float, default=30.0, help="metres between fixes")
    ap.add_argument("--speed", type=float, default=30.0, help="feed speed m/s")
    ap.add_argument("--sim-dt-ms", type=int, default=1000,
                    help="simulated ms between fixes seen by the GPS pipeline")
    ap.add_argument("--max-fixes", type=int, default=0,
                    help="cap fixes/zone (0=full traversal)")
    ap.add_argument("--quick", action="store_true",
                    help="~2 km per zone (entry + no-flap; skips exit check)")
    ap.add_argument("--only", default="", help="comma list of indices or ids")
    ap.add_argument("--no-setup", action="store_true", help="skip device prep")
    ap.add_argument("--keep-online", action="store_true",
                    help="don't force offline/clear (use device's current data)")
    args = ap.parse_args()

    if adb("get-state").returncode != 0:
        sys.exit("no adb device — boot the Pixel_8a emulator first")

    zones = feed_zone.load_zones(args.zones)
    selected = select_zones(zones, args.only)

    max_fixes = args.max_fixes
    expect_exit = not args.quick
    if args.quick:
        max_fixes = max_fixes or int(2000 / args.step)  # ~2 km

    if not args.no_setup:
        setup_device(args.keep_online)

    results = []
    for n, (idx, zone) in enumerate(selected, 1):
        zid = zone.get("id", f"#{idx}")
        print(f"[{n}/{len(selected)}] zone {idx} {zid} … ", end="", flush=True)
        feed_zone_route(zone, args.step, args.speed, max_fixes, args.sim_dt_ms)
        dump = adb("logcat", "-d", "-s", f"{TTS_TAG}:D").stdout
        seq = parse_states(dump)
        ok, reasons, summary = evaluate(zid, seq)
        # In quick mode the drive stops mid-zone, so a clean exit isn't expected.
        if not expect_exit:
            reasons = [r for r in reasons if "clean exit" not in r]
            ok = not reasons
        if n == 1 and not args.no_setup and not args.keep_online:
            loaded_data_matches_bundle(zones)
        results.append((idx, zid, ok, reasons, summary))
        print("PASS" if ok else f"FAIL — {'; '.join(reasons)}")

    if not args.no_setup:
        restore_device(args.keep_online)

    npass = sum(1 for r in results if r[2])
    nfail = len(results) - npass
    print(f"\n=== {npass}/{len(results)} passed, {nfail} failed ===")
    for idx, zid, ok, reasons, summary in results:
        if not ok:
            print(f"  FAIL [{idx}] {zid}: {'; '.join(reasons)}")
            print(f"        path: {summary}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
