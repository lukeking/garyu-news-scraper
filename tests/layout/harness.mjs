// spec 017 SC-007（research R13）：在真的 Chromium 上載入出貨的 pages/traffic/，量版面而不是讀 CSS 文字。
// 頁面由本機 node:http 送出；Worker API 換成 fixtures/ 的 JSON、modern-normalize 換成 vendor/ 的同版副本，
// 其餘外部請求一律 abort 並記進 blocked——測試不打網路，也看得到頁面要了什麼沒準備的東西。
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE_DIR = path.join(HERE, '..', '..', 'pages', 'traffic');
const INDEX = fs.readFileSync(path.join(PAGE_DIR, 'index.html'), 'utf8');

// 出貨的頁面換了版本或 API 網址而這裡沒跟上，量到的就是一份跟 prod 不同的頁面：直接 throw，不靜靜地量下去。
const NORMALIZE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/modern-normalize/2.0.0/modern-normalize.min.css';
if (!INDEX.includes(`href="${NORMALIZE_URL}"`)) {
  throw new Error('harness 過期：index.html 不再載入 modern-normalize 2.0.0，tests/layout/vendor/ 的副本要跟著換');
}
const API_BASE = INDEX.match(/window\.__API_BASE__\s*=\s*'([^']+)'/)?.[1];
if (!API_BASE) throw new Error('harness 過期：index.html 找不到 window.__API_BASE__');
const NORMALIZE_CSS = fs.readFileSync(path.join(HERE, 'vendor', 'modern-normalize.min.css'));

// 照 deploy-pages-traffic.yml 的組法送：app.js、shared.css 取自 pages/shared/。pages/traffic/ 的同名 symlink 被 gitignore，
// fresh checkout（CI、review worktree）沒有它們。部署改了組法而這裡沒跟上，就 throw。
const SHARED_DIR = path.join(HERE, '..', '..', 'pages', 'shared');
const FROM_SHARED = ['app.js', 'shared.css'];
const DEPLOY = fs.readFileSync(path.join(HERE, '..', '..', '.github', 'workflows', 'deploy-pages-traffic.yml'), 'utf8');
for (const name of FROM_SHARED) {
  if (!DEPLOY.includes(`cp pages/shared/${name} /tmp/deploy-traffic/${name}`)) {
    throw new Error(`harness 過期：deploy-pages-traffic.yml 不再從 pages/shared/ 複製 ${name}`);
  }
}

/** fixtures 的 image_url 都在這個來源；回一張 1×1 PNG，圖載得到，寬幅條才不會被 onerror 移掉。 */
export const IMAGE_ORIGIN = 'https://img.layout.test';
const PNG_1PX = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');

/** page.clock 釘住的「現在」。fixtures 的 published 是相對它寫的，所以「10 分鐘前」不隨跑測試的時間變。 */
export const NOW = '2026-11-05T04:00:00Z';

const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
const fixture = name => JSON.parse(fs.readFileSync(path.join(HERE, 'fixtures', name), 'utf8'));

function serve() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, 'http://local').pathname);
    const shared = FROM_SHARED.includes(rel.slice(1));
    const file = shared ? path.join(SHARED_DIR, rel.slice(1)) : path.join(PAGE_DIR, rel === '/' ? 'index.html' : rel);
    let body = null;
    if (shared || file.startsWith(PAGE_DIR + path.sep)) {
      try { body = fs.readFileSync(file); } catch { body = null; }
    }
    if (!body) return res.writeHead(404).end();
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' }).end(body);
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

/** 照 Worker 的路徑回 fixture；/api/weeks 由那一週的資料推出來（同 tests/js 的 pagedApi）。對不到回 null。 */
function apiBody(url, { reports, week }) {
  const p = url.pathname.slice(new URL(API_BASE).pathname.length);
  if (p === '/hot-topics') return reports;
  if (p === '/weeks') return [{ week_id: week.week_id, article_count: week.article_count }];
  if (p === '/tags') return { ai_tags: {}, user_tags: [] };
  if (p === `/weeks/${week.week_id}`) {
    const offset = Number(url.searchParams.get('offset') || 0);
    const limit = Math.min(Number(url.searchParams.get('limit') || 100), 100);
    return { ...week, articles: week.articles.slice(offset, offset + limit) };
  }
  return null;
}

export async function startHarness() {
  const server = await serve();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  return {
    /** 開一個 width×height 的視窗載入交通頁，等兩條流都畫好、網路靜下來。reports 是 fixtures/ 裡的檔名。 */
    async open({ width, height = 900, reports = 'reports.json' }) {
      const context = await browser.newContext({ viewport: { width, height } });
      const page = await context.newPage();
      const data = { reports: fixture(reports), week: fixture('articles.json') };
      const blocked = [];
      await page.clock.setFixedTime(NOW);
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin === origin) return route.continue();
        if (url.href === NORMALIZE_URL) return route.fulfill({ contentType: 'text/css', body: NORMALIZE_CSS });
        if (url.origin === IMAGE_ORIGIN) return route.fulfill({ contentType: 'image/png', body: PNG_1PX });
        const body = url.href.startsWith(`${API_BASE}/`) ? apiBody(url, data) : null;
        if (body) {
          return route.fulfill({
            contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(body),
          });
        }
        blocked.push(url.href);
        return route.abort();
      });
      await page.goto(`${origin}/`);
      await page.waitForSelector('#batch-nav button', { state: 'attached' });
      await page.waitForSelector('#article-list .traffic-row', { state: 'attached' });
      await page.waitForLoadState('networkidle');
      await page.evaluate(() => document.fonts.ready);
      return { page, blocked, close: () => context.close() };
    },
    async close() {
      await browser.close();
      await new Promise(resolve => server.close(resolve));
    },
  };
}
