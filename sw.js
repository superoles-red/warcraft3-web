importScripts('pack.js', 'shell-release.js');
const rootURL=new URL(self.registration.scope);
const cachePrefix='wc3-shell-'+rootURL.pathname+'-';
const cacheName=cachePrefix+self.WC3_SHELL.revision;
const staticFiles=new Set(self.WC3_SHELL.files);

self.addEventListener('install', event=>event.waitUntil((async()=>{
  const cache=await caches.open(cacheName);
  await cache.addAll([...staticFiles].map(name=>new Request(new URL(name,rootURL),{cache:'reload'})));
  await self.skipWaiting();
})()));
self.addEventListener('activate', event=>event.waitUntil((async()=>{
  for (const key of await caches.keys()) {
    if (key.startsWith(cachePrefix) && key!==cacheName) await caches.delete(key);
  }
  await self.clients.claim();
})()));
let current;
async function getPackage(id) {
  if (current?.id === id) return current;
  const row = await packStore('readonly', store => store.get('active'));
  if (!row || row.id !== id) return null;
  const file = await installedArchive(row);
  const entries = await directory(file);
  current = {...row, file, entries};
  return current;
}
async function serve(request, id, name) {
  const pkg = await getPackage(id);
  if (!pkg) return new Response(null, {status:410});
  if (name === 'gamedata/paths.index.json') {
    const names = [...pkg.entries.keys()].filter(n => n.startsWith('gamedata/')).map(n => n.slice('gamedata/'.length));
    return Response.json(names);
  }
  const entry = pkg.entries.get(name);
  if (!entry) return new Response(null, {status:404});
  const blob = await payload(pkg.file, entry);
  const movie = name.startsWith('movies/');
  const headers = new Headers({'Content-Type': movie ? 'video/webm' : 'application/octet-stream',
    'Content-Length': String(blob.size), 'Cache-Control':'no-store'});
  if (movie) {
    headers.set('Accept-Ranges','bytes');
    const range = request.headers.get('Range');
    if (range) {
      const m = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!m || !(m[1] || m[2])) return new Response(null, {status:416});
      const start = m[1] ? Number(m[1]) : Math.max(0, blob.size - Number(m[2]));
      const end = m[1] && m[2] ? Math.min(blob.size-1, Number(m[2])) : blob.size-1;
      if (start > end || end >= blob.size) return new Response(null, {status:416});
      headers.set('Content-Range', 'bytes '+start+'-'+end+'/'+blob.size);
      headers.set('Content-Length', String(end-start+1));
      return new Response(blob.slice(start,end+1), {status:206,headers});
    }
  }
  return new Response(blob, {headers});
}
self.addEventListener('fetch', event => {
  const u = new URL(event.request.url);
  if (u.origin!==rootURL.origin || !u.pathname.startsWith(rootURL.pathname)) return;
  const rel=u.pathname.slice(rootURL.pathname.length);
  const name=rel==='' ? 'index.html' : rel==='engine/' ? 'engine/index.html' : rel;
  if (name === 'manifest.webmanifest' && u.searchParams.has('installed')) {
    event.respondWith((async () => {
      const manifestURL = new URL(name, rootURL);
      const cache = await caches.open(cacheName);
      const template = await cache.match(manifestURL) || await fetch(manifestURL);
      const definition = await template.json();
      const art = await packStore('readonly', store => store.get('presentation'));
      for (const icon of definition.icons) {
        const blob = art?.[icon.src.split('/').pop()];
        if (blob) icon.src = await manifestIconURL(blob);
      }
      return new Response(JSON.stringify(definition), {headers: {
        'Content-Type': 'application/manifest+json', 'Cache-Control': 'no-store'
      }});
    })());
    return;
  }
  if (name.startsWith('presentation/') && event.request.method==='GET') {
    event.respondWith((async()=>{
      const art=await packStore('readonly',store=>store.get('presentation')).catch(()=>null);
      const blob=art?.[name.slice('presentation/'.length)];
      if (blob) return new Response(blob,{headers:{'Content-Type':name.endsWith('.ttf')?'font/ttf':name.endsWith('.webp')?'image/webp':'image/png'}});
      return fetch(event.request);
    })());return;
  }
  if (staticFiles.has(name) && event.request.method==='GET') {
    event.respondWith((async()=>{
      const cache=await caches.open(cacheName);
      return (await cache.match(new URL(name,rootURL))) || fetch(event.request);
    })());return;
  }
  const base = new URL('private-pack/', self.registration.scope);
  if (u.origin !== base.origin || !u.pathname.startsWith(base.pathname)) return;
  const path = decodeURIComponent(u.pathname.slice(base.pathname.length));
  const i = path.indexOf('/');
  event.respondWith(serve(event.request, path.slice(0,i), path.slice(i+1)).catch(() => new Response(null,{status:500})));
});
