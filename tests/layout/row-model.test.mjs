// spec 017 SC-007、BACKLOG GNS-006：列模型的兩個常數（`@container trlist (min-width: 560px)`、`.tr-time` 的 5em）在 Chromium 上量。
// CSS 文字的守門員在 tests/js/row-model-css.test.mjs；這裡證明的是斷點兩側畫出對的形態、時間欄放得下。
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startHarness } from './harness.mjs';

let h;
before(async () => { h = await startHarness(); });
after(() => h.close());

/** 開頁面、切到新文章那一條（窄螢幕一次一條）、在頁面裡跑 measure，確認沒有沒準備的外部請求後關掉。 */
async function measureArticles(width, measure) {
  const v = await h.open({ width });
  try {
    await v.page.click('#tab-articles');
    const m = await v.page.evaluate(measure);
    assert.deepEqual(v.blocked, [], '頁面要了 harness 沒準備的外部資源');
    return m;
  } finally {
    await v.close();
  }
}

const rows = () => {
  const list = document.querySelector('#article-list .tr-group-body');
  return {
    listWidth: list.getBoundingClientRect().width,
    rows: Array.from(list.querySelectorAll('.traffic-row'), row => {
      const time = row.querySelector('.tr-time');
      const text = document.createRange();
      text.selectNodeContents(time);
      return {
        slotShown: row.querySelector('.tr-slot').checkVisibility(),
        time: time.textContent,
        textWidth: text.getBoundingClientRect().width,
        columnWidth: parseFloat(getComputedStyle(time).minWidth),
        stripLeft: row.querySelector('.tr-strip')?.getBoundingClientRect().left ?? null,
      };
    }),
  };
};

for (const [width, listWidth, slotShown] of [[591, 559, true], [592, 560, false]]) {
  test(`560px：視窗 ${width} px（文章列表 ${listWidth} px）時 .tr-slot ${slotShown ? '顯示（窄形）' : '藏起（寬形）'}`, async () => {
    const m = await measureArticles(width, rows);
    assert.equal(m.listWidth, listWidth, '前提：文章列表＝視窗 − .main 左右 padding 各 16');
    assert.equal(m.rows.length, 4, '前提：fixture 的 4 篇都畫出來了');
    assert.deepEqual(m.rows.map(r => r.slotShown), m.rows.map(() => slotShown));
  });
}

test('5em：寬形裡時間是「10 分鐘前」的列，.tr-time 不溢出時間欄（在 CI 的字型下）', async () => {
  const m = await measureArticles(900, rows);
  assert.ok(m.rows.every(r => !r.slotShown), '前提：視窗 900 px 是寬形');
  const widest = m.rows.find(r => r.time === '10 分鐘前');
  assert.ok(widest, `前提：有一列的時間是「10 分鐘前」：${m.rows.map(r => r.time).join('、')}`);
  assert.ok(widest.textWidth <= widest.columnWidth,
    `「10 分鐘前」寬 ${widest.textWidth}px，時間欄（min-width）只有 ${widest.columnWidth}px`);
});

test('5em：寬形裡時間字串不同的列，寬幅條左緣 x 相同', async () => {
  const m = await measureArticles(900, rows);
  assert.ok(m.rows.every(r => !r.slotShown), '前提：視窗 900 px 是寬形');
  assert.equal(new Set(m.rows.map(r => r.time)).size, 4, `前提：4 列的時間字串都不同：${m.rows.map(r => r.time).join('、')}`);
  assert.ok(m.rows.every(r => r.stripLeft !== null), '前提：每列都有寬幅條（圖載得到）');
  const lefts = m.rows.map(r => `${r.time} ${r.stripLeft}`);
  assert.equal(new Set(m.rows.map(r => r.stripLeft)).size, 1, `寬幅條左緣不齊：${lefts.join('、')}`);
});
