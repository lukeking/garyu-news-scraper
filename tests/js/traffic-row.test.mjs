/**
 * `pages/shared/app.js` 的密集列渲染 — 特徵化測試（characterization tests）。
 *
 * **為什麼現在才有**：本 repo 的 JS 層一直沒有測試 runner（`CLAUDE.local.md` 的表格寫「無」），
 * 而這件事已經被**兩份 spec 明文記下再繞過**（`008/tasks.md:10`、`011/plan.md` 的
 * Complexity Tracking）。BACKLOG #6 的觸發點寫著「第 3 次記下就不要再繞，直接開 spec」，
 * 而 BACKLOG #5（列模型改成 E 響應式）動的正是這個檔案——那會是第 3 次。
 *
 * 這一批不是 #6 的完整解（Storybook / E2E 仍未做），是它的頭期款：
 * 先讓「改動這個渲染器」這件事有紅燈可看。
 *
 * **這些測試描述的是「現在」的行為，不是「應該」的行為。** 其中
 * `test_thumbnail_is_hidden_until_expanded` 描述的正是 BACKLOG #5 要修掉的缺陷——
 * 刻意寫成測試，好讓 E 落地時那個改動是**紅的、看得見的**，而不是靜靜地變了。
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadApp, article } from './harness.mjs';

const app = loadApp();

test('esc 跳脫會破版的字元', () => {
  assert.equal(app.esc('<img src=x onerror="alert(1)">'),
    '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(app.esc(null), '');
});

test('stripHtml 走真正的 DOMParser，不是 regex', () => {
  // 巢狀標籤與實體字元是 regex 版本最容易出錯的地方，用它們證明 harness 真的有 DOM。
  assert.equal(app.stripHtml('<p>前<b>中</b>後</p>'), '前中後');
  assert.equal(app.stripHtml('a &amp; b'), 'a & b');
});

test('articleDisplayState：三種狀態', () => {
  assert.equal(app.articleDisplayState(article()), 'normal');
  assert.equal(app.articleDisplayState({ ...article(), noise_downgrade: true }), 'collapsed');
  // hidden 需要使用者收起該來源，走 localStorage
  app.saveHiddenSources(new Set(['自由時報']));
  assert.equal(app.articleDisplayState({ ...article(), source: '自由時報' }), 'hidden');
  app.saveHiddenSources(new Set());
});

test('★ 與左邊框：高信號突顯不依賴圖片（FR-017）', () => {
  const withStar = app.trafficRow({ ...article(), hot_topic_analyzed: true, image_url: '' }, 1, false);
  assert.match(withStar, /class="[^"]*\btr-strong\b/, '已分析的列要有 tr-strong');
  assert.match(withStar, /tr-badge[^>]*>★/, '已分析的列要有 ★');

  const plain = app.trafficRow(article(), 2, false);
  assert.doesNotMatch(plain, /\btr-strong\b/);
  assert.doesNotMatch(plain, /★/);
});

test('降級列淡化，但不因此拿到 tr-strong', () => {
  const dim = app.trafficRow({ ...article(), hot_topic_analyzed: true }, 1, true);
  assert.match(dim, /\btr-dimmed\b/);
  assert.doesNotMatch(dim, /\btr-strong\b/, 'dimmed 的列不該同時被突顯');
});

test('來源色標用真實的 srcColor / srcLabel', () => {
  const html = app.trafficRow({ ...article(), source: '中時新聞網' }, 1, false);
  assert.match(html, /background:#C0392B/);
  assert.match(html, />中時新聞網</);
  // Google News 的多個 feed 顯示成同一個標籤，但 data-source 必須是原值
  const gn = app.trafficRow({ ...article(), source: 'Google News 機車' }, 1, false);
  assert.match(gn, /data-source="Google News 機車"/);
  assert.match(gn, />Google News</);
});

test('標題回音的 summary 視為無摘要', () => {
  const echo = app.trafficRow({
    ...article(), title: '國道三號連環追撞', summary: '國道三號連環追撞 - 中時新聞網',
  }, 1, false);
  assert.doesNotMatch(echo, /tr-summary/, '只是標題複讀＋來源名，展開沒有東西可看');

  const real = app.trafficRow(article(), 1, false);
  assert.match(real, /tr-summary/);
});

test('E 窄形：每一列都有 40px 方格，有圖放縮圖', () => {
  const html = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);
  const main = html.slice(html.indexOf('class="tr-main"'), html.indexOf('class="tr-detail"'));

  assert.match(main, /class="tr-slot"/, '窄形的左側方格要在掃描區裡');
  assert.match(main, /<img[^>]*src="https:\/\/img\.test\/a\.jpg"/, '有圖就放進方格');
});

test('E 窄形：無圖時方格仍在，用來源色＋縮寫填滿（標題左緣才對得齊）', () => {
  const html = app.trafficRow({ ...article(), source: '中時新聞網', image_url: '' }, 1, false);
  const main = html.slice(html.indexOf('class="tr-main"'), html.indexOf('class="tr-detail"'));

  assert.match(main, /class="tr-slot"[^>]*background:#C0392B/, '無圖時方格用來源色填滿');
  assert.match(main, /tr-slot-label[^>]*>中時新聞網</, '方格裡放來源名縮寫');
  assert.doesNotMatch(main, /<img/, '沒有圖就不該有 img');
});

test('E 寬形：有圖時輸出列尾寬幅條，無圖時完全不輸出（不需要佔位物）', () => {
  const withImg = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);
  assert.match(withImg, /class="tr-strip"[^>]*src="https:\/\/img\.test\/a\.jpg"/);

  const noImg = app.trafficRow({ ...article(), image_url: '' }, 1, false);
  assert.doesNotMatch(noImg, /tr-strip/, '寬形無圖時列自然結束，不放任何佔位物');
});

test('E：兩種形態的元件同時存在於同一份 DOM，由 CSS 決定顯示哪一個', () => {
  // 這是 E 的核心契約：不重複 DOM、不用 JS 判斷寬度。
  // ⚠️ 「CSS 在斷點兩側各自顯示對的那一個」**這個 harness 測不到**（jsdom 無 layout），
  // 那道缺口留給 BACKLOG #6 的 E2E／視覺回歸，已在 PR 內文與 BACKLOG 明記。
  const html = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);
  assert.match(html, /tr-slot/);
  assert.match(html, /tr-strip/);
  assert.doesNotMatch(html, /matchMedia|innerWidth/, '形態切換必須是 CSS 的事，不是 JS 的事');
});

test('E：三種顯示狀態不受影響——tr-detail 仍預設收合且仍帶摘要', () => {
  const html = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);
  assert.match(html, /class="tr-detail" hidden/);
  assert.match(html, /tr-summary/);
});

test('沒有摘要時 tr-detail 裡不放大圖（現況行為，未動）', () => {
  const html = app.trafficRow({
    ...article(), title: 'A', summary: 'A - 來源', image_url: 'https://img.test/a.jpg',
  }, 1, false);
  assert.doesNotMatch(html, /tr-thumb/);
  // 但掃描區的方格與寬幅條不受摘要有無影響
  assert.match(html, /tr-slot/);
  assert.match(html, /tr-strip/);
});

// ── E 把按鈕包深了一層，這幾條守的是「往外找」的處理器還找得到目標 ──────────
//
// 新結構把 .tr-src / ★ / .tr-time / × 移進 .tr-top > .tr-body，比原本深兩層。
// 四個 closest() 都是**往上**走訪所以理論上不受影響——但「理論上」不是證據，
// 而這種斷裂是沉默的（按鈕還在、點了沒反應）。jsdom 測不了 layout，但測得了這個。

test('toggleRow：從包深兩層的標題仍找得到 tr-detail', () => {
  const doc = app.window.document;
  doc.body.innerHTML = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);
  const title = doc.querySelector('.tr-title');
  const detail = doc.querySelector('.tr-detail');

  assert.equal(detail.hidden, true, '預設收合');
  app.window.toggleRow(title);
  assert.equal(detail.hidden, false, '點標題要展開');
  app.window.toggleRow(title);
  assert.equal(detail.hidden, true, '再點要收回去');
});

test('dismissArticle：從包深兩層的 × 仍找得到整張 card', () => {
  const doc = app.window.document;
  // 放進 #article-list —— dismissArticle 尾端的 checkEmptyDismissed() 需要它。
  // （第一版沒有這個容器，測試因 null.querySelectorAll 而紅；那是 fixture 不完整，
  //   不是程式的迴歸。補上之後這條就走完整條路徑，比原本更有價值。）
  doc.body.innerHTML = `<div id="article-list">${app.trafficRow(article(), 1, false)}</div>`;
  const row = doc.querySelector('.traffic-row');
  app.window.dismissArticle(doc.querySelector('.tr-dismiss'));

  assert.equal(row.style.display, 'none', '標記過時要把整列收掉，不是只收掉按鈕那一層');
  assert.ok(doc.getElementById('empty-dismissed-state'), '整頁都收掉時要出現空狀態');
});

test('hideSource：來源按鈕帶的是原值不是顯示值', () => {
  const doc = app.window.document;
  doc.body.innerHTML = app.trafficRow({ ...article(), source: 'Google News 機車' }, 1, false);
  const btn = doc.querySelector('.tr-src');

  assert.equal(btn.dataset.source, 'Google News 機車', '收起的單位是 feed，不是顯示標籤');
  assert.equal(btn.textContent, 'Google News', '顯示的是合併後的標籤');
});
