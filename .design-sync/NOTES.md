# design-sync notes — garyu-news-scraper

- **Off-script layout（style-foundation）**: `pages/` 是 vanilla 靜態站，無組件庫可打包。手工產出 layout：無 `_ds_bundle.js`（沒有 React 組件）、無 `.jsx`/`.d.ts`。**未產 `_ds_sync.json`**（誠實省略）——下次 sync 沒有 anchor，會全量重驗，屬預期行為。
- **Tokens 真身在 `pages/traffic/index.html` 的 inline `<style>`**（`:root` + `[data-theme="dark"]`），不在 shared.css。ffxiv 的 index.html 可能有差異色票（未查），本次只 sync traffic 的。
- `.stat-all` 樣式也住在 index.html inline style，已併入 `_ds_bundle.css`。
- **中文 class 變體**：`card-高/中/低`、`imp-高/中/低`；但 stat 用英文 `stat-high/mid/low`。conventions 已載明。
- `.collapsed` 是 app.js 加的純狀態標記，CSS 無規則；收合視覺靠 `hidden` 屬性。verify-bundle.mjs 白名單處理。
- `#theme-toggle` 是 id 不是 class。
- 驗證：`node .design-sync/verify-bundle.mjs`（@dsCard 標記、class↔CSS、var()↔tokens、@import closure、conventions 名詞核對）。無 headless browser，未做像素級截圖比對；preview markup 全部取自 production app.js 渲染函式，風險低。
- Preview 內容為手寫假資料（zh-Hant），版式與 class 組合忠於 production。
- `ds-bundle/` 是生成物，已加入 .gitignore。
