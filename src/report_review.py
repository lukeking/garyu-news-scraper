"""report_review.py：週報審稿的純函式，只有標題的判定與報告的機械檢查。
介面與檢查名照 specs/018-prepublish-review/contracts/check-report.md；不碰網路、資料庫與檔案。
"""
import re
import unicodedata

BOILERPLATE = (
    "0則貼文 | 快來參與LINE TODAY討論牆上的討論 |",
    "台視影音：提供台視最新的綜藝、專題、節目預告及新聞影音，並有數個完整影音節目，供網友選擇收看。",
)
TITLE_ONLY_MIN_CHARS = 20
DELETION_CAP = 0.30
SC001_CHECKS = ("independence_claim", "date_unlabeled", "self_count", "title_only_in_sections")

TEMPLATES = ("digest", "hot")
DIGEST_HEADINGS = ("### 本期概覽", "### 分節彙整", "### 待追蹤")
TITLE_ONLY_HEADING = "### 僅標題"
HOT_HEADINGS = ("### 一、", "### 二、", "### 三、")
INDEPENDENCE_WORDS = ("互相獨立", "無直接因果", "各自獨立")
REPORT_LABEL = "報導"
REPORT_LABEL_WINDOW = 10

_BRACKET = re.compile(r"\[([^\[\]]*)\]")
_ID_LIST = re.compile(r"\s*\d+(?:\s*[,，、]\s*\d+)*\s*")
_SELF_COUNT = re.compile(r"(?:本期)?共[^，。；\n]{0,8}?\d[\d,]*\s*[起個][^，。；\n]{0,8}?事件")
_DATE = re.compile(r"(?<!\d)(?:\d{2,4}\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_INTERWEAVE = re.compile(r"交織度分布[：:](.*)")
_PIECES = re.compile(r"(\d+)\s*篇")


def _normalise(text: str) -> str:
    """NFKC、小寫，去掉標點（P*）、分隔符（Z*）與空白。"""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return "".join(c for c in text if not c.isspace() and unicodedata.category(c)[0] not in "PZ")


_BOILERPLATE_NORMALISED = tuple(_normalise(b) for b in BOILERPLATE)


def is_title_only(title: str, summary: str) -> bool:
    s = _normalise(summary)
    for b in _BOILERPLATE_NORMALISED:
        s = s.replace(b, "")
    if not s:
        return True
    titles = {title or ""}
    if " - " in (title or ""):
        titles.add(title.rsplit(" - ", 1)[0])
    for t in (_normalise(x) for x in titles):
        if s in t or len(s.replace(t, "")) < TITLE_ONLY_MIN_CHARS:
            return True
    return False


def _unique(items) -> list:
    out = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


def _ids(text: str) -> list:
    """方括號裡的編號；[6, 8, 15] 逐一拆開，[工程主導] 這類非數字括號略過。"""
    out = []
    for m in _BRACKET.finditer(text):
        if _ID_LIST.fullmatch(m.group(1)):
            out += [int(n) for n in re.findall(r"\d+", m.group(1))]
    return out


def _section(text: str, heading: str) -> str:
    """從 heading 那一行之後，到下一個以「### 」開頭的行為止（#### 子節不算結束）。"""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("### "):
            inside = line.startswith(heading)
        elif inside:
            out.append(line)
    return "\n".join(out)


def _missing(text: str, headings) -> list:
    lines = text.splitlines()
    return [h for h in headings if not any(line.startswith(h) for line in lines)]


def _date_unlabeled(text: str, sources) -> list:
    corpus = ["".join((s.get(k) or "").split()) for s in sources for k in ("title", "summary")]
    hits = []
    for m in _DATE.finditer(text):
        if REPORT_LABEL in text[m.end():m.end() + REPORT_LABEL_WINDOW]:
            continue
        month, day = int(m.group(1)), int(m.group(2))
        evidence = re.compile(rf"(?<!\d)0?{month}月0?{day}日|(?<!\d)0?{month}/0?{day}(?!\d)")
        if not any(evidence.search(c) for c in corpus):
            hits.append(m.group(0))
    return _unique(hits)


def _interweave_sum(text: str, total: int) -> list:
    hits = []
    for line in text.splitlines():
        m = _INTERWEAVE.search(line)
        counts = [int(n) for n in _PIECES.findall(m.group(1))] if m else []
        if counts and sum(counts) != total:
            hits.append("+".join(map(str, counts)) + f"={sum(counts)}≠{total}")
    return hits


def _numbers(text: str) -> list:
    return [m.group(0) for m in _NUMBER.finditer(unicodedata.normalize("NFKC", text or ""))]


def _new_numbers(replacements, sources) -> list:
    known = {n.replace(",", "") for s in sources for k in ("title", "summary") for n in _numbers(s.get(k))}
    hits = []
    for quote, replacement in replacements:
        allowed = known | {n.replace(",", "") for n in _numbers(quote)}
        hits += [n for n in _numbers(replacement) if n.replace(",", "") not in allowed]
    return _unique(hits)


def _deletion_over_cap(replacements, original_text) -> list:
    if not replacements:
        return []
    ratio = sum(max(0, len(q) - len(r)) for q, r in replacements) / len(original_text)
    return [f"{ratio * 100:.1f}%"] if ratio > DELETION_CAP else []


def _text_checks(text: str, template: str, sources, title_only_ids) -> dict:
    n = len(sources)
    result = {
        "missing_section": _missing(text, HOT_HEADINGS if template == "hot" else
                                    DIGEST_HEADINGS + ((TITLE_ONLY_HEADING,) if title_only_ids else ())),
        "id_out_of_range": _unique(f"[{i}]" for i in _ids(text) if not 1 <= i <= n),
    }
    if template == "hot":
        result["interweave_sum"] = _interweave_sum(text, n)
        return result
    title_only = set(title_only_ids)
    result["title_only_in_sections"] = _unique(
        f"[{i}]" for i in _ids(_section(text, "### 分節彙整")) if i in title_only)
    result["self_count"] = _unique(m.group(0) for m in _SELF_COUNT.finditer(_section(text, "### 本期概覽")))
    result["independence_claim"] = [w for w in INDEPENDENCE_WORDS if w in text]
    result["date_unlabeled"] = _date_unlabeled(text, sources)
    return result


def check_report(report_text, *, template, sources, title_only_ids=(), original_text=None,
                 replacements=()) -> dict:
    """回傳檢查名 → 命中字串；給了 original_text 就只留原稿沒有的命中（同一檢查名內比字串）。"""
    if template not in TEMPLATES:
        raise ValueError(f"template 只能是 digest 或 hot：{template!r}")
    if replacements and not original_text:
        raise ValueError("給了 replacements 就要給 original_text")
    result = _text_checks(report_text, template, sources, title_only_ids)
    if original_text is not None:
        before = _text_checks(original_text, template, sources, title_only_ids)
        result = {k: [h for h in v if h not in before[k]] for k, v in result.items()}
    result["replacement_new_number"] = _new_numbers(replacements, sources)
    result["deletion_over_cap"] = _deletion_over_cap(replacements, original_text)
    return result
