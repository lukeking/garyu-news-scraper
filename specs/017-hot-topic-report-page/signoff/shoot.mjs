// spec 017 簽核截圖（FR-014、SC-005）：對一個交通頁網址截 412 px 亮暗四種狀態與桌機 1024／1280／1440 亮暗，再拼成四張圖。
// 用法見 --help。只讀頁面，不寫任何資料。
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const HELP = `node specs/017-hot-topic-report-page/signoff/shoot.mjs --url <交通頁網址> --out <輸出目錄>
  [--playwright <playwright 套件目錄>] [--chrome <chromium 執行檔>]

預設：--playwright ~/.npm/_npx/5e2e484947874241/node_modules/playwright
      --chrome     ~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome
上次看過：熱點設成 8 天前、新文章設成 3 天前，讓兩個 badge 都有機會出現。
頁面上找不到兩條流（#stream-reports）、齒輪（#stream-settings-btn）或可展開的焦點事件（.ht-focus-toggle）就失敗。`;

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i === -1 ? fallback : process.argv[i + 1];
}
if (process.argv.includes('--help')) { console.log(HELP); process.exit(0); }
const URL_ = arg('--url');
const OUT = arg('--out');
if (!URL_ || !OUT) { console.error(HELP); process.exit(2); }
const HOME = process.env.HOME;
const require = createRequire(import.meta.url);
const { chromium } = require(arg('--playwright', HOME + '/.npm/_npx/5e2e484947874241/node_modules/playwright'));
const CHROME = arg('--chrome', HOME + '/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome');
fs.mkdirSync(OUT, { recursive: true });

const now = Date.now();
const SEEN = {
  traffic_seen_reports: new Date(now - 8 * 86400e3).toISOString(),
  traffic_seen_articles: new Date(now - 3 * 86400e3).toISOString(),
};
const browser = await chromium.launch({ executablePath: CHROME });

async function shot(name, { width, height, dsf = 1, theme, storage, act }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: dsf, locale: 'zh-TW' });
  await ctx.addInitScript(([s]) => {
    localStorage.clear();
    for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v);
  }, [{ theme, ...SEEN, ...storage }]);
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log(`[${name}] pageerror: ${e.message}`));
  await page.goto(URL_, { waitUntil: 'networkidle' });
  await page.waitForSelector('#stream-reports', { state: 'attached', timeout: 10000 });
  if (act) await act(page);
  await page.mouse.move(1, 1);
  await page.waitForTimeout(300);
  const file = path.join(OUT, name + '.png');
  await page.screenshot({ path: file });
  console.log(`${name}: ${width}x${height} theme=${theme}`);
  await ctx.close();
  return file;
}

const mobile = { width: 412, height: 915, dsf: 2 };
const sheets = { 'mobile-light': [], 'mobile-dark': [], 'desktop-light': [], 'desktop-dark': [] };
for (const theme of ['light', 'dark']) {
  const reports = { traffic_stream_last: 'reports' };
  sheets[`mobile-${theme}`].push(
    ['熱點在前', await shot(`m-${theme}-1-reports`, { ...mobile, theme, storage: reports })],
    ['新文章在前', await shot(`m-${theme}-2-articles`, { ...mobile, theme, storage: { traffic_stream_last: 'articles' } })],
    ['齒輪面板展開', await shot(`m-${theme}-3-gear`, { ...mobile, theme, storage: reports,
      act: p => p.click('#stream-settings-btn', { timeout: 5000 }) })],
    ['焦點事件展開（第一項）', await shot(`m-${theme}-4-focus`, { ...mobile, theme, storage: reports,
      act: async p => {
        await p.click('.ht-focus-toggle', { timeout: 5000 });
        await p.$eval('.ht-focus-toggle[aria-expanded="true"]', el => el.closest('li').scrollIntoView({ block: 'start' }));
        await p.evaluate(() => window.scrollBy(0, -60));
      } })]);
  for (const w of [1024, 1280, 1440]) {
    sheets[`desktop-${theme}`].push([`${w} px`, await shot(`d-${w}-${theme}`, { width: w, height: w === 1440 ? 900 : 800, theme, storage: {} })]);
  }
}
await browser.close();

const b = await chromium.launch({ executablePath: CHROME });
for (const [name, items] of Object.entries(sheets)) {
  const p = await b.newPage({ viewport: { width: 400, height: 300 } });
  const row = name.startsWith('mobile');
  const cells = items.map(([cap, f]) =>
    `<figure><figcaption>${cap}</figcaption><img src="data:image/png;base64,${fs.readFileSync(f).toString('base64')}"></figure>`).join('');
  await p.setContent(`<style>body{margin:0;padding:16px;background:#777;font:600 22px sans-serif;color:#fff}
    h1{font-size:26px;margin:0 0 12px} .g{display:flex;flex-direction:${row ? 'row' : 'column'};gap:20px;align-items:flex-start}
    figure{margin:0} figcaption{margin:0 0 6px} img{display:block;border:1px solid #333}</style>
    <h1>${name} · ${URL_} · ${new Date(now).toISOString().slice(0, 10)}</h1><div class="g">${cells}</div>`);
  const file = path.join(OUT, `sheet-${name}.jpg`);
  await p.screenshot({ path: file, fullPage: true, type: 'jpeg', quality: 82 });
  console.log('sheet', file);
  await p.close();
}
await b.close();
