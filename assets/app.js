(function () {
  var toast = document.createElement("div");
  toast.className = "toast";
  document.body.appendChild(toast);
  function say(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(say.t);
    say.t = setTimeout(function () { toast.classList.remove("show"); }, 1600);
  }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () { return legacyCopy(text); });
    }
    return legacyCopy(text);
  }
  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } finally { document.body.removeChild(ta); }
    return Promise.resolve();
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy]");
    if (b) {
      copy(b.getAttribute("data-copy")).then(function () {
        if (b.classList.contains("copy")) {
          var old = b.textContent; b.textContent = "Copied"; b.classList.add("done");
          setTimeout(function () { b.textContent = old; b.classList.remove("done"); }, 1400);
        }
        say(b.hasAttribute("data-copy-all") ? "All active codes copied" : "Copied " + b.getAttribute("data-copy"));
      });
      return;
    }
    var m = e.target.closest(".menu-btn");
    if (m) {
      var nav = document.getElementById("nav");
      var open = nav.classList.toggle("open");
      m.setAttribute("aria-expanded", open ? "true" : "false");
    }
    var s = e.target.closest("[data-share]");
    if (s) {
      if (navigator.share) navigator.share({ title: document.title, url: location.href }).catch(function () {});
      else copy(location.href).then(function () { say("Link copied"); });
    }
  });
  // Next-update countdown: next <weekday> at <hour>:00 Pacific time, shown in the visitor's zone.
  var cdRoot = document.querySelector("[data-countdown]");
  if (cdRoot && window.Intl) {
    var WD = +cdRoot.getAttribute("data-weekday"), HR = +cdRoot.getAttribute("data-hour");
    var LA = "America/Los_Angeles";
    var offsetMin = function (when) { // minutes LA is behind UTC at that instant
      var p = {};
      new Intl.DateTimeFormat("en-US", { timeZone: LA, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric" })
        .formatToParts(when).forEach(function (x) { p[x.type] = +x.value; });
      return (Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - when.getTime()) / 60000;
    };
    var nextTarget = function () {
      var now = new Date();
      var p = {};
      new Intl.DateTimeFormat("en-US", { timeZone: LA, year: "numeric", month: "numeric", day: "numeric" })
        .formatToParts(now).forEach(function (x) { p[x.type] = +x.value; });
      for (var i = 0; i < 8; i++) {
        var dayUTC = new Date(Date.UTC(p.year, p.month - 1, p.day + i, HR));
        if (dayUTC.getUTCDay() !== WD) continue;
        var guess = new Date(dayUTC.getTime() - offsetMin(dayUTC) * 60000);
        if (guess > now) return guess;
      }
      return null;
    };
    var target = nextTarget();
    if (target) {
      var fmt = function (tz) {
        var o = { weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" };
        if (tz) o.timeZone = tz;
        return target.toLocaleString(undefined, o);
      };
      var local = cdRoot.querySelector("[data-local]");
      if (local) local.textContent = fmt() + " (your time)";
      document.querySelectorAll("[data-zone]").forEach(function (td) {
        try { td.textContent = fmt(td.getAttribute("data-zone")); } catch (err) {}
      });
      var q = function (s) { return cdRoot.querySelector(s); };
      var tick = function () {
        var ms = Math.max(0, target - Date.now()), s = Math.floor(ms / 1000);
        q("[data-d]").textContent = Math.floor(s / 86400);
        q("[data-h]").textContent = String(Math.floor(s % 86400 / 3600)).padStart(2, "0");
        q("[data-m]").textContent = String(Math.floor(s % 3600 / 60)).padStart(2, "0");
        q("[data-s]").textContent = String(s % 60).padStart(2, "0");
      };
      tick();
      setInterval(tick, 1000);
    }
  }
  // Site search: filters a pre-rendered list of pages and working codes.
  var q = document.getElementById("q");
  if (q) {
    var box = q.parentNode.querySelector(".search-results");
    var items = [].slice.call(box.querySelectorAll("li"));
    var none = document.createElement("li"); none.className = "none"; none.textContent = "No matches. Try \"codes\", \"tier\" or \"spins\".";
    var idx = -1;
    var visible = function () { return items.filter(function (li) { return li.classList.contains("show"); }); };
    var mark = function () {
      visible().forEach(function (li, i) { li.firstChild.classList.toggle("active", i === idx); });
    };
    var run = function () {
      var term = q.value.trim().toLowerCase();
      idx = -1;
      if (!term) { box.hidden = true; return; }
      var hits = 0;
      items.forEach(function (li) {
        var ok = li.textContent.toLowerCase().indexOf(term) !== -1 && hits < 8;
        li.classList.toggle("show", ok); if (ok) hits++;
      });
      if (!hits) { box.appendChild(none); } else if (none.parentNode) { none.parentNode.removeChild(none); }
      box.hidden = false; mark();
    };
    q.addEventListener("input", run);
    q.addEventListener("focus", run);
    q.addEventListener("keydown", function (ev) {
      var vis = visible();
      if (ev.key === "ArrowDown") { idx = Math.min(idx + 1, vis.length - 1); mark(); ev.preventDefault(); }
      else if (ev.key === "ArrowUp") { idx = Math.max(idx - 1, 0); mark(); ev.preventDefault(); }
      else if (ev.key === "Enter") { var t = vis[Math.max(idx, 0)]; if (t) location.href = t.firstChild.href; }
      else if (ev.key === "Escape") { box.hidden = true; q.blur(); }
    });
    document.addEventListener("click", function (ev) { if (!q.parentNode.contains(ev.target)) box.hidden = true; });
  }
  // Relative "checked x min ago"
  document.querySelectorAll("time[data-rel]").forEach(function (t) {
    var d = new Date(t.getAttribute("datetime"));
    if (isNaN(d)) return;
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    var txt = mins < 1 ? "just now" : mins < 60 ? mins + " min ago" : mins < 1440 ? Math.round(mins / 60) + " h ago" : Math.round(mins / 1440) + " days ago";
    t.textContent = txt;
    t.title = d.toLocaleString();
  });
})();
