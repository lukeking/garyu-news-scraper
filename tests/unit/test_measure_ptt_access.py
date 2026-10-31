"""measure_ptt_access 的判讀句：GNS-016 照最後一行決定停用看板還是換 client，判錯就是做錯決定。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import measure_ptt_access as m  # noqa: E402


def _rows(*pairs):
    return [("biker", name, {"status": status} if status else {"status": None, "error": "x"})
            for name, status in pairs]


def test_all_200_means_not_blocked():
    assert "全部 200，這個出口沒有被擋" in m.verdict(_rows(("prod", 200), ("curl", 200)))


def test_all_403_including_curl_points_to_ip():
    assert "指向 IP 層" in m.verdict(_rows(("prod", 403), ("ua-only", 403), ("curl", 403)))


def test_all_403_without_curl_answer_cannot_separate_ip_from_tls():
    line = m.verdict(_rows(("prod", 403), ("curl", None)))
    assert "分不出擋 IP 還是擋 TLS 指紋" in line
    assert "IP 層" not in line


def test_mixed_lists_the_200_variants():
    line = m.verdict(_rows(("prod", 403), ("curl", 200)))
    assert "跟請求形狀有關" in line and "biker/curl" in line and "biker/prod" not in line


def test_no_response_is_no_measurement():
    assert "沒有量到東西" in m.verdict(_rows(("prod", None), ("curl", None)))
