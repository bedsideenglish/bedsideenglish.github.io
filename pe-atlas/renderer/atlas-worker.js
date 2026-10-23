import { drawAtlas, atlasTiming } from './pe-atlas-browser.js';
let config, cardText, canvases;
const lastDraw = new Map();
self.onmessage = ({ data }) => {
  try {
    if (data.type === 'init') {
      config = data.config; cardText = JSON.stringify(config); canvases = data.canvases;
      self.postMessage({ type: 'ready', timing: JSON.parse(atlasTiming(cardText)) }); return;
    }
    const s = data.state;
    for (const [key, canvas] of Object.entries(canvases)) {
      const width = s.widths[key];
      const diagram = key === 'primary' && Boolean(config.diagram);
      const progress = key === 'position' ? 0 : s.progress;
      const zoom = diagram ? 1 : s.zoom;
      const signature = JSON.stringify([width, progress, s.language, s.elevation, s.azimuth, zoom]);
      if (lastDraw.get(key) === signature) continue;
      if (canvas.width !== width) { canvas.width = width; canvas.height = Math.round(width * 270 / 480); }
      drawAtlas(canvas, cardText, progress, s.language, s.elevation, s.azimuth, diagram, zoom);
      lastDraw.set(key, signature);
    }
    self.postMessage({ type: 'drawn', sequence: data.sequence });
  } catch (error) { self.postMessage({ type: 'error', message: String(error) }); }
};
