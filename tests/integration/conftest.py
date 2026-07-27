"""整合測試的安全閘：強制指向本機測試庫，永遠不碰正式環境。

為什麼存在
----------
2026-07-21，這些測試在 `.env` 有正式憑證的環境下被執行，直接寫進**正式** Supabase
的 articles 表，插進 16 列（`2025-W01-test` 等 week_id、`example.com` 連結）。
汙染不只停在資料表：`scripts/measure_source_uptake.py` 把它們納入統計，baseline 由
0.1954 位移到 0.1914，每個來源倍率跟著偏，依此設定的 prod 變數 `SOURCE_UPTAKE_JSON`
整份是錯的，必須重設。

當時**沒有任何東西擋下來，也沒有任何提示**告訴執行者這件事正在發生。
這個檔案就是那個「任何東西」。

設計原則：預設要安全，不能靠執行者記得。所以這裡是**強制覆寫**連線設定，
而不是「偵測到正式環境就提醒」——提醒可以被忽略，覆寫不行。
"""
import os
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEST_ENV = os.path.join(_REPO_ROOT, ".env.test.local")

# 只有這些主機被認定為「本機」。任何其他值都代表測試即將寫進別人的資料庫。
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

# 被覆寫的變數。三個都要蓋：storage.supabase_api_key() 會依序看
# SUPABASE_SERVICE_ROLE_KEY 再看 SUPABASE_KEY，只蓋其中一個會留下後門。
_OVERRIDDEN = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY")

_SETUP_HINT = (
    "整合測試需要本機 Supabase。請執行：\n"
    "    npx supabase start          # 本 repo 的 stack（API 54331 / DB 54332）\n"
    "    bash scripts/setup_test_db.sh\n"
    "設定會寫進 .env.test.local。"
)


# ── 覆寫必須發生在「模組載入時」，不能等到 fixture ────────────────────────────
# pytest 先 import 同目錄的 conftest，才 import 各測試模組。而測試模組的 import
# 本身就可能注入正式憑證——test_digest_weekly.py 已經有一份手工防線，它 exec
# scripts/traffic_weekly_analysis.py 之前先把 dotenv.load_dotenv 換成 no-op，
# 註解寫著「那會把真實憑證注入整個 pytest 程序」。那是對的，但只補了一個檔。
#
# 在這裡先把環境變數設定好，就能一次蓋住所有檔案：python-dotenv 的
# load_dotenv() 預設 override=False，既有的值不會被覆寫。也就是說只要我們搶先，
# 之後任何模組怎麼 load_dotenv() 都拿不回控制權。
_saved_env = {k: os.environ.get(k) for k in _OVERRIDDEN}
load_dotenv(_TEST_ENV, override=True)
_TEST_URL = (os.environ.get("SUPABASE_TEST_URL") or "").strip()
_TEST_KEY = (os.environ.get("SUPABASE_TEST_SERVICE_ROLE_KEY") or "").strip()

if _TEST_URL and _TEST_KEY and urlparse(_TEST_URL).hostname in _LOCAL_HOSTS:
    os.environ["SUPABASE_URL"] = _TEST_URL
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = _TEST_KEY
    os.environ["SUPABASE_KEY"] = _TEST_KEY

# ── 同樣手法擋掉線上 LLM ────────────────────────────────────────────────────
# `pytest tests`（unit + integration 一起跑）會經由 tests/unit/test_source_uptake.py
# → scripts/measure_source_uptake.py 的模組層 load_dotenv(".env") 把真實憑證灌進
# 整個 pytest 程序。test_weekly_analysis.py 的 skip 閘門看的是 GEMINI_API_KEY，
# 一旦被灌進來它就解除 skip，去打真的 Gemini API——實測會直接卡住不返回，
# 而且花的是真的配額。（這個坑在本次改動之前就存在，不是新引入的。）
#
# 設成空字串而不是 pop：load_dotenv(override=False) 判斷的是「鍵在不在」，
# 空字串一樣算存在，所以能擋掉後續注入；而閘門用 .strip() 檢查，空字串會正確 skip。
_ALLOW_LIVE_LLM = (os.environ.get("GARYU_ALLOW_LIVE_LLM") or "").strip() == "1"
if not _ALLOW_LIVE_LLM:
    _saved_env["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = ""


def _reset_storage_client():
    """清掉 src.storage 的 module-global client 快取。

    `_client` 是 lazy init 之後就一直被重用的全域變數。如果在覆寫環境變數之前
    有任何程式碼先建立過 client（例如另一個測試、或 import 時的副作用），
    那個指向正式環境的 client 會活過我們的覆寫。所以前後都要清。
    """
    import src.storage
    src.storage._client = None


@pytest.fixture(autouse=True, scope="session")
def force_local_supabase():
    """把整個整合測試 session 釘在本機測試庫上。

    真正的覆寫已經在模組載入時做完（見上）。這裡負責三件事：
    設定缺失時明確 skip、指向非本機時 fail、以及跑完的清理與環境還原。
    """
    url, key = _TEST_URL, _TEST_KEY

    if not url or not key:
        # 這裡 skip 而不是 fail：沒有本機 stack 的環境（例如只想跑 unit 的人）
        # 不該被整個測試套件擋住。真正危險的是「連上正式環境」，那條在下面 fail。
        # 註：整合測試刻意不進 CI，所以這個 skip 不會變成 CI 的假綠燈——
        # 見 .github/workflows/tests.yml 的說明與 specs/BACKLOG.md「CI gating」L2。
        pytest.skip(f"未設定本機測試庫。\n{_SETUP_HINT}", allow_module_level=True)

    host = urlparse(url).hostname
    if host not in _LOCAL_HOSTS:
        pytest.fail(
            f"SUPABASE_TEST_URL 指向非本機主機 `{host}`。\n"
            "整合測試會寫入資料，只允許指向本機（見本檔開頭：2026-07-21 的正式庫汙染事件）。\n"
            "若真的要改變這條規則，請連同 conftest 的 _LOCAL_HOSTS 一起改，"
            "並在 specs/BACKLOG.md 記錄理由——不要只改這一行。",
            pytrace=False,
        )

    # 環境變數在模組載入時就已覆寫，這裡只需要確保 client 沒有帶著舊設定活過來。
    _reset_storage_client()

    yield

    _cleanup_test_rows()
    # 還原成「conftest 載入之前」的值——不是覆寫後的值，所以用模組層存的 _saved_env。
    for k, v in _saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset_storage_client()


def _cleanup_test_rows():
    """刪掉測試造出來的列，讓重複執行不會互相干擾。

    只在本機庫執行——上面的 fixture 已經驗證過主機是 localhost 才會走到這裡。
    測試資料的辨識特徵是 week_id 帶 `-test` 尾碼（`2025-W01-test` 等），
    與 `scripts/measure_source_uptake.py` 的 ISO_WEEK 過濾用的是同一個特徵。
    """
    try:
        from src.storage import _get_client
        client = _get_client()
        client.table("articles").delete().like("week_id", "%-test").execute()
    except Exception as e:  # 清理失敗不該讓測試結果變紅
        print(f"\n[conftest] 測試資料清理失敗（不影響測試結果）：{e}")
