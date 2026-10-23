// Lossless snapshots retain the loop compressed, with a small decoded working set.
export function createFrameRenderer(config, canvases, drawAtlas, timing) {
  const compressedLimit = 48 * 1024 * 1024, decodedLimit = 24 * 1024 * 1024;
  const frames = (config.diagram || config.figure).frames.length;
  const samples = Math.max(1, Math.ceil(timing.transition / (1000 / 24)));
  const poses = Array.from({length: frames * samples}, (_, i) => Math.floor(i / samples) + (i % samples) / samples);
  const cardText = JSON.stringify(config);
  const entries = new Map(), decoded = new Map(), displayed = new Map();
  const encodings = new Set();
  let view = '', compressedBytes = 0, decodedBytes = 0, warmIndex = 0;
  const stats = {geometry: 0, hits: 0, decodes: 0, compressedBytes: 0, decodedBytes: 0};
  function clear() {
    for (const item of decoded.values()) item.image.close?.();
    entries.clear(); decoded.clear(); displayed.clear();
    compressedBytes = decodedBytes = warmIndex = 0;
  }
  function updateStats() {
    stats.compressedBytes = compressedBytes; stats.decodedBytes = decodedBytes;
    return {...stats};
  }
  function adopt(s) {
    const next = JSON.stringify([s.language, s.elevation, s.azimuth, s.zoom, s.widths]);
    if (view !== next) { clear(); view = next; }
  }
  function spec(key, s, pose = s.progress) {
    const width = s.widths[key], height = Math.round(width * 270 / 480);
    const diagram = key === 'primary' && Boolean(config.diagram);
    const progress = key === 'position' ? 0 : pose;
    return {width, height, diagram, progress, zoom: diagram ? 1 : s.zoom, id: `${key}:${progress}`};
  }
  function retain(id, image, bytes) {
    while (decodedBytes + bytes > decodedLimit && decoded.size) {
      const oldest = decoded.keys().next().value, item = decoded.get(oldest);
      decoded.delete(oldest); decodedBytes -= item.bytes; item.image.close?.();
    }
    decoded.set(id, {image, bytes}); decodedBytes += bytes;
    return image;
  }
  async function decode(blob) {
    if (typeof createImageBitmap === 'function') return createImageBitmap(blob);
    const image = new Image(), url = URL.createObjectURL(blob);
    try { image.src = url; await image.decode(); return image; }
    finally { URL.revokeObjectURL(url); }
  }
  async function prepare(key, s, pose) {
    const p = spec(key, s, pose), resident = decoded.get(p.id);
    if (resident) {
      decoded.delete(p.id); decoded.set(p.id, resident);
      stats.hits++; return resident.image;
    }
    const record = entries.get(p.id), bytes = p.width * p.height * 4;
    if (record) {
      const blob = record.blob || await record.promise;
      if (blob) {
        entries.delete(p.id); entries.set(p.id, record);
        stats.hits++; stats.decodes++;
        return retain(p.id, await decode(blob), bytes);
      }
    }
    // Bound temporary surfaces and encode work, while showing a new frame before
    // its lossless compression finishes. The first animation need not wait for PNG.
    if (encodings.size >= 2) await Promise.race(encodings);
    const surface = typeof OffscreenCanvas === 'function'
      ? new OffscreenCanvas(p.width, p.height) : document.createElement('canvas');
    surface.width = p.width; surface.height = p.height;
    // Snapshots read pixels: avoid an expensive GPU readback for each new mesh.
    surface.getContext('2d', {willReadFrequently: true});
    drawAtlas(surface, cardText, p.progress, s.language, s.elevation, s.azimuth, p.diagram, p.zoom);
    stats.geometry++;
    const image = typeof createImageBitmap === 'function' ? await createImageBitmap(surface) : null;
    const entry = {blob: null, promise: null};
    entries.set(p.id, entry);
    const task = (async () => {
      try {
        const png = surface.convertToBlob
          ? await surface.convertToBlob({type: 'image/png'})
          : await new Promise(resolve => surface.toBlob(resolve, 'image/png'));
        if (entries.get(p.id) === entry) {
          if (png && png.size <= compressedLimit) {
            entry.blob = png; compressedBytes += png.size;
            for (const [id, old] of entries) {
              if (compressedBytes <= compressedLimit) break;
              if (old.blob) { compressedBytes -= old.blob.size; entries.delete(id); }
            }
          } else entries.delete(p.id);
        }
        return png;
      } catch (_) {
        if (entries.get(p.id) === entry) entries.delete(p.id);
        return null; // A snapshot failure can still use the decoded working set.
      } finally {
        surface.width = surface.height = 1;
      }
    })();
    entry.promise = task; encodings.add(task);
    task.then(() => encodings.delete(task));
    const snapshot = image || await decode(await task);
    return retain(p.id, snapshot, bytes);
  }
  return {
    async draw(s) {
      adopt(s);
      for (const [key, canvas] of Object.entries(canvases)) {
        const p = spec(key, s);
        if (displayed.get(key) === p.id) continue;
        const image = await prepare(key, s, s.progress);
        if (canvas.width !== p.width) { canvas.width = p.width; canvas.height = p.height; }
        const g = canvas.getContext('2d');
        g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(image, 0, 0);
        displayed.set(key, p.id);
      }
      return updateStats();
    },
    async warm(s) {
      adopt(s);
      // One frame per task lets incoming rotations take priority.
      while (warmIndex < poses.length) {
        const pose = poses[warmIndex++];
        if (!entries.has(spec('primary', s, pose).id)) {
          await prepare('primary', s, pose); return true;
        }
      }
      return false;
    },
    dispose: clear,
    stats: updateStats,
  };
}
