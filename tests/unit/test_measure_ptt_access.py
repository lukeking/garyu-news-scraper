"""measure_ptt_access 的判讀句：GNS-016 照最後一行決定停用看板還是換 client，判錯就是做錯決定。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import measure_ptt_access as m  # noqa: E402

CHALLENGE = {"Cf-Mitigated": "challenge"}


def _r(status, headers=None):
    return {"status": status, "headers": headers or {}} if status else {"status": None, "error": "x"}


def _rows(*pairs, control=None):
    rows = [("biker", p[0], _r(p[1], p[2] if len(p) > 2 else None)) for p in pairs]
    if control is not None:
        rows.append((m.CONTROL, "ua-only", _r(control)))
    return rows


def test_all_200_means_not_blocked():
    assert "全部 200，這個出口沒有被擋" in m.verdict(_rows(("prod", 200), ("curl", 200)))


def test_all_403_including_curl_points_to_ip():
    assert "指向 IP 層" in m.verdict(_rows(("prod", 403), ("ua-only", 403), ("curl", 403)))


def test_actions_2026_10_31_boards_challenged_robots_cached_200():
    """Actions run 41165997831：看板全部 403＋cf-mitigated: challenge，robots.txt 從快取回 200。"""
    line = m.verdict(_rows(("prod", 403, CHALLENGE), ("curl", 403, {"cf-mitigated": "challenge"}), control=200))
    assert "指向 IP 層" in line and "Cloudflare challenge" in line and "對照：robots.txt 200" in line
    assert "跟請求形狀有關" not in line


def test_all_403_without_curl_answer_cannot_separate_ip_from_tls():
    line = m.verdict(_rows(("prod", 403), ("curl", None)))
    assert "分不出擋 IP 還是擋 TLS 指紋" in line
    assert "IP 層" not in line


def test_mixed_lists_the_200_variants():
    line = m.verdict(_rows(("prod", 403), ("curl", 200)))
    assert "跟請求形狀有關" in line and "biker/curl" in line and "biker/prod" not in line


def test_no_response_is_no_measurement():
    assert "沒有量到東西" in m.verdict(_rows(("prod", None), ("curl", None), control=200))
