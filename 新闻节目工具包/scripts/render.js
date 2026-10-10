// Deterministic frame renderer for engine/studio.html.
// node render.js <url> range <outDir> <frameFrom> <frameTo>
// node render.js <url> stills <outDir> t1 t2 ...
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const [url, mode, out, ...rest] = process.argv.slice(2);
const FPS = 30;
(async () => {
  const film = await (await fetch(url.replace(/[^/]*$/, 'film.json'))).json();
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.addInitScript(f => { window.__FILM = f; let now = 0; const raf = [], tos = []; let id = 1;
    performance.now = () => now; window.requestAnimationFrame = cb => { raf.push(cb); return id++; };
    window.setTimeout = (cb, ms) => { tos.push({ at: now + (ms || 0), cb }); return id++; };
    window.__adv = ms => { const end = now + ms; tos.sort((a, b) => a.at - b.at); while (tos.length && tos[0].at <= end) { const t = tos.shift(); now = Math.max(now, t.at); t.cb(); tos.sort((a, b) => a.at - b.at); } now = end; const q = raf.splice(0); q.forEach(cb => cb(now)); };
  }, film);
  await p.goto(url); await p.waitForFunction(() => window.READY === true, null, { timeout: 120000, polling: 200 });
  await p.evaluate(() => __adv(33));
  const miss = await p.evaluate(() => window.MISSING_STICKERS || []);
  if (miss.length && (mode === 'stills' || +rest[0] === 0)) console.log(`  （${miss.length} 张贴纸还没有，用占位图：${miss.slice(0, 6).join('、')}${miss.length > 6 ? '…' : ''}）`);
  const step = async () => p.evaluate(async () => { await prepClip(T + 1 / 30); __adv(1000 / 30); });
  const grab = async () => p.evaluate(async () => { await prepClip(T + 1 / 30); __adv(1000 / 30); return document.getElementById('c').toDataURL('image/jpeg', 0.9).slice(23); });
  fs.mkdirSync(out, { recursive: true });
  if (mode === 'layers') {
    const L = await p.evaluate(() => window.exportLayers());
    for (const k of ['back', 'front', 'guide']) fs.writeFileSync(path.join(out, k + '.png'), Buffer.from(L[k].split(',')[1], 'base64'));
  } else if (mode === 'stills') {
    for (const ts of rest) { const t = +ts;
      await p.evaluate(t => { T = Math.max(0, t - 4); last = performance.now(); }, t);
      for (let i = 0; i < Math.round(Math.min(4, t) * FPS) - 1; i++) await step();
      fs.writeFileSync(path.join(out, `still_${ts}.jpg`), Buffer.from(await grab(), 'base64')); }
  } else {
    const f0 = +rest[0], f1 = +rest[1];
    await p.evaluate(t => { T = t; last = performance.now(); }, Math.max(0, f0 / FPS - 3));
    for (let i = 0; i < Math.round(Math.min(3, f0 / FPS) * FPS); i++) await step();
    for (let f = f0; f < f1; f++) fs.writeFileSync(path.join(out, String(f).padStart(5, '0') + '.jpg'), Buffer.from(await grab(), 'base64'));
  }
  const real = errs.filter(e => !/404/.test(e));
  if (real.length) { console.error('页面报错:', real.slice(0, 5)); process.exitCode = 1; }
  await b.close();
})();
