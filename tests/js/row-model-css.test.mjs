// `pages/shared/shared.css` 的結構守門員：擋「簡化 CSS 時把其中一個形態整段刪掉」。
// 兩形態互為隱形依賴——刪掉寬形不報錯，只是桌機悄悄變回手機版面。
// ⚠️ 不證明渲染正確：jsdom 無 layout，斷點兩側顯示對的形態測不到（BACKLOG #6）。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const CSS = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'pages', 'shared', 'shared.css'),
  'utf8',
);

/** 取出 `@container trlist (...) { ... }` 的內容（大括號配對，不用 regex 硬吞）。 */
function containerBlock() {
  const at = CSS.indexOf('@container trlist');
  if (at < 0) return null;
  let i = CSS.indexOf('{', at), depth = 0;
  for (let j = i; j < CSS.length; j++) {
    if (CSS[j] === '{') depth++;
    else if (CSS[j] === '}' && --depth === 0) return CSS.slice(i + 1, j);
  }
  return null;
}

test('窄形（預設）：方格與兩行標題都有宣告', () => {
  assert.match(CSS, /\.tr-slot\s*\{[^}]*width:\s*40px/, '方格是 40px');
  assert.match(CSS, /\.tr-title\s*\{[^}]*-webkit-line-clamp:\s*2/, '窄形標題夾兩行');
  assert.match(CSS, /\.tr-strip\s*\{\s*display:\s*none/, '窄形不顯示寬幅條');
});

test('寬形：@container 區塊存在，且斷點是清單寬度 560px', () => {
  const block = containerBlock();
  assert.ok(block, '@container trlist 區塊不見了 → 桌機會悄悄退回手機版面');
  assert.match(CSS, /@container trlist \(min-width:\s*560px\)/,
    '斷點改了就要同步更新 BACKLOG #5（那裡記著 560 是推導、待實測）');
});

test('寬形：方格收起、寬幅條展開、標題改回單行——三件事缺一不可', () => {
  const block = containerBlock();
  assert.match(block, /\.tr-slot\s*\{\s*display:\s*none/, '寬形要收起方格');
  assert.match(block, /\.tr-strip\s*\{[^}]*display:\s*block/, '寬形要展開寬幅條');
  assert.match(block, /\.tr-title\s*\{[^}]*white-space:\s*nowrap/, '寬形標題改回單行');
});

test('寬形靠 display:contents ＋ order 排版，不靠第二份 DOM', () => {
  const block = containerBlock();
  assert.match(block, /\.tr-body,\s*\.tr-top\s*\{\s*display:\s*contents/);
  for (const [sel, ord] of [['tr-src', 1], ['tr-badge', 2], ['tr-title', 3],
                            ['tr-strip', 4], ['tr-time', 5], ['tr-dismiss', 6]]) {
    assert.match(block, new RegExp(`\\.${sel}\\s*\\{[^}]*order:\\s*${ord}`),
      `${sel} 的 order 不對——順序錯了會讓寬幅條跑到時間後面`);
  }
});

test('容器本身有宣告 container-type，否則 @container 永遠不會生效', () => {
  // 「宣告了查詢卻沒有容器」是這個功能最典型的沉默失敗：不報錯，只是永遠不套用。
  assert.match(CSS, /\.tr-group-body\s*\{[^}]*container-type:\s*inline-size/);
  assert.match(CSS, /\.tr-group-body\s*\{[^}]*container-name:\s*trlist/);
});

test('寬形：時間欄有寬度下界，否則寬幅條會被時間文字推著左右跑', () => {
  // .tr-time 貼著內容，而 Intl.RelativeTimeFormat 的字串跟瀏覽器 locale 走
  // （英文光 "yesterday" 到 "10 minutes ago" 就差 5 個字元）。
  const block = containerBlock();
  assert.match(block, /\.tr-time\s*\{[^}]*min-width:/, '沒有下界，寬幅條就會逐列漂移');
  assert.match(block, /\.tr-time\s*\{[^}]*text-align:\s*right/, '欄變寬後文字要靠右貼齊 ×');
});

test('方格是定位脈絡，否則疊在它上面的圖會跑掉', () => {
  // 圖疊在來源色塊上，載入失敗時移掉 img 就露出色塊——這靠的是 relative/absolute 這一對。
  assert.match(CSS, /\.tr-slot\s*\{[^}]*position:\s*relative/);
  assert.match(CSS, /\.tr-slot img\s*\{[^}]*position:\s*absolute/);
});
