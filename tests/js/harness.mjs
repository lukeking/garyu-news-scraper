/**
 * 把 `pages/shared/app.js` 載進 jsdom，取出可測的函式。
 *
 * **為什麼是這個形狀**：`app.js` 是部署到 Cloudflare Pages 的**全域腳本**
 * （`<script src="app.js">`，沒有 export）。為了讓它可測而把它改成 ESM，等於為了測試
 * 去改被測物的形狀——所以這裡反過來，讓 harness 去配合它：讀原始檔、在 jsdom 裡求值。
 * **被測的是真正出貨的那份位元組。**
 *
 * jsdom 是唯一的依賴，因為 `stripHtml()` 用的是 `DOMParser`。用 regex 假造一個 HTML
 * parser 會讓測試跑在一份行為不同的副本上（實體字元、巢狀標籤都不一樣），那種測試
 * 通過了也不代表什麼。替換邊界可以，替換邏輯不行。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = path.join(HERE, '..', '..', 'pages', 'shared', 'app.js');

/** 與 pages/traffic/index.html 的 SITE_CONFIG 同形（只放被測函式真的會讀的欄位）。 */
export const TRAFFIC_CONFIG = {
  contentType: 'traffic',
  shareToLine: true,
  dismissedKey: 'dismissed-traffic',
  sourceColors: {
    'Google News': '#4285F4', 'PTT/biker': '#FF4500', '聯合新聞網': '#1A3C6E',
    '中時新聞網': '#C0392B', '自由時報': '#27AE60', 'TVBS新聞': '#2980B9',
  },
  srcColor(s) { return this.sourceColors[s] || (s.startsWith('Google News') ? '#4285F4' : '#555'); },
  srcLabel: s => s.startsWith('Google News') ? 'Google News' : s,
};

const EXPORTED = [
  'esc', 'stripHtml', 'relativeTime', 'articleDisplayState', 'trafficRow',
  'isSourceHidden', 'getHiddenSources', 'saveHiddenSources',
];

export function loadApp(config = TRAFFIC_CONFIG) {
  const raw = fs.readFileSync(APP_JS, 'utf8');

  // app.js 結尾會自己呼叫 init()，那會發網路請求。測試只要純函式，所以拿掉那一行。
  // ⚠️ 拿不掉就直接 throw：若 app.js 改了結尾形狀而這裡沒跟上，init() 會在測試裡
  // 靜靜地跑起來，而「靜靜地跑起來」正是最難發現的那種失敗。
  const src = raw.replace(/\ninit\(\);\s*$/, '\n');
  if (src === raw) {
    throw new Error('harness 過期：app.js 的結尾不再是 `init();`，請確認新的啟動點再更新這裡');
  }

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://garyu.test/',          // localStorage 需要 http(s) origin
    runScripts: 'outside-only',
  });
  dom.window.SITE_CONFIG = config;
  dom.window.__API_BASE__ = '/api';
  dom.window.fetch = () => Promise.reject(new Error('測試不該打網路'));

  dom.window.eval(`${src}\nwindow.__exports = { ${EXPORTED.join(', ')} };`);
  const api = dom.window.__exports;
  const missing = EXPORTED.filter(n => typeof api[n] !== 'function');
  if (missing.length) throw new Error(`app.js 沒有這些函式了：${missing.join(', ')}`);
  return { ...api, window: dom.window };
}

/** 一篇最小的 traffic 文章；欄位名與 `articles` 表一致。 */
export function article(over = {}) {
  return {
    title: '國道三號連環追撞 3 人輕傷',
    link: 'https://example.test/a1',
    source: 'Google News 機車',
    published: new Date(Date.now() - 3600 * 1000).toISOString(),
    summary: '警方表示，事故發生於今日上午，初步研判為未保持安全距離所致，詳細肇因仍在調查中。',
    image_url: '',
    hot_topic_analyzed: false,
    ...over,
  };
}
