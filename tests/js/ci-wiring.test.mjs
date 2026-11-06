// spec 017 SC-007：版面測試要在 ruleset 指名的必要檢查 `unit` job 裡跑。讀出貨的 workflow，依序取出 unit job 的 run 指令；
// 只認單行的 `run:`，改成多行區塊時這裡會紅，不會靜靜通過。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const WORKFLOW = fs.readFileSync(path.join(ROOT, '.github', 'workflows', 'tests.yml'), 'utf8');

/** `jobs:` 底下 `<job>:` 那一段（到下一個同層的 job 或頂層 key 為止）的非註解行；找不到 job 回 null。 */
function jobBody(yml, job) {
  const lines = yml.split('\n');
  const jobsAt = lines.findIndex(l => /^jobs:\s*$/.test(l));
  const start = jobsAt < 0 ? -1 : lines.findIndex((l, i) => i > jobsAt && new RegExp(`^  ${job}:\\s*$`).test(l));
  if (start < 0) return null;
  const body = [];
  for (const l of lines.slice(start + 1)) {
    if (/^\s*#/.test(l)) continue;
    if (/^ {0,2}\S/.test(l)) break;
    body.push(l);
  }
  return body;
}
const runsOf = body => body.map(l => l.match(/^\s+(?:-\s+)?run:\s*(.*?)\s*$/)).filter(Boolean).map(m => m[1]);

test('SC-007：unit job 依序跑 npm test、裝 Chromium、npm run test:layout（版面測試在必要檢查裡）', () => {
  const body = jobBody(WORKFLOW, 'unit');
  assert.ok(body, '.github/workflows/tests.yml 找不到 jobs.unit');
  const runs = runsOf(body);
  const wanted = ['npm test', 'npx playwright install --with-deps chromium', 'npm run test:layout'];
  assert.deepEqual(runs.filter(r => wanted.includes(r)), wanted, `unit job 的 run：${runs.join(' | ')}`);
});

test('SC-007：unit job 沒有 if／continue-on-error——步驟被跳過或失敗也算過，版面測試就擋不住 merge', () => {
  const conditional = jobBody(WORKFLOW, 'unit').filter(l => /^\s+(?:-\s+)?(?:if|continue-on-error):/.test(l));
  assert.deepEqual(conditional, [], '要加條件之前先想清楚它會不會讓必要檢查空轉');
});
