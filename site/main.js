/* Project Opener 3 · landing page
   1. The launch sequence (the live thing): autoplay once in view on a desktop, replay on the button
   2. Reveals, the path check and the office map (one IntersectionObserver)
   3. The ending wordmark fitted to the page width (desktop and tablet)
   Nothing is fetched: the markup carries the release's version and direct links, and the page loads from
   its own origin only. Everything on the page is readable with this file absent. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var touchLayout = function () { return window.innerWidth < 1024; }; // tablet and phone: the sheet would cover the button

  /* ---------- 1. The launch sequence ---------- */
  var openBtn = document.getElementById("open-p12513");
  var sheet = document.getElementById("launch");
  var timers = [];
  var played = false;
  // One item per timestamp, as the real sheet reports them: three local items at once, the offline share
  // after its timeout, then the link and the missing reference. The footer's 4.0 s is this schedule's length.
  var SCHEDULE = [220, 480, 740, 3000, 3300, 3600];
  var TOTAL_MS = 4000;

  function clearTimers() { timers.forEach(clearTimeout); timers = []; }

  function finish(counts) {
    sheet.classList.remove("is-playing");
    sheet.classList.add("is-done");
    var foot = sheet.querySelector("[data-foot-main]");
    if (foot) foot.textContent = counts.opened + " opened";
    // The Home screen reacts the way the app does: the finding line counts the launch.
    var f = document.querySelector("[data-finding]");
    if (f && !f.dataset.bumped) {
      f.textContent = f.textContent.replace(/(\d+) launches today/, function (m, n) { return (parseInt(n, 10) + 1) + " launches today"; });
      f.dataset.bumped = "1";
    }
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
    if (bar) { bar.style.transition = "none"; bar.style.width = "0"; void bar.offsetWidth; bar.style.transition = "width " + TOTAL_MS + "ms linear"; bar.style.width = "100%"; }
    for (var n = 0; n < items.length; n++) {
      (function (el, at) {
        timers.push(setTimeout(function () { el.classList.add("is-lit"); }, at));
      })(items[n], SCHEDULE[n] || TOTAL_MS);
    }
    timers.push(setTimeout(function () { finish(counts); }, TOTAL_MS));
  }

  if (openBtn && sheet) {
    openBtn.addEventListener("click", play);
    var close = sheet.querySelector(".launch__close");
    if (close) close.addEventListener("click", closeSheet);
  }

  /* ---------- 2. One observer: reveals, autoplay, the path check, the office map ---------- */
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
      // On a tablet or a phone the sheet opens over or under the button, so it waits for the press.
      if (touchLayout()) return;
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
          else setTimeout(function () { line.classList.add("is-done"); }, 300 + idx * 300);
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

  /* ---------- 3. The wordmark fitted to the page width (the phone sets it on two lines in CSS) ---------- */
  var fit = document.querySelector(".end__fit");
  var name = document.querySelector(".end__name");
  function fitName() {
    if (!fit || !name) return;
    if (window.innerWidth < 768) { name.style.fontSize = ""; return; }
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
