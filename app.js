const launch = document.querySelector('#launch');
const picker = document.querySelector('#file');
const message = document.querySelector('#message');
const chooser = document.querySelector('#chooser');
const retry = document.querySelector('#retry');
const query = new URLSearchParams(location.search);
const manage = query.has('files');
function gameURL(info) {
  const params = new URLSearchParams();
  if (info) params.set('pack', info.id);
  if (query.get('edition') === 'tft') params.set('edition','tft');
  const map = query.get('map') || info?.startMap;
  if (map) params.set('map',map);
  return 'engine/' + (params.size ? '?' + params : '');
}
function connect(info) {
  launch.href = gameURL(info);
  launch.hidden = false;
  if (!manage) location.replace(launch.href);
}
function choose(error) {
  LoadingScreen.hide();
  chooser.hidden=false;
  message.textContent=error || '';
}
const gameStore=(mode,fn)=>packStore(mode,fn);
const read=key=>gameStore('readonly',s=>s.get(key));
function applyArt(blobs) {
  if (blobs && blobs['background.webp']) LoadingScreen.art(name=>blobs[name] && URL.createObjectURL(blobs[name]));
  if (blobs?.['icon-192.png']) activateInstalledManifest();
}
async function install(file, id, source, name, chunkKeys) {
  LoadingScreen.set('Проверяем игровые файлы…');
  const {manifest,art}=await inspectPack(file);
  applyArt(art);
  const info={id,name,source,startMap:manifest.startMap || null};
  await gameStore('readwrite',store=>{
    const previous=store.get('active');
    previous.onsuccess=()=>{
      const keep=new Set(chunkKeys || []);
      for(const key of previous.result?.chunkKeys || []) if(!keep.has(key)) store.delete(key);
    };
    store.put(art,'presentation');
    store.put(info,'info');
    return store.put(chunkKeys ? {...info,chunkKeys} : {...info,file},'active');
  });
  return info;
}
const crcTable=Uint32Array.from({length:256},(_,i)=>{
  let n=i;
  for(let j=0;j<8;j++) n=(n&1)?(0xedb88320^(n>>>1)):(n>>>1);
  return n>>>0;
});
async function validPart(bytes, part) {
  if (bytes.byteLength!==part.bytes) return false;
  if (crypto.subtle) {
    const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
    return [...hash].map(v=>v.toString(16).padStart(2,'0')).join('')===part.sha256;
  }
  // HTTP over a private Wi-Fi network has no SubtleCrypto in Chrome.
  let crc=0xffffffff;
  for(const b of bytes) crc=crcTable[(crc^b)&255]^(crc>>>8);
  return ((crc^0xffffffff)>>>0)===part.crc32;
}
async function downloadPart(part,url,progress) {
  const response=await fetch(url,{cache:'no-store'});
  if(!response.ok) throw Error('Сервер вернул '+response.status+' при загрузке игровых файлов.');
  const reader=response.body.getReader();
  const bytes=new Uint8Array(part.bytes);
  let offset=0;
  while(true) {
    const {done,value}=await reader.read();
    if(done) break;
    if(offset+value.length>bytes.length) { await reader.cancel();throw Error('Размер полученного блока не совпал.'); }
    bytes.set(value,offset);offset+=value.length;progress(offset);
  }
  if(offset!==bytes.length || !await validPart(bytes,part)) throw Error('Нарушена целостность загрузки. Повторите попытку.');
  return new Blob([bytes]);
}
async function automatic(manifestPath) {
  const url=new URL(manifestPath,location.href);
  const response=await fetch(url,{cache:'no-store'});
  if(!response.ok) throw Error('Каталог полной версии временно недоступен.');
  const catalog=await response.json();
  if(catalog.format!==1 || !/^[0-9a-f]{64}$/.test(catalog.id) || !Array.isArray(catalog.chunks) ||
     !catalog.chunks.length || catalog.chunks.some(p=>!Number.isSafeInteger(p.bytes)||p.bytes<1||p.bytes>32*1024*1024||
       !/^[0-9a-f]{64}$/.test(p.sha256)||p.file!==p.sha256+'.bin') ||
     catalog.chunks.reduce((n,p)=>n+p.bytes,0)!==catalog.bytes) throw Error('Повреждён каталог загрузки.');
  const id='auto-'+catalog.id;
  const old=await read('info');
  if(old?.id===id) return old;
  await LoadingScreen.art(name=>new URL('presentation/'+name,url).href);
  const blocks=[], keys=[];
  let completed=0;
  let lastPaint=-Infinity;
  const report=(additional,force=false)=>{
    const now=performance.now(), bytes=completed+additional;
    if (!force && now-lastPaint<100 && bytes!==catalog.bytes) return;
    lastPaint=now; LoadingScreen.set('Загрузка Warcraft III',bytes,catalog.bytes);
  };
  report(0);
  for(const part of catalog.chunks) {
    const key='chunk/'+part.sha256;
    let blob=await read(key);
    if(blob?.size!==part.bytes) {
      blob=await downloadPart(part,new URL(part.file,url),report);
      await gameStore('readwrite',store=>store.put(blob,key));
    }
    blocks.push(blob);keys.push(key);completed+=part.bytes;report(0,true);
  }
  return install(new Blob(blocks,{type:'application/zip'}),id,'automatic',catalog.name,keys);
}
async function boot() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js',{updateViaCache:'none'}).catch(()=>null);
  const [disk,existing,art]=await Promise.all([
    fetch('local-status.json',{cache:'no-store'}).then(r=>r.ok?r.json():null).catch(()=>null),
    read('info').catch(()=>null), read('presentation').catch(()=>null)
  ]);
  applyArt(art);
  if(manage) {
    if(existing||disk?.ready) connect(existing);
    return choose();
  }
  if(!existing && !disk?.distribution && !disk?.ready) return choose();
  if(existing?.source === 'manual' || (!disk?.distribution && existing)) return connect(existing);
  if(!disk?.distribution) return connect(null);
  // Complete a new installation before starting the game. A prior package survives failure.
  try {
    const info=navigator.locks ? await navigator.locks.request('warcraft3-install',()=>automatic(disk.distribution))
      : await automatic(disk.distribution);
    connect(info);
  } catch(error) {
    if(existing) {launch.href=gameURL(existing);launch.hidden=false;}
    retry.hidden=false;
    choose(error.name==='QuotaExceededError'?'Недостаточно места в хранилище браузера.':error.message);
  }
}
retry.onclick=()=>location.reload();
picker.onchange=async()=>{
  const file=picker.files[0];if(!file)return;
  chooser.hidden=true;
  try {
    const id=Array.from(crypto.getRandomValues(new Uint32Array(4)),n=>n.toString(16).padStart(8,'0')).join('');
    const info=await install(file,id,'manual',file.name);
    location.replace(gameURL(info));
  } catch(error){choose(error.name==='QuotaExceededError'?'Недостаточно места в хранилище браузера.':error.message);}
  finally{picker.value='';}
};
boot().catch(error=>choose(error.message));
