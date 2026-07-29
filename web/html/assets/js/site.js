/* SrednaBG site.js — no cookies, no storage, vanilla. */

(function () {
  "use strict";

  /* ------------------------------------------------------ i18n (inlined) */
  const I18N = { bg: null, en: null };
  function loadLang(code) {
    if (I18N[code]) return Promise.resolve(I18N[code]);
    const tag = document.getElementById("i18n-" + code);
    if (tag) { try { I18N[code] = JSON.parse(tag.textContent); return Promise.resolve(I18N[code]); } catch (_) {} }
    // Fallback to fetch for dev servers that serve the raw JSON files
    return fetch("assets/i18n/" + code + ".json", { cache: "no-store" })
      .then((r) => r.json()).then((j) => (I18N[code] = j));
  }
  function apply(dict) {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const v = dict[el.getAttribute("data-i18n")];
      if (v != null) el.textContent = v;
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
      const v = dict[el.getAttribute("data-i18n-alt")];
      if (v != null) el.setAttribute("alt", v);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      const v = dict[el.getAttribute("data-i18n-aria-label")];
      if (v != null) el.setAttribute("aria-label", v);
    });
    const meta = document.querySelector('meta[name="description"]');
    if (meta && dict["meta.description"]) meta.setAttribute("content", dict["meta.description"]);
    if (dict["meta.title"]) document.title = dict["meta.title"];
  }
  /* ------- carry the active language across internal links (no storage) */
  function propagateLang(code) {
    document.querySelectorAll("a[href]").forEach((a) => {
      const raw = a.getAttribute("href");
      if (!raw || raw[0] === "#") return;            // in-page anchor: lang already active
      let u;
      try { u = new URL(raw, location.href); } catch (_) { return; }
      if (u.origin !== location.origin) return;      // external link
      if (/\.(png|jpe?g|svg|webp|gif|ico|apk|zip|json|txt|pdf|xml)$/i.test(u.pathname)) return; // asset
      u.searchParams.set("lang", code);
      a.setAttribute("href", u.pathname + u.search + u.hash);
    });
  }

  function pickLang() {
    const url = new URL(location.href);
    const q = url.searchParams.get("lang");
    if (q === "bg" || q === "en") return q;
    const list = (navigator.languages || [navigator.language || "bg"]);
    for (const t of list) { const p = (t || "").toLowerCase().split("-")[0]; if (p === "bg") return "bg"; if (p === "en") return "en"; }
    return "bg";
  }
  async function setLang(code, pushHistory) {
    const dict = await loadLang(code);
    document.documentElement.lang = code;
    apply(dict);
    applyMediaSources(code);
    propagateLang(code);
    document.querySelectorAll(".lang-pill button").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.lang === code));
    });
    document.body.classList.remove("i18n-swap"); void document.body.offsetWidth; document.body.classList.add("i18n-swap");
    if (pushHistory) {
      const u = new URL(location.href); u.searchParams.set("lang", code);
      history.pushState({}, "", u);
    }
  }

  /* ------------------------- per-visitor platform screenshots (no storage) */
  function detectPlatformBucket() {
    const ua = navigator.userAgent || "";
    const uad = navigator.userAgentData;
    const uadPlat = (uad && uad.platform ? uad.platform : "").toLowerCase();
    const navPlat = (navigator.platform || "").toLowerCase();
    const isIPad = navPlat === "macintel" && (navigator.maxTouchPoints || 0) > 1;
    const isIOS = /iPhone|iPad|iPod/.test(ua) || isIPad || uadPlat === "ios";
    const isMac = !isIOS && (/Macintosh|Mac OS X/.test(ua) || uadPlat === "macos");
    const isAndroid = /Android/.test(ua) || uadPlat === "android";
    const isCrOS = /CrOS/.test(ua) || uadPlat === "chrome os" || uadPlat === "chromeos";
    if (isIOS || isMac) return "ios";
    if (isAndroid || isCrOS) return "android";
    return "random";
  }
  function applyMediaSources(lang) {
    const bucket = detectPlatformBucket();
    const imgs = document.querySelectorAll(".step-shot img, .screen-card img");
    imgs.forEach((img) => {
      const src = img.getAttribute("src") || "";
      const m = src.match(/screenshots\/(?:(?:android|ios)\/)?(?:(?:bg|en)\/)?([^\/]+\.png)$/i);
      if (!m) return;
      const filename = m[1];
      let plat = img.dataset.platform;
      if (!plat) {
        plat = bucket === "random" ? (Math.random() < 0.5 ? "ios" : "android") : bucket;
        img.dataset.platform = plat;
      }
      img.setAttribute("src", "screenshots/" + plat + "/" + lang + "/" + filename);
    });
  }

  /* ------------------------------- screenshot onerror -> dark fallback tile */
  window.__ssFallback = function (img) {
    const label = img.getAttribute("data-fallback-label") || "Screen";
    const box = document.createElement("div");
    box.className = "ss-fallback";
    box.innerHTML =
      '<svg viewBox="0 0 48 48" fill="none" aria-hidden="true">' +
      '<circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="2.5"/>' +
      '<path d="M24 24 L34 15" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>' +
      '<circle cx="24" cy="24" r="2.5" fill="currentColor"/>' +
      "</svg>" +
      '<div class="ss-label">SrednaBG</div>' +
      '<div class="ss-label ss-fallback-label" style="color:var(--text-mid)"></div>';
    box.querySelector(".ss-fallback-label").textContent = label;
    img.replaceWith(box);
  };

  /* --------------------------- animated zone-status demo (hero AA slot) */
  /* One simulated drive through a real zone. The running average and the max
     speed still sustainable for the remainder are *derived* from that drive
     rather than hardcoded, so the three numbers on screen are always mutually
     consistent — in particular "max" can only fall below the limit once the
     average is already over it. Zone constants: europa-01-east in
     backend/data/zones.json (АМ Европа, 10.26 km, 120 km/h for a car). */
  const ZDEMO = {
    lengthKm: 10.26,
    limitKmh: 120,
    loopMs: 15600, // wall-clock time for one full traversal
    holdMs: 1200,  // rest on the final frame before looping
    tickMs: 250,   // 4 Hz; faster reads as flicker, not instrumentation
    maxRemainderKmh: 250, // MAX_REMAINDER_SPEED_KMH in android/core
  };

  /* Instantaneous speed (km/h) at a fraction p of the zone: cruise under the
     limit, accelerate, then sit above it long enough to spend the budget. */
  function zdemoSpeedAt(p) {
    if (p < 0.34) return 112;
    if (p < 0.62) return 112 + ((p - 0.34) / 0.28) * 20;
    return 132;
  }

  function zdemoBuildFrames() {
    const L = ZDEMO.lengthKm;
    const limit = ZDEMO.limitKmh;
    const allowedH = L / limit; // time budget to finish exactly at the limit
    const dtH = 1 / 3600;       // integrate in 1-second simulated steps
    const frames = [];
    let d = 0;
    let t = 0;
    while (d < L && frames.length < 3600) {
      const now = zdemoSpeedAt(d / L);
      d = Math.min(L, d + now * dtH);
      t += dtH;
      const avg = d / t;
      const remH = allowedH - t;
      const remKm = L - d;
      // Mirrors AverageSpeedCalc.calculate() in android/core: 0 once the zone
      // is behind you, otherwise the quotient capped at MAX_REMAINDER_SPEED_KMH
      // so the number cannot blow up as the remainder approaches zero.
      let max;
      if (remKm <= 0) max = 0;
      else if (remH <= 0) max = ZDEMO.maxRemainderKmh;
      else max = Math.min(remKm / remH, ZDEMO.maxRemainderKmh);
      let state = "green";
      if (avg > limit) state = "red";
      else if (now > max) state = "amber";
      frames.push({ d: d, avg: avg, now: now, max: max, state: state, p: d / L });
    }
    return frames;
  }

  function startZoneDemo() {
    const root = document.getElementById("zdemo");
    if (!root) return null;
    const el = {
      avg: document.getElementById("zdemo-avg"),
      now: document.getElementById("zdemo-now"),
      max: document.getElementById("zdemo-max"),
      remain: document.getElementById("zdemo-remain"),
      limit: document.getElementById("zdemo-limit"),
      fill: document.getElementById("zdemo-fill"),
      verdict: document.getElementById("zdemo-verdict"),
    };
    if (!el.avg || !el.verdict) return null;

    const frames = zdemoBuildFrames();
    if (!frames.length) return null;
    const KEYS = { green: "legend.green", amber: "legend.amber", red: "legend.red" };
    let timer = null;
    let observer = null;
    let elapsed = 0;
    let stopped = false;

    // the roundel shows the zone's posted limit, which never changes mid-zone
    if (el.limit) el.limit.textContent = String(ZDEMO.limitKmh);

    function render(f) {
      el.avg.textContent = String(Math.round(f.avg));
      if (el.now) el.now.textContent = String(Math.round(f.now));
      if (el.max) el.max.textContent = String(Math.max(0, Math.round(f.max)));
      if (el.remain) el.remain.textContent = Math.max(0, ZDEMO.lengthKm - f.d).toFixed(1);
      if (el.fill) el.fill.style.width = (f.p * 100).toFixed(1) + "%";
      if (root.getAttribute("data-state") !== f.state) {
        root.setAttribute("data-state", f.state);
        // Retarget the i18n key so apply() keeps translating this on lang switch
        const key = KEYS[f.state];
        el.verdict.setAttribute("data-i18n", key);
        const dict = I18N[document.documentElement.lang];
        if (dict && dict[key]) el.verdict.textContent = dict[key];
      }
    }

    function tick() {
      elapsed = (elapsed + ZDEMO.tickMs) % (ZDEMO.loopMs + ZDEMO.holdMs);
      const p = Math.min(1, elapsed / ZDEMO.loopMs);
      render(frames[Math.min(frames.length - 1, Math.round(p * (frames.length - 1)))]);
    }

    function play() {
      if (stopped || timer || document.hidden) return;
      timer = setInterval(tick, ZDEMO.tickMs);
    }
    function pause() {
      if (timer) { clearInterval(timer); timer = null; }
    }
    function onVisibility() {
      if (document.hidden) pause(); else play();
    }

    // The global reduced-motion rule kills CSS animation but cannot stop a
    // timer, so opt out explicitly and rest on the most informative frame.
    const mq = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq && mq.matches) {
      let still = frames.filter(function (f) { return f.state === "amber"; })[0];
      if (!still) still = frames[Math.floor(frames.length / 2)];
      render(still);
      return { stop: function () { stopped = true; } };
    }

    render(frames[0]);
    document.addEventListener("visibilitychange", onVisibility);
    if (window.IntersectionObserver) {
      observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) play(); else pause(); });
      }, { threshold: 0.15 });
      observer.observe(root);
    } else {
      play();
    }

    return {
      stop: function () {
        stopped = true;
        pause();
        document.removeEventListener("visibilitychange", onVisibility);
        if (observer) { observer.disconnect(); observer = null; }
      },
    };
  }

  let zoneDemo = null;

  /* ------------------- hero AA slot: hydrate real image if the file exists */
  function hydrateAaSlot() {
    const slot = document.getElementById("aa-slot");
    if (!slot) return;
    const src = slot.getAttribute("data-src");
    const key = slot.getAttribute("data-alt-key");
    if (!src) return;
    const probe = new Image();
    probe.onload = () => {
      const dict = I18N[document.documentElement.lang] || {};
      // Stop the demo before detaching its nodes, or the timer ticks into space
      if (zoneDemo) { zoneDemo.stop(); zoneDemo = null; }
      const placeholder = slot.querySelector(".aa-placeholder");
      if (placeholder) placeholder.remove();
      const real = document.createElement("img");
      real.src = src;
      real.setAttribute("width", "1920");
      real.setAttribute("height", "1080");
      real.setAttribute("loading", "lazy");
      real.setAttribute("data-i18n-alt", key);
      real.alt = dict[key] || "";
      slot.appendChild(real);
    };
    probe.src = src;
  }

  /* ----------------------------------------------------------------- init */
  window.addEventListener("DOMContentLoaded", () => {
    setLang(pickLang(), false);
    zoneDemo = startZoneDemo();
    hydrateAaSlot();
    document.querySelectorAll(".lang-pill button").forEach((b) => {
      b.addEventListener("click", () => setLang(b.dataset.lang, true));
    });
    window.addEventListener("popstate", () => setLang(pickLang(), false));
  });
})();
