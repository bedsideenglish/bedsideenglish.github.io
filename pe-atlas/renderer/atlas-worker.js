import { drawAtlas, atlasTiming } from './pe-atlas-browser.js';
let config, cardText, canvases;
self.onmessage = ({ data }) => {
  try {
    if (data.type === 'init') {
      config = data.config; cardText = JSON.stringify(config); canvases = data.canvases;
      self.postMessage({ type: 'ready', timing: JSON.parse(atlasTiming(cardText)) }); return;
    }
    const s = data.state;
    for (const [key, canvas] of Object.entries(canvases)) {
      const width = s.widths[key];
      if (canvas.width !== width) { canvas.width = width; canvas.height = Math.round(width * 270 / 480); }
      drawAtlas(canvas, cardText, key === 'position' ? 0 : s.progress, s.language,
        s.elevation, s.azimuth, key === 'primary' && Boolean(config.diagram),
        key === 'primary' && config.diagram ? 1 : s.zoom);
    }
    self.postMessage({ type: 'drawn', sequence: data.sequence });
  } catch (error) { self.postMessage({ type: 'error', message: String(error) }); }
};
