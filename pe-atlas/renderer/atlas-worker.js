import { drawAtlas, atlasTiming } from './pe-atlas-browser.js';
import { createFrameRenderer } from './atlas-frame-cache.js?v=canvas4';
let renderer, pending, latest, running = false, warmTimer = 0, active = false;
async function pump() {
  if (running) return;
  clearTimeout(warmTimer);
  running = true;
  try {
    if (pending) {
      const data = pending; pending = null; latest = data.state;
      const stats = await renderer.draw(latest);
      self.postMessage({type: 'drawn', sequence: data.sequence, stats});
    } else if (active && latest) {
      if (!await renderer.warm(latest)) active = false;
    }
  } catch (error) { active = false; self.postMessage({type: 'error', message: String(error)}); }
  finally {
    running = false;
    if (pending) pump();
    else if (active) warmTimer = setTimeout(pump, 25);
  }
}
self.onmessage = ({data}) => {
  try {
    if (data.type === 'init') {
      const timing = JSON.parse(atlasTiming(JSON.stringify(data.config)));
      renderer = createFrameRenderer(data.config, data.canvases, drawAtlas, timing);
      self.postMessage({type: 'ready', timing});
    } else if (data.type === 'active') {
      active = data.value;
      if (active) pump(); else clearTimeout(warmTimer);
    } else if (data.type === 'render') {
      active = data.warm; pending = data; pump();
    }
  } catch (error) { self.postMessage({type: 'error', message: String(error)}); }
};
