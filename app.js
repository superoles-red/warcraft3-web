const launch = document.querySelector('#launch');
const filePicker = document.querySelector('#file');
const message = document.querySelector('#message');
const manage = new URLSearchParams(location.search).has('files');
let swReady = false;

function playURL(info) {
  if (!info) return 'engine/';
  const params = new URLSearchParams({pack: info.id});
  if (info.startMap) params.set('map', info.startMap);
  return 'engine/?' + params;
}
function connect(info) {
  launch.href = playURL(info);
  launch.hidden = false;
  if (!manage) location.replace(launch.href);
}

async function services() {
  if (!('serviceWorker' in navigator)) return;
  await navigator.serviceWorker.register('sw.js');
  await navigator.serviceWorker.ready;
  if (!navigator.serviceWorker.controller) await new Promise(resolve =>
    navigator.serviceWorker.addEventListener('controllerchange', resolve, {once:true}));
  swReady = true;
}
const ready = services().catch(() => {});
async function boot() {
  const disk = await fetch('local-status.json', {cache:'no-store'})
    .then(r => r.ok ? r.json() : null).catch(() => null);
  if (disk?.ready) connect();
  else {
    await ready;
    const meta = swReady && await packStore('readonly', store => store.get('info')).catch(() => null);
    if (meta) connect(meta);
  }
  document.querySelector('main').hidden = false;
}
boot();
filePicker.addEventListener('change', async () => {
  const file = filePicker.files[0];
  if (!file) return;
  message.textContent = 'Проверяем игровой пакет…';
  try {
    await ready;
    if (!swReady) throw Error('Для выбора ZIP откройте страницу по HTTPS или на localhost.');
    const entries = await directory(file);
    const description = entries.get('warcraft3-pack.json');
    if (description.size > 64*1024) throw Error('Повреждён манифест игрового пакета.');
    const manifest = JSON.parse(await (await payload(file, description)).text());
    if (manifest.format !== 1 || (manifest.startMap && !entries.has('gamedata/' + manifest.startMap))) {
      throw Error('В этом пакете отсутствует карта запуска.');
    }
    const info = {id:crypto.randomUUID(), name:file.name, startMap:manifest.startMap || null};
    message.textContent = 'Сохраняем пакет в браузере…';
    await packStore('readwrite', store => {
      store.put(info, 'info');
      return store.put({...info, file}, 'active');
    });
    location.replace(playURL(info));
  } catch (err) {
    message.textContent = err.name === 'QuotaExceededError' ? 'На устройстве недостаточно места для пакета.' : err.message;
  } finally {filePicker.value = '';}
});
