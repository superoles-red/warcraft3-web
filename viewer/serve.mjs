import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readdir, stat, readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { resolve, join, relative, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const cache = join(homedir(), 'Library/Caches/warcraft3-original-web');
const install = resolve(process.argv[2] || join(cache, 'extracted/app'));
const dist = resolve(process.argv[3] || join(cache, 'openwar3/dist'));
const host = process.env.WC3_BIND || '127.0.0.1';
const port = Number(process.env.WC3_PORT || 8886);
const here = fileURLToPath(new URL('.', import.meta.url));
const assets = new Map();
const web = new Map();

async function list(dir, accept, optional = false) {
  let entries;
  try { entries = await readdir(dir, { withFileTypes: true }); }
  catch (err) { if (optional && err.code === 'ENOENT') return; throw err; }
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) await list(path, accept);
    if (entry.isFile()) accept(path, entry.name);
  }
}

const manifest = { archives: [], maps: [], customKeys: null, casc: null };
const rootFiles = await readdir(install, { withFileTypes: true });
const build = rootFiles.find(e => e.isFile() && e.name === '.build.info');
if (build) {
  const casc = { buildInfo: build.name, config: [], idx: [], data: {} };
  assets.set(build.name, join(install, build.name));
  await list(join(install, 'Data'), (path, name) => {
    const key = relative(install, path).split(sep).join('\\');
    if (/^[a-f\d]{32}$/i.test(name)) casc.config.push(key);
    else if (/^[a-f\d]{10}\.idx$/i.test(name)) casc.idx.push(key);
    else if (/^data\.\d{3}$/i.test(name)) casc.data[Number(name.slice(5))] = key;
    else return;
    assets.set(key, path);
  });
  manifest.casc = casc;
}
for (const entry of rootFiles) {
  if (entry.isFile() && /^war3.*\.mpq$/i.test(entry.name)) {
    assets.set(entry.name, join(install, entry.name));
    manifest.archives.push(entry.name);
  }
  if (entry.isDirectory() && entry.name.toLowerCase() === 'maps') {
    await list(join(install, entry.name), (path, name) => {
      if (!/\.w3[mx]$/i.test(name)) return;
      const key = relative(install, path).split(sep).join('\\');
      manifest.maps.push(key);
      assets.set(key, path);
    });
  }
}
if (!manifest.casc && !manifest.archives.length) throw Error('Expected a Warcraft III installation with CASC or MPQ data');
await list(dist, (path) => web.set('/' + relative(dist, path).split(sep).join('/'), path));
const index = (await readFile(join(dist, 'index.html'), 'utf8')).replace('</head>', '<script src="/touch.js" defer></script></head>');
web.set('/touch.js', join(here, 'touch.js'));
const types = { '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.png': 'image/png', '.ttf': 'font/ttf', '.woff2': 'font/woff2' };
const manifestText = JSON.stringify(manifest);
const server = createServer(async (req, res) => {
  try {
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/' || url.pathname === '/index.html') {
      if (!url.search) { res.writeHead(302, { Location: '/?local&edition=roc&chapter=Human01&patch=1.30.4' }).end(); return; }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }).end(req.method === 'HEAD' ? undefined : index);
      return;
    }
    if (url.pathname === '/wc3/manifest.json') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }).end(req.method === 'HEAD' ? undefined : manifestText);
      return;
    }
    const game = url.pathname === '/wc3/file';
    const file = game ? assets.get(url.searchParams.get('path')) : web.get(url.pathname);
    if (!file) { res.writeHead(404).end(); return; }
    const { size } = await stat(file);
    const headers = { 'Content-Type': game ? 'application/octet-stream' : types[extname(file)] || 'application/octet-stream',
      'Accept-Ranges': 'bytes', 'Cache-Control': game ? 'private, no-cache' : 'no-cache' };
    let start = 0, end = size - 1;
    if (req.headers.range) {
      const match = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range);
      if (match) {
        start = Number(match[1]);
        if (match[2]) end = Math.min(end, Number(match[2]));
      }
      if (!match || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end) {
        res.writeHead(416, { 'Content-Range': 'bytes */' + size }).end(); return;
      }
      headers['Content-Range'] = 'bytes ' + start + '-' + end + '/' + size;
    }
    headers['Content-Length'] = Math.max(0, end - start + 1);
    res.writeHead(req.headers.range ? 206 : 200, headers);
    if (req.method === 'HEAD' || size === 0) { res.end(); return; }
    const stream = createReadStream(file, { start, end });
    res.on('close', () => stream.destroy());
    stream.on('error', () => res.destroy()).pipe(res);
  } catch (err) {
    console.error(err.message);
    if (!res.headersSent) res.writeHead(500);
    res.end();
  }
});
server.listen(port, host, () => console.log('OpenWar3 listening at http://' + host + ':' + port));
