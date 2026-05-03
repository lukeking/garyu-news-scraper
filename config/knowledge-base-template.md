# FFXIV Knowledge Base Template (V1.0)
*此文件為 Agent 擴展知識庫時必須遵循的抽象格式。*

## 1. 術語定義格式 (Glossary Entry Format)
所有新增術語必須包含以下欄位，以確保多語系定錨：

```markdown
### [中文統一術語]
- **EN**: [English Term]
- **JP**: [日本語用語]
- **Category**: [Job / Skill / System / Zone]
- **Description**: [簡短的功能描述，用於 AI 摘要時的背景參考]
- **Source**: [來源 URL 或 Wiki 連結]
```

## 2. 職業縮寫規範
- 輸出週報時，優先使用「中文名稱 (縮寫)」格式。
- 例如：`吟遊詩人 (BRD)`, `武僧 (MNK)`。

## 3. 數據定錨原則
- **Potency (威力)**: 必須保留數值變化（例如：500 -> 520）。
- **Cooldown (冷卻時間)**: 統一使用「秒」作為單位。

## 4. 排除詞彙清單 (Exclusion Filter)
Agent 在摘要時應主動過濾以下無意義內容：
- 社交辭令 (如：お疲れ様です, 感謝開發組)
- 非技術性的玩家抱怨或情緒抒發。
```

---
*維護提醒：Agent 發現缺漏並完成檢索後，應依照此格式附加於 knowledge-base.md 末尾。*
