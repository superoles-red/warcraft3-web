// The C file API is synchronous. Chrome bypasses service workers for synchronous
// page XHR. Read short-lived blob: slices of the selected ZIP on this code path.
function readSlice(file, start, length) {
  const blob = file.slice(start, start + length, 'application/octet-stream');
  const url = URL.createObjectURL(blob);
  try {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);
    xhr.overrideMimeType('text/plain; charset=x-user-defined');
    xhr.send();
    const text = xhr.responseText;
    if (xhr.status !== 200 || text.length !== length) throw Error('Неполная запись ZIP.');
    const bytes = new Uint8Array(length);
    for (let i=0; i<length; i++) bytes[i] = text.charCodeAt(i) & 255;
    return bytes;
  } finally { URL.revokeObjectURL(url); }
}

async function mountLocalArchive(id) {
  const row = await packStore('readonly', store => store.get('active'));
  if (!row || row.id !== id) throw Error('Выберите игровой ZIP ещё раз.');
  const file = row.file;
  const entries = await directory(file);
  Module.WC3_READ_LOCAL = (diskPath, rel) => {
    let entry = entries.get('gamedata/' + rel);
    let base64 = false;
    if (!entry && rel.endsWith('.blp')) entry = entries.get('gamedata/' + rel.slice(0,-4) + '.dds');
    if (!entry) {
      entry = entries.get('gamedata/' + rel + '.b64');
      base64 = true;
    }
    if (!entry) return 0;
    if (entry.start === undefined) {
      const h = new DataView(readSlice(file, entry.offset, 30).buffer);
      if (h.getUint32(0,true) !== 0x04034b50) throw Error('Повреждён заголовок ZIP.');
      entry.start = entry.offset + 30 + h.getUint16(26,true) + h.getUint16(28,true);
    }
    let bytes = readSlice(file, entry.start, entry.packed);
    if (entry.method === 8) bytes = fflate.inflateSync(bytes, {out:new Uint8Array(entry.size)});
    if (bytes.length !== entry.size) throw Error('Размер ресурса не совпал с каталогом ZIP.');
    if (base64) bytes = Uint8Array.from(atob(new TextDecoder().decode(bytes)), c => c.charCodeAt(0));
    const fs = Module.FS;
    fs.mkdirTree(diskPath.slice(0, diskPath.lastIndexOf('/')));
    fs.writeFile(diskPath, bytes);
    window.__packReads = (window.__packReads || 0) + 1;
    return bytes.length;
  };
  const catalog = await payload(file, entries.get('gamedata/maps.index.txt'));
  Module.WC3_MAPS = await catalog.text();
}
