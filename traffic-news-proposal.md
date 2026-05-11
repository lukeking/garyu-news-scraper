This is a comprehensive development proposal designed for your AI Agent. It details the modular separation of the Traffic and Game news tracks, optimizing for high-value curated content on the traffic side and efficient info-aggregation on the game side, all while keeping Token costs near zero.
------------------------------
## Proposal: Modular News Processing Engine (Traffic Curation & Game Aggregation)## 1. Project Objective
To implement a high-efficiency news deduplication and analysis engine that treats different news categories with tailored logic:

* Traffic News: A weekly "Topic-Curation" model that identifies trends and performs one deep analysis per week.
* Game News: A high-frequency "Information-Streaming" model that focuses on fast deduplication and list generation.

------------------------------
## 2. System Architecture & Coupling Strategy
To maintain code maintainability without bloating Token costs, the system uses a Shared Core with Domain-Specific Pipelines.
## A. The "Decoupled" Pipeline

* Shared Infrastructure: Both tracks share the same Scraper, Database Schema, and Normalization Utils.
* Pipeline Logic:
* GamePipeline (Daily/Real-time): Triggered upon crawl. Uses 100% algorithmic deduplication. LLM: Disabled.
   * TrafficPipeline (Weekly): Crawls daily but "buffers" data. Triggered once every Monday at 08:00 AM for deep analysis. LLM: Batch Analysis.

## B. Coupling Management
The Agent should implement an abstract BaseProcessor class. The coupling is restricted to the Preprocessing Layer, ensuring that improvements in Chinese word segmentation or noise removal benefit both tracks simultaneously.
------------------------------
## 3. Traffic News: Weekly Curation Logic

* Frequency: Weekly (Every Monday at 08:00 AM).
* The "Clustering" Algorithm:
* Primary Tool: Jaccard Similarity.
   * Deduplication Threshold: Score > 0.45 (Merge identical reports).
   * Topic Grouping: Score 0.20 - 0.40. Items in this range are grouped into a "Topic Bucket" (e.g., all news related to "Large Vehicle Blind Spots").
* Selection Mechanism: If multiple reports exist for one event, the system auto-selects the version with the highest word count (maximum info density).
* LLM Integration (Token-Saving Mode):
1. The algorithm identifies the "Top Topic Bucket" of the week.
   2. The Agent extracts only the Titles + 200-character Snippets of the top 5-10 news items in that bucket.
   3. One Single API Call: LLM analyzes the bucket to produce a "Weekly Insight" (Comparing to international standards or simulating community sentiment).

------------------------------
## 4. Game News: Efficient Aggregation Logic

* Frequency: Daily / Real-time.
* Algorithm: Jaccard Similarity + Inclusion Check.
* Logic: If CleanTitle_A is contained within CleanTitle_B, or Jaccard > 0.5, discard the duplicate.
* Output: A clean, chronological list of 20 unique game updates.
* Token Strategy: Zero Token Consumption. All processing is performed locally via Python.

------------------------------
## 5. Technical Specification for the Agent## Step 1: Preprocessing & Normalization (Shared)

* Regex to strip media tags: 【...】, （...）, [... ].
* Remove "Link to..." suffixes and journalist names.
* Convert full-width digits to half-width; convert Chinese numerals to Arabic.
* Entity Protection: Force jieba to keep Road Names and Numerical Facts (e.g., "3 injured", "57-year-old") as single tokens.

## Step 2: Set-Based Deduplication (Shared)

* Algorithm: Jaccard Similarity: Intersection(Set A, Set B) / Union(Set A, Set B).
* Database Search: Use PostgreSQL text[] array with GIN Index for fast intersection queries (&& operator) within a 10-day window (for Weekly support).

## Step 3: Monday Morning Trigger (Traffic Specific)

* At 07:30 AM Monday, the system identifies the largest "Clustered Group."
* Batch send the group summary to the LLM for the "Weekly Special Report."
* Publish the result at 08:00 AM for the Monday morning commute.

------------------------------
## 6. Expected Outcome & Value

   1. Token Efficiency: Game news costs $0. Traffic news costs ~$0.02/week (single batch call).
   2. User Value: Readers receive a high-speed game feed and a high-depth traffic insight every Monday morning.
   3. System Stability: By decoupling the pipelines, a logic change in the "Traffic Special" will not break the "Game List" delivery.

------------------------------
Instruction for the Agent:

"Implement the TrafficAnalysisPipeline as a separate module from the GameNewsPipeline. Ensure the Jaccard logic is centralized but utilizes different thresholds for each. Prioritize local algorithmic deduplication to keep API costs at a minimum. The Traffic LLM analysis must only trigger once per week using a batch of summaries."

「這是一份完整的系統規格。請分步驟 (Step-by-step) 實作。我們先處理資料預處理與 Jaccard 模組，完成並通過 Unit Test 後，再進行資料庫層與自動化排程的整合。」