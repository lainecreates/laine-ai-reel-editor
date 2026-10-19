// Render an overlay page to transparent PNG frames with headless Chrome.
// Zero npm dependencies: talks to Chrome over the DevTools protocol using
// Node's built-in WebSocket and fetch.
//
//   node tools/render_overlay.mjs <page.html> <out_dir> <fps> <duration> [width height]
//
// The page must define window.__seek(t) -> state key (string). Frames whose
// key matches the previous frame reuse its PNG, so static stretches cost
// nothing. Writes <out_dir>/frames.ffconcat for ffmpeg's concat demuxer.
// Chrome runs with its own temporary profile; the user's Chrome is untouched.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [page, outDir, fpsArg, durArg, wArg = '1080', hArg = '1920'] = process.argv.slice(2);
const fps = Number(fpsArg), duration = Number(durArg), W = Number(wArg), H = Number(hArg);
const CHROME = process.env.LAINE_CHROME || [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  join(homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find(existsSync);
if (!CHROME) { console.error('Google Chrome or Chromium not found'); process.exit(2); }

mkdirSync(outDir, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), 'laine-reel-chrome-'));
const chrome = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-sync', '--hide-scrollbars',
  '--force-device-scale-factor=1', '--mute-audio', `--window-size=${W},${H}`, 'about:blank',
], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));
let port;
for (let i = 0; i < 200 && !port; i++) {
  await sleep(50);
  const f = join(profile, 'DevToolsActivePort');
  if (existsSync(f)) port = readFileSync(f, 'utf8').split('\n')[0];
}
if (!port) { chrome.kill(); console.error('Chrome did not start'); process.exit(3); }
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let nextId = 1; const pending = new Map(); const waiters = [];
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  else if (m.method) waiters.filter(w => w.method === m.method).forEach(w => w.resolve(m));
};
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = nextId++;
  pending.set(id, m => m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result));
  ws.send(JSON.stringify({ id, method, params }));
});
const once = method => new Promise(resolve => waiters.push({ method, resolve }));

// If Chrome stalls while loading the page (rare), give up after 60 s so the
// caller can retry, instead of waiting forever.
const loadWatchdog = setTimeout(() => { console.error('page load timed out'); chrome.kill(); process.exit(5); }, 60000);
try {
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 0, g: 0, b: 0, a: 0 } });
  const loaded = once('Page.loadEventFired');
  await send('Page.navigate', { url: pathToFileURL(resolve(page)).href });
  await loaded;
  await send('Runtime.evaluate', { expression: 'document.fonts.ready.then(() => 1)', awaitPromise: true });
  clearTimeout(loadWatchdog);

  // Record the font stack each element really got (checked against the brand).
  const fr = await send('Runtime.evaluate', { expression: 'window.__fonts ? window.__fonts() : "[]"', returnByValue: true });
  writeFileSync(join(outDir, 'fonts.json'), fr.result.value);
  const fl = await send('Runtime.evaluate', { expression: 'window.__fontsLoaded ? window.__fontsLoaded() : "{}"', awaitPromise: true, returnByValue: true });
  writeFileSync(join(outDir, 'fonts_loaded.json'), fl.result.value);
  const rr = await send('Runtime.evaluate', { expression: 'window.__rects ? window.__rects() : "[]"', returnByValue: true });
  writeFileSync(join(outDir, 'rects.json'), rr.result.value);
  // Any error inside the page (e.g. a style component) fails the render loudly.
  const er = await send('Runtime.evaluate', { expression: 'JSON.stringify(window.__errors || [])', returnByValue: true });
  writeFileSync(join(outDir, 'errors.json'), er.result.value);
  if (JSON.parse(er.result.value).length) { console.error('page errors: ' + er.result.value); process.exitCode = 4; }
  // What each element really looks like (style comparison tests).
  const sr = await send('Runtime.evaluate', { expression: 'window.__styleReport ? window.__styleReport() : "[]"', returnByValue: true });
  writeFileSync(join(outDir, 'style_report.json'), sr.result.value);

  const total = Math.round(duration * fps);
  const lines = ['ffconcat version 1.0'];
  let prevKey = null, prevFile = null, runStart = 0, shots = 0;
  const flush = (endFrame) => {
    if (prevFile !== null) {
      lines.push(`file '${prevFile}'`, `duration ${((endFrame - runStart) / fps).toFixed(6)}`);
    }
  };
  for (let i = 0; i < total; i++) {
    const t = i / fps;
    const r = await send('Runtime.evaluate', { expression: `window.__seek(${t})`, returnByValue: true });
    const key = String(r.result.value);
    if (key === prevKey) continue;
    flush(i);
    const file = `f_${String(i).padStart(6, '0')}.png`;
    const shot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
    writeFileSync(join(outDir, file), Buffer.from(shot.data, 'base64'));
    shots++;
    prevKey = key; prevFile = file; runStart = i;
  }
  flush(total);
  lines.push(`file '${prevFile}'`);  // concat demuxer needs the last file repeated
  writeFileSync(join(outDir, 'frames.ffconcat'), lines.join('\n') + '\n');
  console.log(JSON.stringify({ frames: total, screenshots: shots }));
} finally {
  ws.close(); chrome.kill();
  await sleep(200);
  rmSync(profile, { recursive: true, force: true });
}
