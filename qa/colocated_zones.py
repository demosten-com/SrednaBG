# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 SrednaBG Contributors
#
# SrednaBG — qa
#
# colocated_zones.py — drive a continuous route through a *co-located* zone pair
# (one camera ends zone A and begins zone B, so the engine steps
# InZone(A) -> Exiting(A) -> InZone(B) on consecutive fixes) and assert, from the
# app's own TTS log, that ENTERING the second zone is announced.
#
# Why this exists: the back-to-back camera case has no `Outside` between the two
# zones, so the entry into B is the `Exiting -> InZone` transition. The TTS layer
# originally handled only Outside->InZone / InZone->InZone / InZone->Exiting, so
# at the 24 co-located pairs in the data (mostly Trakiya) the driver got NO
# "entering / new limit" cue for the next zone — the announcement was silently
# dropped. validate_zones.py drives one zone at a time (STOP between zones), so it
# structurally cannot see this; this harness keeps tracking running across the
# boundary. Regression for the AudioAlertManager `Exiting->InZone` fix.
#
#   python3 qa/colocated_zones.py                  # first detected pair
#   python3 qa/colocated_zones.py --pair trakiya-02-east,trakiya-03-east
#   python3 qa/colocated_zones.py --all            # every co-located pair
#   python3 qa/colocated_zones.py --keep-online    # use device's current data
#
# Requires the DEBUG build installed + the Pixel_8a emulator running.
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

# Allow `python3 qa/colocated_zones.py …` (run from colocated-zones.sh) to
# import the qa package, matching srednabg_qa.py's bootstrap.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from qa import adb, feed_zone, parsers  # noqa: E402
from qa.events import TtsSpeak, ZoneStateChange  # noqa: E402

PKG = adb.PACKAGE
RC = adb.DEBUG_CONTROL_RECEIVER
TTS_TAG = "SrednaBG.TTS"

ACT_START = "com.demosten.srednabg.debug.START_TRACKING"
ACT_STOP = "com.demosten.srednabg.debug.STOP_TRACKING"
ACT_FEED = "com.demosten.srednabg.debug.FEED_POINT"

# Two zones are co-located when zone A's end camera is also zone B's start camera
# on the same road + carriageway direction (gap ~0 m in the data).
COLOCATION_GAP_M = 80.0

# English entry/exit message fragments (we force app_language=en for a
# deterministic match). BG fragments kept too in case the device ignores the set.
ENTRY_FRAGMENTS = ("Entering average speed zone", "Влизате в зона")
EXIT_FRAGMENTS = ("Leaving zone", "Излизате от зоната")


def launch_app():
    """Bring the app to the foreground so START_TRACKING's foreground-service
    start is permitted. Android 12+ denies an FGS start from a background
    broadcast receiver (uidState RCVR → code:DENIED), so without a visible
    activity the service never runs and no announcements fire. Poll until the
    activity is resumed so a launch failure surfaces instead of a silent pass."""
    adb.shell("am start -W -a android.intent.action.MAIN "
              f"-c android.intent.category.LAUNCHER -n {adb.MAIN_ACTIVITY}")
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        out = adb.shell("dumpsys activity activities")
        for line in out.splitlines():
            if "ResumedActivity" in line and PKG in line:
                return True
        time.sleep(0.5)
    print(f"  WARNING: {PKG} did not reach the foreground within 10s; "
          f"START_TRACKING will likely be denied (background FGS start).")
    return False


def set_setting(key, value):
    adb.broadcast(adb.ACTION_SET_SETTING, RC, {"key": key, "value": value})


# --- pair detection -------------------------------------------------------

def find_pairs(zones):
    """All ordered (A, B) where A.end ~= B.start on the same road+direction."""
    pairs = []
    for a in zones:
        ae = (a["end"]["lat"], a["end"]["lng"])
        for b in zones:
            if a is b or a.get("direction") != b.get("direction"):
                continue
            if a.get("road") != b.get("road"):
                continue
            bs = (b["start"]["lat"], b["start"]["lng"])
            if feed_zone.hav(ae, bs) <= COLOCATION_GAP_M:
                pairs.append((a, b))
    return pairs


def resolve_pair(zones, spec):
    """spec is 'idA,idB' (exact ids) — must be co-located."""
    ida, _, idb = spec.partition(",")
    ida, idb = ida.strip(), idb.strip()
    a = next((z for z in zones if z.get("id") == ida), None)
    b = next((z for z in zones if z.get("id") == idb), None)
    if not a or not b:
        sys.exit(f"--pair: zone not found ({ida!r} / {idb!r})")
    gap = feed_zone.hav((a["end"]["lat"], a["end"]["lng"]),
                        (b["start"]["lat"], b["start"]["lng"]))
    if gap > COLOCATION_GAP_M:
        print(f"  WARNING: {ida} -> {idb} are {gap:.0f} m apart "
              f"(> {COLOCATION_GAP_M:.0f} m) — not really co-located.")
    return a, b


# --- device setup ---------------------------------------------------------

def set_network(enabled):
    adb.set_wifi_enabled(enabled)
    adb.set_data_enabled(enabled)
    adb.shell(f"cmd connectivity airplane-mode {'disable' if enabled else 'enable'}")


def setup_device(keep_online):
    print("Setup: muting audio…")
    adb.mute_audio()
    if not keep_online:
        print("Setup: forcing device offline + clearing app data so the bundle "
              "loads…")
        set_network(False)
        time.sleep(1.0)
        adb.shell(f"pm clear {PKG}")
        adb.grant_runtime_permissions()
        time.sleep(0.5)
    # Foreground the app (after any pm clear) so the FGS start is permitted.
    print("Setup: foregrounding the app (required for the FGS start)…")
    launch_app()
    # Deterministic announcement state: English voice on, no periodic chatter.
    set_setting("app_language", "en")
    set_setting("voice_enabled", "true")
    set_setting("periodic_voice_updates", "false")
    time.sleep(0.4)


def restore_device(keep_online):
    # setup_device always mutes, so always unmute on teardown.
    print("Teardown: restoring audio…")
    adb.unmute_audio()
    if not keep_online:
        print("Teardown: restoring network…")
        set_network(True)
        print("Note: app data was cleared (pm clear) for offline bundle testing; "
              "the app starts fresh on the next manual use.")


# --- continuous drive across the pair ------------------------------------

def build_pair_route(a, b, step):
    """A's full route (approach + A start->end) then B's centerline start->end
    with NO fresh approach — we are already on the road, driving straight through
    the shared camera into B.

    Dedupe near-coincident points at the seam: A ends at A.end and B begins at
    B.start, which for a co-located pair are ~0 m apart. Two coincident fixes
    yield a meaningless junction bearing, and a single wrong-bearing fix at the
    shared camera spuriously matches the *opposite-carriageway sibling* zone for a
    fix or two. A real drive moves continuously through the camera with a
    consistent heading, so dropping the duplicate restores that — leaving the
    clean InZone(A) -> Exiting(A) -> InZone(B) transition we want to assert on."""
    route_a = feed_zone.build_route(a, step)   # 4 approach pts + A
    route_b = feed_zone.build_route(b, step)[4:]  # drop B's approach pts
    merged = []
    for p in route_a + route_b:
        if merged and feed_zone.hav(merged[-1], p) < 1.0:
            continue  # skip a duplicate seam point (garbage bearing otherwise)
        merged.append(p)
    return merged


def feed_route(full, step, speed, sim_dt_ms):
    adb.broadcast(ACT_STOP, RC)
    time.sleep(0.8)
    adb.clear_logcat()
    adb.broadcast(ACT_START, RC)
    time.sleep(2.0)

    base_ms = int(time.time() * 1000)   # epoch fix stamp — time.time() is correct here
    lines = []
    for i in range(1, len(full)):
        a, b = full[i - 1], full[i]
        br = feed_zone.brng(a, b)
        lines.append(
            f"am broadcast -n {RC} -a {ACT_FEED} "
            f"--es lat {b[0]:.6f} --es lng {b[1]:.6f} "
            f"--es speed_ms {speed:.0f} --es bearing {br:.0f} "
            f"--es time_ms {base_ms + i * sim_dt_ms} >/dev/null 2>&1")

    # PID-stamped temp name so concurrent runs don't clobber each other; removed
    # from the device after the batch.
    name = f"srednabg_pair_feed_{os.getpid()}.sh"
    script = os.path.join(tempfile.gettempdir(), name)
    with open(script, "w") as f:
        f.write("\n".join(lines) + "\n")
    remote = f"/data/local/tmp/{name}"
    adb.push(script, remote)
    adb.shell(f"sh {remote}", timeout=max(180.0, len(full) * 0.5))
    adb.shell(f"rm -f {remote}")
    os.remove(script)

    time.sleep(1.0)
    adb.broadcast(ACT_STOP, RC)
    time.sleep(0.6)


# --- log parsing + assertions --------------------------------------------

def parse_events(dump):
    """Return the TTS log as an ordered list of events:
       ("state", prev, new, zone) | ("entry", text) | ("exit", text).

    Uses the shared `qa.parsers` regex set (STATE_RE / SPEAK_RE) instead of
    hand-rolled string slicing, so a log-format change is fixed in one place."""
    events = []
    for line in dump.splitlines():
        ev = parsers.parse_threadtime_line(line)
        if isinstance(ev, ZoneStateChange):
            zone = ev.zone if ev.zone != "-" else None
            events.append(("state", ev.prev, ev.new, zone))
        elif isinstance(ev, TtsSpeak):
            text = ev.text
            if any(fr in text for fr in ENTRY_FRAGMENTS):
                events.append(("entry", text))
            elif any(fr in text for fr in EXIT_FRAGMENTS):
                events.append(("exit", text))
    return events


def evaluate(a_id, b_id, events):
    """Correct behaviour: after driving through A, ENTERING the co-located zone B
    is announced. We correlate by order — the first `new=InZone zone=B` state line
    must be followed by an `entry` speak before the next state line.

    Keying on zone == B (not "any entry after the boundary") matters two ways:
      * it ignores the benign sibling-jog blip (B's centerline often starts with a
        backwards first segment that matches the opposite-carriageway sibling for
        one fix, firing a spurious entry for the *sibling* — a different zone id);
      * it works whether B is entered as the direct `Exiting->InZone(B)` (the
        case the fix targets — no Outside between cameras) or as
        `Exiting->Outside->InZone(B)` (a one-fix gap, which the pre-existing
        Outside->InZone handler already announces — not a bug). The direct-path
        pairs (e.g. trakiya) are the ones that exercise the fix: verified to fail
        there without it."""
    reasons = []

    saw_in_a = any(e[0] == "state" and e[2] == "InZone" and e[3] == a_id
                   for e in events)
    if not saw_in_a:
        reasons.append(f"never entered A ({a_id})")

    enter_b_idx = next(
        (i for i, e in enumerate(events)
         if e[0] == "state" and e[2] == "InZone" and e[3] == b_id),
        None)
    if enter_b_idx is None:
        reasons.append(f"never entered B ({b_id}) — pair never traversed")
    else:
        prev_state = events[enter_b_idx][1]  # "Exiting" (direct) or "Outside"
        announced = False
        for e in events[enter_b_idx + 1:]:
            if e[0] == "state":
                break
            if e[0] == "entry":
                announced = True
                break
        if not announced:
            reasons.append(
                f"ENTERING {b_id} was NOT announced (prev={prev_state}; entry "
                "into B fired no entry speak) — the co-located entry "
                "announcement was dropped")

    ok = not reasons
    return ok, reasons


def summarize(events):
    out = []
    for e in events:
        if e[0] == "state":
            out.append(f"{e[2]}:{e[3]}" if e[3] else e[2])
        else:
            out.append(f"<{e[0]}>")
    # collapse consecutive identical tokens
    collapsed = []
    for t in out:
        if not collapsed or collapsed[-1] != t:
            collapsed.append(t)
    return " ".join(collapsed) or "(no events)"


# --- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Assert the co-located zone-pair entry announcement.")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--zones",
                    default=os.path.join(repo_root, "backend", "data", "zones.json"))
    ap.add_argument("--pair", default="",
                    help="'idA,idB' (exact, co-located). Default: first detected.")
    ap.add_argument("--all", action="store_true",
                    help="drive every detected co-located pair")
    ap.add_argument("--step", type=float, default=30.0)
    ap.add_argument("--speed", type=float, default=30.0)
    ap.add_argument("--sim-dt-ms", type=int, default=1000)
    ap.add_argument("--no-setup", action="store_true")
    ap.add_argument("--keep-online", action="store_true")
    args = ap.parse_args()

    if adb.get_state() is None:
        sys.exit("no adb device — boot the Pixel_8a emulator first")

    zones = feed_zone.load_zones(args.zones)

    if args.all:
        pairs = find_pairs(zones)
    elif args.pair:
        pairs = [resolve_pair(zones, args.pair)]
    else:
        detected = find_pairs(zones)
        if not detected:
            sys.exit("no co-located pairs found in the data")
        pairs = [detected[0]]

    if not pairs:
        sys.exit("no co-located pairs to drive")

    if not args.no_setup:
        setup_device(args.keep_online)

    results = []
    for n, (a, b) in enumerate(pairs, 1):
        a_id, b_id = a["id"], b["id"]
        print(f"[{n}/{len(pairs)}] {a_id} -> {b_id} … ", end="", flush=True)
        full = build_pair_route(a, b, args.step)
        feed_route(full, args.step, args.speed, args.sim_dt_ms)
        dump = adb.logcat_dump("-s", f"{TTS_TAG}:D")
        events = parse_events(dump)
        ok, reasons = evaluate(a_id, b_id, events)
        results.append((a_id, b_id, ok, reasons, summarize(events)))
        print("PASS" if ok else f"FAIL — {'; '.join(reasons)}")

    if not args.no_setup:
        restore_device(args.keep_online)

    npass = sum(1 for r in results if r[2])
    nfail = len(results) - npass
    print(f"\n=== {npass}/{len(results)} passed, {nfail} failed ===")
    for a_id, b_id, ok, reasons, summary in results:
        if not ok:
            print(f"  FAIL {a_id} -> {b_id}: {'; '.join(reasons)}")
            print(f"        events: {summary}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
