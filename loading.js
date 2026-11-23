const LoadingScreen = (() => {
  const root = document.createElement('section');
  root.id = 'loading';
  root.setAttribute('aria-label','Загрузка Warcraft III');
  root.innerHTML = '<div class="loading-panel"><img id="loading-art" alt="" hidden><img id="loading-logo" alt="" hidden>' +
    '<div class="loading-body"><p class="loading-caption" role="status">Загрузка Warcraft III…</p>' +
    '<div class="loading-meter"><progress aria-label="Загружено"></progress><div class="loading-track" hidden><div class="loading-ink"></div></div>' +
    '<img class="loading-frame" alt="" hidden></div><p class="loading-size"></p></div></div>';
  document.body.append(root);
  const $ = sel => root.querySelector(sel);
  function set(caption, value=null, total=0) {
    root.hidden = false;
    $('.loading-caption').textContent = caption;
    const progress = $('progress');
    root.classList.toggle('waiting',!(typeof value === 'number' && total>0));
    if (typeof value === 'number' && total>0) {
      const percent = Math.min(100,Math.max(0,value/total*100));
      progress.max=100; progress.value=percent;
      root.style.setProperty('--progress',percent+'%');
      $('.loading-size').textContent = total > 1000000
        ? (percent===100 ? Math.ceil(total/1000000) : Math.floor(value/1000000))+' / '+Math.ceil(total/1000000)+' МБ · '+Math.floor(percent)+'%' : '';
    } else {
      progress.removeAttribute('value');
      $('.loading-size').textContent='';
    }
  }
  async function art(urlFor) {
    const edition=new URLSearchParams(location.search).get('edition')==='tft'?'tft':'roc';
    const fontURL=await urlFor('font.ttf');
    if(fontURL && window.FontFace) {
      const face=new FontFace('Warcraft Loading','url("'+fontURL+'")');
      face.load().then(loaded=>document.fonts.add(loaded)).catch(()=>{});
    }
    const images=[['#loading-art','background.webp'],['#loading-logo',edition+'.webp'],['.loading-frame','border.png']];
    await Promise.all(images.map(async ([selector,name])=>{
      const url=await urlFor(name);if(!url) return;
      const img=$(selector);
      img.onload=()=>{img.hidden=false;}; img.src=url;
    }));
    const chooser=document.getElementById('chooser');
    if (chooser) {
      const button=await urlFor('button.webp');
      if (button) {
        chooser.style.setProperty('--wc3-button','url("'+button+'")');
        chooser.classList.add('original-controls');
      }
    }
    const fill=await urlFor('fill.png');
    if(fill) {
      $('.loading-ink').style.backgroundImage='url("'+fill+'")';
      $('.loading-track').hidden=false;$('.loading-meter').classList.add('original');
    }
  }
  return {set,art,hide:()=>{root.hidden=true;}};
})();
