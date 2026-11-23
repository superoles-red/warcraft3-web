importScripts('pack.js');
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
let current;
async function getPackage(id) {
  if (current?.id === id) return current;
  const row = await packStore('readonly', store => store.get('active'));
  if (!row || row.id !== id) return null;
  const entries = await directory(row.file);
  current = {...row, entries};
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
  const base = new URL('private-pack/', self.registration.scope);
  if (u.origin !== base.origin || !u.pathname.startsWith(base.pathname)) return;
  const path = decodeURIComponent(u.pathname.slice(base.pathname.length));
  const i = path.indexOf('/');
  event.respondWith(serve(event.request, path.slice(0,i), path.slice(i+1)).catch(() => new Response(null,{status:500})));
});
