/* Project Opener 3 · landing page
   1. Newer release from GitHub (the markup already carries v3.1.0 and its direct links)
   2. The launch sequence (the live thing): autoplay once in view, replay on the button
   3. Reveals, the path check and the office map (one IntersectionObserver)
   4. The ending wordmark fitted to the page width
   Everything on the page is readable with this file absent. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 1. A newer release only ---------- */
  var RELEASES = "https://api.github.com/repos/dexterity-admin/project-opener/releases/latest";
  var SHIPPED = "3.1.0";

  function newer(a, b) { // a > b, dotted versions
    var x = a.split(".").map(Number), y = b.split(".").map(Number);
    for (var i = 0; i < 3; i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); }
    return false;
  }
  function mb(bytes) { return Math.round(bytes / 1048576) + " MB"; }

  function applyRelease(version, assets) {
    var byName = {};
    assets.forEach(function (a) { byName[a.name] = a; });
    var installer = byName["ProjectOpener-Setup-" + version + ".exe"];
    var portable = byName["ProjectOpener-Portable-" + version + ".zip"];
    if (!installer || !portable) return; // never half-swap: the shipped links stay
    document.querySelectorAll("[data-version]").forEach(function (n) { n.textContent = version; });
    document.querySelectorAll("[data-dl]").forEach(function (a) {
      var kind = a.getAttribute("data-dl");
      a.href = kind === "installer" ? installer.browser_download_url : portable.browser_download_url;
    });
    document.querySelectorAll("[data-size]").forEach(function (n) {
      var asset = n.getAttribute("data-size") === "installer" ? installer : portable;
      if (asset.size) n.textContent = mb(asset.size);
    });
  }

  if (window.fetch) {
    fetch(RELEASES, { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (rel) {
        if (!rel || !rel.tag_name || !rel.assets) return;
        var v = String(rel.tag_name).replace(/^v/i, "");
        if (!/^\d+\.\d+\.\d+$/.test(v) || !newer(v, SHIPPED)) return;
        applyRelease(v, rel.assets);
      })
      .catch(function () { /* the markup already says 3.1.0 */ });
  }

  /* ---------- 2. The launch sequence ---------- */
  var openBtn = document.getElementById("open-p12513");
  var sheet = document.getElementById("launch");
  var timers = [];
  var played = false;

  function clearTimers() { timers.forEach(clearTimeout); timers = []; }

  function finish(counts) {
    sheet.classList.remove("is-playing");
    sheet.classList.add("is-done");
    var foot = sheet.querySelector("[data-foot-main]");
    if (foot) foot.textContent = counts.opened + " opened";
    // The Home screen reacts: the finding line, the KPI strip, the card's count.
    var k = document.querySelector("[data-launches]");
    if (k && !k.dataset.bumped) { k.textContent = String(parseInt(k.textContent, 10) + 1); k.dataset.bumped = "1"; }
    var f = document.querySelector("[data-finding]");
    if (f && k) f.textContent = "2 items need attention · " + k.textContent + " launches today";
    var c = document.querySelector("[data-count]");
    if (c) c.textContent = "6/6 items · Just now";
    openBtn.removeAttribute("aria-busy");
  }

  function closeSheet() {
    clearTimers();
    sheet.hidden = true;
    sheet.classList.remove("is-playing");
    openBtn.removeAttribute("aria-busy");
    document.removeEventListener("keydown", onKey);
    openBtn.focus();
  }
  function onKey(e) { if (e.key === "Escape") closeSheet(); }

  function play(ev) {
    if (!sheet) return;
    var manual = !!ev;                  // a click or Enter on the button; autoplay passes nothing
    clearTimers();
    played = true;
    var items = sheet.querySelectorAll(".litem");
    var counts = { opened: 0, skipped: 0 };
    for (var i = 0; i < items.length; i++) {
      items[i].classList.remove("is-lit");
      if (items[i].getAttribute("data-outcome") === "ok") counts.opened++; else counts.skipped++;
    }
    sheet.classList.remove("is-done");
    sheet.hidden = false;
    openBtn.setAttribute("aria-busy", "true");
    document.removeEventListener("keydown", onKey);
    document.addEventListener("keydown", onKey);
    if (manual) sheet.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    sheet.focus({ preventScroll: true });

    if (reduceMotion) {
      // Keep the content, drop the travel: everything resolves at once.
      for (var j = 0; j < items.length; j++) items[j].classList.add("is-lit");
      finish(counts);
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
    timers.push(setTimeout(function () { finish(counts); }, 220 + items.length * step + 120));
  }

  if (openBtn && sheet) {
    openBtn.addEventListener("click", play);
    var close = sheet.querySelector(".launch__close");
    if (close) close.addEventListener("click", closeSheet);
  }

  /* ---------- 3. One observer: reveals, autoplay, the path check, the office map ---------- */
  var win = document.getElementById("demo");
  var pathcard = document.getElementById("pathcard");
  var office = document.getElementById("office");

  function revealDelay(el) {
    // 50–70 ms stagger among the risers of the same section, computed once
    if (el.dataset.delay) return el.dataset.delay;
    var scope = el.closest("section, footer") || document.body;
    var sibs = scope.querySelectorAll("[data-rise]");
    var i = Array.prototype.indexOf.call(sibs, el);
    el.dataset.delay = (i * 60) + "ms";
    return el.dataset.delay;
  }

  function onEnter(el) {
    if (el === win) {
      if (!played && !openBtn.hasAttribute("aria-busy")) {
        if (reduceMotion) play(); else timers.push(setTimeout(function () { if (!played) play(); }, 1200));
      }
      return;
    }
    if (el === pathcard) {
      var lines = el.querySelectorAll(".pathline");
      for (var i = 0; i < lines.length; i++) {
        (function (line, idx) {
          if (reduceMotion) line.classList.add("is-done");
          else setTimeout(function () { line.classList.add("is-done"); }, 200 + idx * 300);
        })(lines[i], i);
      }
      return;
    }
    if (el === office) { el.classList.add("is-in"); return; }
    el.style.transitionDelay = revealDelay(el);
    el.classList.add("is-in");
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        onEnter(e.target);
        io.unobserve(e.target);
      });
    }, { rootMargin: "0px 0px -15% 0px", threshold: 0 });
    document.querySelectorAll("[data-rise]").forEach(function (el) { io.observe(el); });
    if (pathcard) io.observe(pathcard);
    if (office) io.observe(office);
    // The window autoplays once it is 60 % in view of the real viewport (no reveal margin here).
    if (win && openBtn) {
      var wio = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.intersectionRatio < 0.6) return;
          onEnter(win);
          wio.disconnect();
        });
      }, { threshold: [0.6] });
      wio.observe(win);
    }
  } else {
    document.querySelectorAll("[data-rise]").forEach(function (el) { el.classList.add("is-in"); });
    if (pathcard) pathcard.querySelectorAll(".pathline").forEach(function (l) { l.classList.add("is-done"); });
    if (office) office.classList.add("is-in");
  }

  /* ---------- 4. The wordmark fitted to the page width ---------- */
  var fit = document.querySelector(".end__fit");
  var name = document.querySelector(".end__name");
  function fitName() {
    if (!fit || !name) return;
    name.style.fontSize = "100px";
    var w = fit.getBoundingClientRect().width;
    var avail = name.getBoundingClientRect().width;
    if (w > 0 && avail > 0) name.style.fontSize = Math.floor(100 * avail / w * 0.995) + "px";
  }
  function fitWhenReady() {
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitName); else fitName();
  }
  fitWhenReady();
  var rt;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(fitName, 80); });
})();
