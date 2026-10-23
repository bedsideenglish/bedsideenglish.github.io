/* Local, dependency-free controls. Atlas media stays on demand. */
(() => {
  'use strict';
  let language = 'en';
  try { language = localStorage.getItem('pe-atlas-language') === 'ko' ? 'ko' : 'en'; } catch (_) {}
  const text = (en, ko) => language === 'ko' ? ko : en;
  const viewers = [];
  const search = document.querySelector('#atlas-search');
  const category = document.querySelector('#atlas-category');
  function filter() {
    if (!search) return;
    const query = search.value.normalize('NFKC').toLocaleLowerCase().trim();
    const terms = query.split(/\s+/).filter(Boolean);
    let count = 0;
    document.querySelectorAll('.catalog .atlas-row').forEach(row => {
      const match = (!category.value || row.dataset.category === category.value) && terms.every(term => row.dataset.search.normalize('NFKC').includes(term));
      row.hidden = !match;
      count += Number(match);
    });
    document.querySelector('[data-result-count]').textContent = text(`${count} techniques`, `${count}개 진찰법`);
    document.querySelector('[data-empty]').hidden = count !== 0;
    document.querySelector('[data-clear]').hidden = !query && !category.value;
  }
  search?.addEventListener('input', filter);
  category?.addEventListener('change', filter);
  document.querySelector('[data-clear]')?.addEventListener('click', () => { search.value = ''; category.value = ''; filter(); search.focus(); });

  const scriptBase = new URL('.', document.currentScript.src);
  document.querySelectorAll('[data-viewer]').forEach(root => {
    const config = JSON.parse(root.querySelector('[data-render-config]').textContent);
    const primary = root.querySelector('[data-primary-canvas]');
    const position = root.querySelector('[data-position-canvas]');
    const turningCanvas = position || primary;
    const play = root.querySelector('[data-play]');
    const pause = root.querySelector('[data-stop]');
    const status = root.querySelector('[data-media-status]');
    const timeline = config.diagram || config.figure;
    const frames = timeline.frames;
    let transition = 0, cycle = 1, holds = frames.map(() => 0);
    const canvases = {primary, ...(position ? {position} : {})};
    let step = 0, progress = 0, elapsed = 0, angle = 0;
    let elevation = config.figure.view?.elevation ?? 22, zoom = 1;
    let playing = false, started = 0, raf = 0, renderer = null, busy = false, pending = false;
    let ready = false, starting = null, sequence = 0, disposed = false;
    let inView = false, resumePlayback = true;
    let lastDraw = '', lastTick = -Infinity, captionStep = -1;
    // Bound animation work while preserving automatic playback and native timing.
    const frameInterval = 1000 / 24;
    function adoptTiming(timing) {
      transition=timing.transition;holds=timing.holds;
      cycle=holds.reduce((sum,hold)=>sum+hold+transition,0);
      elapsed=holds.slice(0,step).reduce((sum,hold)=>sum+hold+transition,0);
    }
    function widths() {
      const ratio = Math.min(devicePixelRatio || 1, 2);
      return Object.fromEntries(Object.entries(canvases).map(([key, canvas]) => [key, Math.max(480, Math.min(1600, Math.round(canvas.clientWidth * ratio)))]));
    }
    function state() { return {progress, language, elevation, azimuth:(config.figure.view?.azimuth ?? 0) + angle, zoom, widths:widths()}; }
    function captions() {
      if (captionStep !== step) {
        root.querySelectorAll('[data-caption]').forEach(item => { item.hidden = Number(item.dataset.caption) !== step; });
        root.querySelectorAll('[data-step]').forEach(item => item.setAttribute('aria-pressed', String(Number(item.dataset.step) === step)));
        captionStep = step;
      }
      root.dataset.progress = progress.toFixed(4);
      root.dataset.angle = angle.toFixed(2);
    }
    function finishDraw() {
      busy = false; root.dataset.rendered = 'true';
      if (pending) { pending = false; requestDraw(); }
    }
    function fail(error) {
      root.dataset.playing = 'false';
      playing = false; cancelAnimationFrame(raf); play.disabled = false; pause.disabled = true;
      status.textContent = text('The examination could not load. Reload this page to retry.', '그림을 불러오지 못했습니다. 페이지를 새로고침하세요.');
      root.dataset.renderError = String(error);
    }
    async function ensureRenderer() {
      if (starting) return starting;
      starting = (async () => {
        // An OffscreenCanvas worker keeps geometry calculations off the page's UI thread.
        if (typeof Worker !== 'undefined' && primary.transferControlToOffscreen && typeof OffscreenCanvas !== 'undefined') {
          const worker = new Worker(new URL('renderer/atlas-worker.js?v=canvas3', scriptBase), {type:'module'});
          const transferred = Object.fromEntries(Object.entries(canvases).map(([key, canvas]) => [key, canvas.transferControlToOffscreen()]));
          await new Promise((resolve, reject) => {
            worker.onerror = error => { reject(error); fail(error); };
            worker.onmessage = ({data}) => {
              if (data.type === 'ready') { adoptTiming(data.timing); resolve(); }
              else if (data.type === 'drawn') finishDraw();
              else if (data.type === 'error') { reject(Error(data.message)); fail(data.message); }
            };
            worker.postMessage({type:'init',config,canvases:transferred},Object.values(transferred));
          });
          renderer = s => worker.postMessage({type:'render',sequence:++sequence,state:s});
          root.dataset.renderMode = 'worker';
          window.addEventListener('pagehide', event => { if (!event.persisted) { disposed = true; worker.terminate(); } });
        } else {
          const {drawAtlas,atlasTiming} = await import(new URL('renderer/pe-atlas-browser.js', scriptBase));
          const cardText = JSON.stringify(config);
          const canvasStates = new Map();
          adoptTiming(JSON.parse(atlasTiming(cardText)));
          renderer = s => {
            for (const [key, canvas] of Object.entries(canvases)) {
              const width=s.widths[key];
              const diagram=key==='primary'&&Boolean(config.diagram);
              const pose=key==='position'?0:s.progress;
              const scale=diagram?1:s.zoom;
              const signature=JSON.stringify([width,pose,s.language,s.elevation,s.azimuth,scale]);
              if(canvasStates.get(key)===signature)continue;
              if (canvas.width!==width) { canvas.width=width; canvas.height=Math.round(width*270/480); }
              drawAtlas(canvas,cardText,pose,s.language,s.elevation,s.azimuth,diagram,scale);
              canvasStates.set(key,signature);
            }
            requestAnimationFrame(finishDraw);
          };
          root.dataset.renderMode = 'main';
        }
        ready = true; play.disabled = frames.length < 2; status.textContent = '';
        requestDraw();
      })();
      return starting;
    }
    function requestDraw() {
      if (disposed) return;
      if (!ready) { ensureRenderer().catch(fail); return; }
      if (busy) { pending = true; return; }
      const next = state();
      const key = JSON.stringify(next);
      // In particular, keyframe holds must not redraw the same full mesh at 60 Hz.
      if (key === lastDraw) return;
      busy = true; lastDraw = key;
      try { renderer(next); } catch (error) { busy = false; lastDraw = ''; fail(error); }
    }
    function pausePlayback(preserve = false) {
      resumePlayback = preserve && playing;
      if (playing) elapsed = (performance.now() - started) % cycle;
      playing = false; cancelAnimationFrame(raf); play.disabled = frames.length < 2; pause.disabled = true;
      root.dataset.playing = 'false';
    }
    function tick(now) {
      if (!playing) return;
      raf=requestAnimationFrame(tick);
      if (now-lastTick < frameInterval) return;
      lastTick=now;
      elapsed = (now - started) % cycle;
      let offset=elapsed;
      for (let i=0; i<frames.length; i++) {
        const hold=holds[i];
        if (offset < hold+transition) { step=i;progress=i+Math.max(0,(offset-hold)/transition);break; }
        offset-=hold+transition;
      }
      captions(); requestDraw();
    }
    function beginPlayback() {
      if (playing || disposed || frames.length < 2) return;
      resumePlayback = true; root.dataset.playing = 'true';
      playing=true;lastTick=-Infinity;started=performance.now()-elapsed;play.disabled=true;pause.disabled=false;raf=requestAnimationFrame(tick);
    }
    play.addEventListener('click', async () => {
      try { await ensureRenderer(); beginPlayback(); } catch (error) { fail(error); }
    });
    pause.addEventListener('click',()=>pausePlayback());
    root.querySelectorAll('[data-step]').forEach(button => button.addEventListener('click', () => {
      pausePlayback();step=Number(button.dataset.step);progress=step;
      elapsed=holds.slice(0,step).reduce((sum,hold)=>sum+hold+transition,0);
      captions();requestDraw();
    }));
    function turn(next) { angle=((next+180)%360+360)%360-180;captions();requestDraw(); }
    root.querySelectorAll('[data-turn]').forEach(button=>button.addEventListener('click',()=>turn(angle+Number(button.dataset.turn))));
    root.querySelector('[data-reset]').addEventListener('click',()=>{elevation=config.figure.view?.elevation??22;zoom=1;turn(0);});
    let drag=null;
    turningCanvas.tabIndex=0;turningCanvas.setAttribute('aria-label',text('Drag to rotate. Arrow keys rotate; Home resets.','드래그하여 회전. 방향키로 회전하고 Home 키로 초기화합니다.'));
    turningCanvas.addEventListener('keydown',event=>{
      if (event.key==='ArrowLeft'||event.key==='ArrowRight') {event.preventDefault();turn(angle+(event.key==='ArrowRight'?5:-5));}
      if (event.key==='ArrowUp'||event.key==='ArrowDown') {event.preventDefault();elevation=Math.max(-30,Math.min(90,elevation+(event.key==='ArrowUp'?5:-5)));requestDraw();}
      if (event.key==='Home') {event.preventDefault();root.querySelector('[data-reset]').click();}
    });
    turningCanvas.addEventListener('pointerdown',event=>{if(event.button===0)drag={x:event.clientX,y:event.clientY,angle,id:event.pointerId};});
    turningCanvas.addEventListener('pointermove',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const dx=event.clientX-drag.x;
      if(Math.abs(event.clientY-drag.y)>Math.abs(dx)&&!turningCanvas.hasPointerCapture(event.pointerId)){drag=null;return;}
      if(Math.abs(dx)<5)return;
      turningCanvas.setPointerCapture(event.pointerId);turn(drag.angle+dx*.55);
    });
    for(const name of ['pointerup','pointercancel','lostpointercapture'])turningCanvas.addEventListener(name,()=>{drag=null;});
    new ResizeObserver(()=>{if(ready)requestDraw();}).observe(primary);
    const observer=new IntersectionObserver(entries=>{
      inView=entries.some(entry=>entry.isIntersecting);
      if(inView)ensureRenderer().then(()=>{if(inView&&!document.hidden&&resumePlayback)beginPlayback();}).catch(fail);
      else if(playing)pausePlayback(true);
    },{rootMargin:'100px'});observer.observe(root);
    document.addEventListener('visibilitychange',()=>{
      if(document.hidden){if(playing)pausePlayback(true);}
      else if(inView&&ready&&resumePlayback)beginPlayback();
    });
    viewers.push({refresh(){captions();if(ready)requestDraw();}});
    captions();
  });
  function applyLanguage(initial = false) {
    document.documentElement.lang = language;
    document.querySelectorAll('[data-play-badge]').forEach(img => {
      img.src = img.src.replace(/google-play-badge-(en|ko)\.png/, `google-play-badge-${language}.png`);
      img.alt = text('Get it on Google Play', 'Google Play에서 다운로드');
    });
    document.querySelectorAll('input[name="language"]').forEach(input => { input.checked = input.value === language; });
    for (const viewer of viewers) viewer.refresh(initial);
    filter();
  }
  document.querySelectorAll('input[name="language"]').forEach(input => input.addEventListener('change', () => {
    language = input.value;
    try { localStorage.setItem('pe-atlas-language', language); } catch (_) {}
    applyLanguage();
  }));
  applyLanguage(true);
})();
