# cold review：這個 repo 的權威順序與硬邊界

`~/.agents/bin/render_cold_review_prompt.py` 把下面兩節的內文原樣填進 reviewer prompt（模板是
`~/.agents/skills/cold-review/reviewer-prompt.md`），讀的是受審範圍 base 那一版，所以 PR 改不到審自己的這份契約。
這裡只寫每一輪都成立的內容；某個 PR 刻意的改動、哪些不算 finding，寫進那一輪的「來由」。
只能有這兩個 `##` 節，多一節或少一節腳本都會拒絕；內文不要有角括號佔位字，會被當成沒填。

## 權威順序

.specify/memory/constitution.md 是本 repo 的規則，效力高於其他開發慣例（憲章 Governance）；衝突時以憲章為準，或先修訂憲章。憲章只寫意圖與結構性選擇，會浮動的值（模型、排程、門檻、來源）住在設定與執行它們的地方。.specify/templates/plan-template.md 是 /speckit-plan 產出 plan 時優先讀的本專案範本；其餘 spec-kit 程序與範本在 user 層，不在本 repo。routines/weekly-verify/ 是週報驗收 cloud routine 的程序：PROMPT.md 是常設指示，FOCUS-CHECK.md 是週三的過期檢查，兩者執行時從 main 讀，改它們就是改 routine 的行為；FOCUS.md 是每週更新的本週重點，README.md 寫給維護者（怎麼滾 FOCUS、怎麼重建 routine）。docs/standing-cautions.md 是常設提醒，動到某一塊之前要先知道的事。specs/BACKLOG.md 是待辦紀錄（只列還沒做完的條目，完成就移出）。specs/ 下每個 feature 目錄是設計與狀態紀錄，不是工作方式的規則。CLAUDE.md 只指向當前的 plan。config/ 下的 example 檔是 GitHub production environment variables 的鏡像，正式設定的真身在 GitHub。

## 硬邊界

handle-secrets 禁止讀取或引用憑證；只讀此 checkout 在 head 的 tracked 檔案；不寫入、不連網、不用 MCP、不委派。CLAUDE.local.md、HANDOFF.md（都不進版控）、memory 檔（~/.claude/projects/*/memory/）、user 層的 spec-kit、規則與 skills、個人 runtime 與 settings.json、GitHub 上的 environment variables、Linear 與 Supabase 的資料都不在來源內，讀不到不構成 finding。整合測試會寫入資料，只能指向本機 Supabase（tests/integration/conftest.py 對非本機主機 fail closed），這是資料安全邊界，不是風格偏好。
