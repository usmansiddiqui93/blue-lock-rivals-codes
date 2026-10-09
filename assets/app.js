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
        var lbl = b.querySelector(".cb-copy-txt");
        if (lbl) {
          lbl.textContent = "Copied"; b.classList.add("done");
          setTimeout(function () { lbl.textContent = "Copy"; b.classList.remove("done"); }, 1400);
        } else if (b.classList.contains("copy")) {
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
    var cat = document.getElementById("qcat");
    var btn = q.parentNode.querySelector(".search-btn");
    var run = function () {
      var term = q.value.trim().toLowerCase();
      var want = cat ? cat.value : "";
      idx = -1;
      if (!term && !want) { box.hidden = true; return; }
      var hits = 0;
      items.forEach(function (li) {
        var inCat = !want || li.getAttribute("data-cat") === want;
        var ok = inCat && li.textContent.toLowerCase().indexOf(term) !== -1 && hits < 8;
        li.classList.toggle("show", ok); if (ok) hits++;
      });
      if (!hits) { box.appendChild(none); } else if (none.parentNode) { none.parentNode.removeChild(none); }
      box.hidden = false; mark();
    };
    q.addEventListener("input", run);
    if (cat) cat.addEventListener("change", function () { run(); q.focus(); });
    if (btn) btn.addEventListener("click", function () {
      var t = visible()[0];
      if (t && q.value.trim()) location.href = t.firstChild.href; else { run(); q.focus(); }
    });
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
  // Email alerts sign-up
  document.querySelectorAll(".alerts-form").forEach(function (f) {
    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var msg = f.querySelector(".af-msg"), btn = f.querySelector("button"), input = f.querySelector("input[type=email]");
      var say2 = function (t, ok) { msg.textContent = t; msg.className = "af-msg " + (ok ? "ok" : "err"); };
      var email = input.value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) { say2("Please enter a valid email address.", false); input.focus(); return; }
      var ep = f.getAttribute("data-endpoint");
      if (!ep) { say2("Email alerts are launching very soon. Please check back shortly.", false); return; }
      btn.disabled = true;
      fetch(ep.replace(/\/$/, "") + "/subscribe", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email, website: f.querySelector(".hp").value })
      }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { r: r, j: j }; }); })
        .then(function (x) {
          if (x.r.ok && x.j.ok) {
            say2(x.j.already ? "You're already subscribed. New codes will come straight to your inbox."
                             : "Almost done! Check your inbox and click the link to confirm.", true);
            input.value = "";
          } else { say2(x.j.error || "Something went wrong. Please try again.", false); }
        })
        .catch(function () { say2("Couldn't reach the server. Check your connection and try again.", false); })
        .then(function () { btn.disabled = false; });
    });
  });
  // Browser (push) notifications
  (function () {
    var boxes = [].slice.call(document.querySelectorAll(".push-box"));
    if (!boxes.length) return;
    var ep = (boxes[0].getAttribute("data-endpoint") || "").replace(/\/$/, "");
    var base = document.body.getAttribute("data-base") || "";
    var supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;
    var ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
    var setAll = function (label, msg, on, disabled) {
      boxes.forEach(function (b) {
        b.hidden = false;
        b.querySelector(".push-label").textContent = label;
        var m = b.querySelector(".push-msg"); m.textContent = msg || "";
        var btn = b.querySelector(".push-btn"); btn.classList.toggle("on", !!on); btn.disabled = !!disabled;
      });
    };
    if (!supported) {
      if (ios && !standalone) setAll("Browser notifications", "On iPhone/iPad: tap Share, then Add to Home Screen, open the site from there and turn notifications on.", false, true);
      return; // other unsupported browsers: keep the option hidden
    }
    var b64ToBytes = function (b64) {
      var pad = "=".repeat((4 - b64.length % 4) % 4), raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
      var out = new Uint8Array(raw.length); for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i); return out;
    };
    var reg = null;
    var permission = function () { // Permissions API is the more reliable source where available
      if (navigator.permissions && navigator.permissions.query) {
        return navigator.permissions.query({ name: "notifications" })
          .then(function (st) { return st.state === "prompt" ? "default" : st.state; })
          .catch(function () { return Notification.permission; });
      }
      return Promise.resolve(Notification.permission);
    };
    var refresh = function () {
      permission().then(function (perm) {
        if (perm === "denied") { setAll("Notifications blocked", "Notifications are blocked for this site. Allow them in your browser's site settings to turn them on.", false, true); return; }
        (reg ? reg.pushManager.getSubscription() : Promise.resolve(null)).then(function (sub) {
          if (sub) setAll("Browser notifications are on", "Tap to turn them off.", true, false);
          else setAll("Turn on browser notifications", "", false, false);
        });
      });
    };
    navigator.serviceWorker.register(base + "/sw.js", { scope: base + "/" }).then(function (r) { reg = r; refresh(); })
      .catch(function () { setAll("Turn on browser notifications", "", false, false); });
    boxes.forEach(function (b) {
      b.querySelector(".push-btn").addEventListener("click", function () {
        if (!ep) { setAll("Turn on browser notifications", "Browser notifications are launching very soon. Please check back shortly.", false, false); return; }
        if (!reg) return;
        setAll("Working…", "", false, true);
        reg.pushManager.getSubscription().then(function (sub) {
          if (sub) { // turn off
            return fetch(ep + "/push-unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: sub.endpoint }) })
              .catch(function () {}).then(function () { return sub.unsubscribe(); })
              .then(function () { setAll("Turn on browser notifications", "Browser notifications are off.", false, false); });
          }
          return Notification.requestPermission().then(function (perm) {
            if (perm !== "granted") { refresh(); return; }
            return fetch(ep + "/vapid").then(function (r) { return r.json(); }).then(function (k) {
              return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(k.publicKey) });
            }).then(function (newSub) {
              return fetch(ep + "/push-subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ subscription: newSub.toJSON() }) })
                .then(function (r) { return r.json().then(function (j) { if (!r.ok || !j.ok) { newSub.unsubscribe(); throw new Error(j.error || "Could not turn on notifications."); } }); });
            }).then(function () { setAll("Browser notifications are on", "Done! You'll get a test notification now, then one for every new code.", true, false); });
          });
        }).catch(function (err) { setAll("Turn on browser notifications", (err && err.message) || "Something went wrong. Please try again.", false, false); });
      });
    });
  })();
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
