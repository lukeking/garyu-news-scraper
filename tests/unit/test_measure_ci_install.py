"""原 BACKLOG GNS-20261105-v4e 的量測層：`scripts/measure_ci_install.py` 從 Actions 的 jobs 回應算出安裝 Chromium 那一步的秒數。
全部離線：jobs 回應是寫死的假資料，不呼叫 gh。"""
import os
import sys

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

import scripts.measure_ci_install as m  # noqa: E402

INSTALL = {"name": m.STEP, "started_at": "2026-11-16T14:37:40Z", "completed_at": "2026-11-16T14:38:10Z", "conclusion": "success"}


def _jobs(step=None, job="unit"):
    steps = [{"name": "Checkout 程式碼", "started_at": "2026-11-16T14:36:50Z", "completed_at": "2026-11-16T14:36:51Z",
              "conclusion": "success"}]
    if step is not None:
        steps.append(step)
    return {"jobs": [{"name": job, "steps": steps}]}


def test_step_seconds_known_answer():
    assert m.step_seconds(_jobs(INSTALL)) == (30.0, "success")


def test_step_name_is_the_one_in_the_workflow():
    """workflow 的步驟改名時這條會紅：腳本對找不到那一步的 run 只列「沒有那一步」，自己不會報錯。"""
    with open(os.path.join(_REPO, ".github", "workflows", m.WORKFLOW), encoding="utf-8") as f:
        assert f"- name: {m.STEP}\n" in f.read()


@pytest.mark.parametrize("payload", [_jobs(), _jobs(INSTALL, job="other"), {"jobs": []}])
def test_missing_step_or_job_is_none_not_zero(payload):
    assert m.step_seconds(payload) is None


def test_step_without_end_time_refuses():
    running = dict(INSTALL, completed_at=None, conclusion=None)
    with pytest.raises(m.MeasureError):
        m.step_seconds(_jobs(running))


def test_skipped_step_is_not_a_measurement():
    """前面的步驟失敗時這一步被跳過，起訖時間相同；算成 0 秒會把中位數往下拉。"""
    skipped = dict(INSTALL, completed_at=INSTALL["started_at"], conclusion="skipped")
    assert m.step_seconds(_jobs(skipped)) == (None, "skipped")


def test_summary_counts_only_measured_runs():
    rows = [{"seconds": 30.0}, {"seconds": 562.0}, {"seconds": 26.0}, {"seconds": None}]
    assert m.summary_line(rows, slow=120) == "量到 3 次（另 1 次沒量到，原因見各列）：中位數 30 秒、最長 562 秒、超過 120 秒 1 次"


def test_summary_refuses_when_nothing_was_measured():
    with pytest.raises(m.MeasureError):
        m.summary_line([{"seconds": None}, {"seconds": None}], slow=120)
