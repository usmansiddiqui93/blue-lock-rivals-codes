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
