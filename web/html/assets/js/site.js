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
    hydrateAaSlot();
    document.querySelectorAll(".lang-pill button").forEach((b) => {
      b.addEventListener("click", () => setLang(b.dataset.lang, true));
    });
    window.addEventListener("popstate", () => setLang(pickLang(), false));
  });
})();
