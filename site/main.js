/* Project Opener 3 · landing page
   1. Release version from GitHub (static fallback stays in the markup)
   2. The launch sequence (the live thing)
   3. Entrances, the floating window and button feedback (GSAP + ScrollTrigger)
   Everything on the page is readable with this file absent. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 1. Version ---------- */
  var RELEASES = "https://api.github.com/repos/dexterity-admin/project-opener/releases/latest";
  var FALLBACK = "3.1.0";

  function applyVersion(version, assets) {
    var nodes = document.querySelectorAll("[data-version]");
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = version;
    var byName = {};
    (assets || []).forEach(function (a) { byName[a.name] = a.browser_download_url; });
    var installer = byName["ProjectOpener-Setup-" + version + ".exe"];
    var portable = byName["ProjectOpener-Portable-" + version + ".zip"];
    document.querySelectorAll("[data-dl]").forEach(function (a) {
      var kind = a.getAttribute("data-dl");
      if (kind === "installer" && installer) a.href = installer;
      if (kind === "portable" && portable) a.href = portable;
    });
  }

  if (window.fetch) {
    fetch(RELEASES, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (rel) {
        if (!rel || !rel.tag_name) return;
        var v = String(rel.tag_name).replace(/^v/i, "");
        if (!/^\d+\.\d+\.\d+/.test(v)) return;
        applyVersion(v, rel.assets);
      })
      .catch(function () { /* the markup already says 3.1.0 */ });
  }
  if (!document.querySelector("[data-version]").textContent) applyVersion(FALLBACK);

  /* ---------- 2. The launch sequence ---------- */
  var openBtn = document.getElementById("open-p12513");
  var sheet = document.getElementById("launch");
  var playing = false;
  var timers = [];

  function clearTimers() { timers.forEach(clearTimeout); timers = []; }

  function finish(items, counts) {
    sheet.classList.remove("is-playing");
    sheet.classList.add("is-done");
    var foot = sheet.querySelector("[data-foot-main]");
    if (foot) foot.textContent = counts.opened + " opened";
    // The Home screen reacts: Recent activity, the KPI strip, the card's count.
    var t = document.querySelector("[data-act-title]");
    var s = document.querySelector("[data-act-sub]");
    var ago = document.querySelector("[data-act-ago]");
    if (t) t.textContent = "P12513 As-built isometrics";
    if (s) s.textContent = counts.opened + " opened · " + counts.skipped + " skipped";
    if (ago) ago.textContent = "just now";
    var k = document.querySelector("[data-launches]");
    if (k && !k.dataset.bumped) { k.textContent = String(parseInt(k.textContent, 10) + 1); k.dataset.bumped = "1"; }
    var c = document.querySelector("[data-count]");
    if (c) c.textContent = "6/6 items · opened 16× · just now";
    openBtn.removeAttribute("aria-busy");
    playing = false;
  }

  function play() {
    if (!sheet) return;
    clearTimers();
    var items = sheet.querySelectorAll(".litem");
    var counts = { opened: 0, skipped: 0 };
    for (var i = 0; i < items.length; i++) {
      items[i].classList.remove("is-lit");
      if (items[i].getAttribute("data-outcome") === "ok") counts.opened++; else counts.skipped++;
    }
    sheet.classList.remove("is-done");
    sheet.hidden = false;
    openBtn.setAttribute("aria-busy", "true");
    playing = true;

    if (reduceMotion) {
      // Keep the content, drop the travel: everything resolves at once.
      for (var j = 0; j < items.length; j++) items[j].classList.add("is-lit");
      finish(items, counts);
      return;
    }

    sheet.classList.add("is-playing");
    var bar = sheet.querySelector(".launch__bar i");
    if (bar) { bar.style.transition = "none"; bar.style.width = "0"; void bar.offsetWidth; bar.style.transition = ""; bar.style.width = "100%"; }
    var step = 260;
    for (var n = 0; n < items.length; n++) {
      (function (el, idx) {
        timers.push(setTimeout(function () { el.classList.add("is-lit"); }, 220 + idx * step));
      })(items[n], n);
    }
    timers.push(setTimeout(function () { finish(items, counts); }, 220 + items.length * step + 120));
  }

  if (openBtn && sheet) {
    openBtn.addEventListener("click", play);
    var close = sheet.querySelector(".launch__close");
    if (close) close.addEventListener("click", function () {
      clearTimers(); sheet.hidden = true; sheet.classList.remove("is-playing"); playing = false;
      openBtn.removeAttribute("aria-busy"); openBtn.focus();
    });
    sheet.addEventListener("keydown", function (e) { if (e.key === "Escape") { close && close.click(); } });
  }

  /* ---------- 3. Motion layer ---------- */
  function motion() {
    var gsap = window.gsap;
    if (!gsap || !window.ScrollTrigger || reduceMotion) return;
    gsap.registerPlugin(window.ScrollTrigger);

    // Hero: heading → sentence → action on load; the app window is never hidden.
    var heroParts = document.querySelectorAll(".hero > [data-rise]:not(.stage), .hero__row > [data-rise]");
    if (heroParts.length) gsap.from(heroParts, { opacity: 0, y: 20, duration: 0.6, ease: "power3.out", stagger: 0.08 });

    // Entrance per section: heading → text → picture, 80 ms apart, 20 px rise, once.
    var sections = document.querySelectorAll("section:not(.hero), footer");
    for (var i = 0; i < sections.length; i++) {
      var all = sections[i].querySelectorAll("[data-rise]");
      var parts = [];
      for (var p = 0; p < all.length; p++) {
        if (all[p].closest("section, footer") === sections[i]) parts.push(all[p]);
      }
      if (!parts.length) continue;
      gsap.from(parts, {
        opacity: 0, y: 20, duration: 0.7, ease: "power3.out", stagger: 0.08,
        scrollTrigger: { trigger: sections[i], start: "top 82%", once: true }
      });
    }

    // The moving picture: the app window drifts 6 px over 6 s.
    var win = document.querySelector(".stage .win");
    if (win) {
      gsap.to(win, { y: -6, duration: 3, ease: "sine.inOut", yoyo: true, repeat: -1, delay: 1.2 });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", motion);
  else motion();
})();
