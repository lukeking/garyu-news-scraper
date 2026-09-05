"""抽出註解／docstring 區塊。Python 用 tokenize+ast，JS/MJS 用行首掃描（近似）。"""
import ast
import io
import os
import tokenize

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "data", "experiments", ".claude", "__pycache__"}
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


def walk(root):
    """回傳 {相對路徑: [(起始行, 行數)]}，只含至少有一個區塊的檔案。"""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(EXTS):
                continue
            full = os.path.join(dirpath, name)
            try:
                b = blocks_for(full)
            except (UnicodeDecodeError, OSError):
                continue
            if b:
                found[os.path.relpath(full, root).replace(os.sep, "/")] = b
    return found
