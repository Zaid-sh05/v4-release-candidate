const CACHE='qanoni-v4-static-40';
const ASSETS=['/','/static/styles.css?v=40','/static/pilot-polish.css?v=1','/static/app.js?v=40','/static/feedback-review.css?v=2','/static/feedback-review.js?v=2','/favicon.ico'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).catch(()=>{})));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))),self.clients.claim()])));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)))});
