#!/usr/bin/env python3
"""Report functions whose block nesting exceeds a limit.

Usage: nesting_depth.py [--max N] PATH...

PATH may be a file or a directory (searched for .py, .go, .ex, .exs).
Depth counts the function body as 1 and each enclosing control block
(if/for/while/with/try/match/switch/select/case/cond/receive/fn/closure)
as one more. Default limit is 3: anything at depth 4 or deeper is reported.

Python is measured exactly with the ast module. Go and Elixir are measured
with a line heuristic (a stack of control-statement indents), which assumes
gofmt / mix format output. Treat Go and Elixir findings as leads to read,
not verdicts.

Exit status: 0 if nothing exceeds the limit, 1 if something does, 2 on
usage errors, including a file of another type or a directory with no
supported files (nothing measured is not a pass).
"""

import argparse
import ast
import re
import sys
from pathlib import Path

PY_BLOCKS = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
    ast.Try, ast.Match,
)
if hasattr(ast, "TryStar"):
    PY_BLOCKS += (ast.TryStar,)

GO_FUNC = re.compile(r"^(\s*)func\b")
GO_CONTROL = re.compile(
    r"^\s*(\}\s*else\b|if\b|for\b|switch\b|select\b|go\s+func\b|defer\s+func\b)"
    r"|\bfunc\s*\([^)]*\)[^{]*\{\s*$"
)
GO_NAME = re.compile(r"func\s*(?:\([^)]*\)\s*)?(\w+)")
GO_CLAUSE = re.compile(r"^\s*(case\b|default\s*:)")
EX_FUNC = re.compile(r"^(\s*)(def|defp|defmacro|defmacrop)\b")
EX_CONTROL = re.compile(
    r"^\s*(if|unless|case|cond|with|for|receive|try)\b"
    r"|\bfn\b[^\n]*->\s*$"
)
EX_NAME = re.compile(r"(?:def|defp|defmacro|defmacrop)\s+(\w+[?!]?)")
EX_CLAUSE = re.compile(r"^\s*(else|after|rescue|catch)\b")
SUPPORTED = (".py", ".go", ".ex", ".exs")


def is_elif(parent, child):
    return (
        isinstance(parent, ast.If)
        and isinstance(child, ast.If)
        and len(parent.orelse) == 1
        and parent.orelse[0] is child
    )


def python_findings(path, text, limit):
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as err:
        return [f"{path}:{err.lineno}: cannot parse: {err.msg}"]
    out = []

    def deepest(node, depth):
        best = (depth, getattr(node, "lineno", 0))
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue  # nested functions are reported on their own
            step = 1 if isinstance(child, PY_BLOCKS) else 0
            if is_elif(node, child):
                step = 0  # elif is a sibling branch, not a nested block
            cand = deepest(child, depth + step)
            if cand[0] > best[0]:
                best = cand
        return best

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth, line = deepest(node, 1)
            if depth > limit:
                out.append(f"{path}:{line}: {node.name}: depth {depth} (limit {limit})")
    return out


def indent_of(line, tab_width):
    expanded = line.expandtabs(tab_width)
    return len(expanded) - len(expanded.lstrip())


def heuristic_findings(path, text, limit, lang, tab_width):
    func_re, name_re, control_re, clause_re = lang
    out = []
    name, func_indent, stack, worst = None, 0, [], (0, 0)

    def flush():
        if name is not None and worst[0] > limit:
            out.append(f"{path}:{worst[1]}: {name}: depth {worst[0]} (limit {limit}, heuristic)")

    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        indent = indent_of(line, tab_width)
        fm = func_re.match(line)
        if fm and (name is None or indent <= func_indent):
            flush()
            nm = name_re.search(line)
            name = nm.group(1) if nm else line.strip()
            func_indent, stack, worst = indent, [], (1, lineno)
            continue
        if name is None:
            continue
        if indent <= func_indent and not line.strip().startswith(("}", "end")):
            flush()
            name = None
            continue
        if clause_re.match(line):
            continue  # a case/else clause sits at its opener's indent; keep the opener
        while stack and stack[-1] >= indent:
            stack.pop()
        if control_re.search(line):
            stack.append(indent)
            depth = len(stack) + 1
            if depth > worst[0]:
                worst = (depth, lineno)
    flush()
    return out


def findings_for(path, limit):
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return python_findings(path, text, limit)
    if path.suffix == ".go":
        return heuristic_findings(path, text, limit, (GO_FUNC, GO_NAME, GO_CONTROL, GO_CLAUSE), 1)
    if path.suffix in (".ex", ".exs"):
        return heuristic_findings(path, text, limit, (EX_FUNC, EX_NAME, EX_CONTROL, EX_CLAUSE), 2)
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max", type=int, default=3, help="deepest allowed level (default 3)")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    files = []
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"nesting_depth: path {raw!r} does not exist", file=sys.stderr)
            return 2
        if p.is_dir():
            found_in_dir = sorted(f for ext in SUPPORTED for f in p.rglob("*" + ext))
            if not found_in_dir:
                print(f"nesting_depth: directory {raw!r} has no {', '.join(SUPPORTED)} files;"
                      " nothing was measured", file=sys.stderr)
                return 2
            files += found_in_dir
        elif p.suffix not in SUPPORTED:
            print(f"nesting_depth: unsupported file type {p.suffix or '(none)'!r} for {raw!r};"
                  f" supported: {', '.join(SUPPORTED)}. Use the language's linter instead",
                  file=sys.stderr)
            return 2
        else:
            files.append(p)

    found = [msg for f in files for msg in findings_for(f, args.max)]
    for msg in found:
        print(msg)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
