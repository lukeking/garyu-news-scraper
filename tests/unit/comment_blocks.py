"""抽出註解／docstring 區塊。Python 用 tokenize+ast，JS/MJS 用行首掃描（近似）。"""
import ast
import io
import os
import subprocess
import tokenize

# 政策排除：已封存的 A/B 實驗碼，不再維護，故不納入預算。
SKIP_PREFIXES = ("experiments/",)
EXTS = (".py", ".js", ".mjs")


def _python(path):
    src = io.open(path, encoding="utf-8").read()
    out, run = [], []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return out
    for t in toks:
        if t.type == tokenize.COMMENT:
            if run and t.start[0] == run[-1] + 1:
                run.append(t.start[0])
            else:
                if run:
                    out.append((run[0], len(run)))
                run = [t.start[0]]
        elif t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            if run:
                out.append((run[0], len(run)))
                run = []
    if run:
        out.append((run[0], len(run)))
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            e = node.body[0]
            out.append((e.lineno, (e.end_lineno or e.lineno) - e.lineno + 1))
    return out


def _js(path):
    out, cur, start, inblk = [], 0, 0, False
    for i, line in enumerate(io.open(path, encoding="utf-8").read().splitlines(), 1):
        s = line.strip()
        if inblk:
            hit = True
            if "*/" in s:
                inblk = False
        elif s.startswith("/*"):
            hit, inblk = True, "*/" not in s
        else:
            hit = s.startswith("//")
        if hit:
            if not cur:
                start = i
            cur += 1
        elif cur:
            out.append((start, cur))
            cur = 0
    if cur:
        out.append((start, cur))
    return out


def blocks_for(path):
    """回傳 [(起始行, 行數)]。"""
    return _python(path) if path.endswith(".py") else _js(path)


def tracked(root):
    """已版控的原始碼清單。取自 git 而非磁碟，否則本機的 gitignored 產物（symlink、
    暫存檔）會進債務表，讓同一份 LEGACY 在本機與 CI 算出不同答案。
    """
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(
        p for p in out.split("\0")
        if p.endswith(EXTS) and not p.startswith(SKIP_PREFIXES)
    )


def walk(root):
    """回傳 {相對路徑: [(起始行, 行數)]}，只含至少有一個區塊的檔案。"""
    found = {}
    for rel in tracked(root):
        try:
            b = blocks_for(os.path.join(root, rel))
        except (UnicodeDecodeError, OSError):
            continue
        if b:
            found[rel] = b
    return found
