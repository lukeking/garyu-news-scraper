/**
 * `pages/shared/shared.css` 的**結構**守門員。
 *
 * ⚠️ **這一批不證明 CSS 渲染正確。** jsdom 沒有 layout（`clientWidth` / `scrollWidth`
 * 永遠是 0），所以「斷點兩側各自顯示對的那一個形態」在這個 harness 裡**測不到**。
 * 那道缺口要 E2E／視覺回歸才補得起來，屬於 BACKLOG #6 的完整解，本輪未做。
 *
 * 這裡守的是一件比較窄、但真的會發生的事：**有人在「簡化 CSS」時把其中一個形態
 * 整段刪掉**。列模型 E 的兩種形態互為對方的隱形依賴——刪掉寬形不會有任何錯誤，
 * 只是桌機悄悄變回手機版面。這幾條讓那個刪除變成紅燈。
 */
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
