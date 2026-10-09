/* Blue Lock Rivals Codes: service worker for browser notifications about new codes. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data && event.data.text() }; }
  var title = data.title || "New Blue Lock Rivals code";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "A new code just dropped. Tap to see it.",
    icon: data.icon,
    badge: data.icon,
    tag: data.tag || "blr-new-code",
    renotify: true,
    data: { url: data.url || self.registration.scope }
  }));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var url = (event.notification.data && event.notification.data.url) || self.registration.scope;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url.indexOf(self.registration.scope) === 0 && "focus" in list[i]) {
        list[i].navigate(url); return list[i].focus();
      }
    }
    return self.clients.openWindow(url);
  }));
});
