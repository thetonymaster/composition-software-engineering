#!/usr/bin/env python3
"""Report functions whose block nesting exceeds a limit.

Usage: nesting_depth.py [--max N] PATH...

PATH may be a file or a directory (searched for .py, .go, .ex, .exs, .java,
.cs, .rs, .ts, .tsx). Depth counts the function body as 1 and each enclosing
control block (if/for/while/with/try/match/switch/select/case/cond/receive)
and block closure as one more; an else-if chain, case clauses and Rust match
arms do not add a level. Default limit is 3: anything at depth 4 or deeper
is reported.

Python is measured exactly with the ast module. The other languages are
measured with a line heuristic (a stack of control-statement indents) that
assumes formatter output: gofmt, mix format, google-java-format, dotnet
format, rustfmt, prettier. Each language is a Syntax value: adding one is a
new entry in MEASURERS, not a new code path. Against exact parsers the
heuristic found 87/90 over-nested TypeScript functions (1 false positive)
and 59/60 Java methods; Rust and C# were spot-checked by hand. It misses
functions whose multi-line string literals start lines at column 0. Treat
heuristic findings as leads to read, not verdicts.

Exit status: 0 if nothing exceeds the limit, 1 if something does, 2 on
usage errors, including a file of another type or a directory with no
supported files (nothing measured is not a pass).
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

PY_BLOCKS = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
    ast.Try, ast.Match,
)
if hasattr(ast, "TryStar"):
    PY_BLOCKS += (ast.TryStar,)


@dataclass(frozen=True)
class Syntax:
    """How the indentation heuristic reads one language."""

    func: re.Pattern  # line that starts a function
    name: re.Pattern  # group 1 is the function's name
    control: re.Pattern  # line that opens a nested block
    clause: re.Pattern  # line that continues the block above it (case, else)
    tab_width: int
    comment: tuple = ()  # line prefixes to skip


GO = Syntax(
    func=re.compile(r"^(\s*)func\b"),
    name=re.compile(r"func\s*(?:\([^)]*\)\s*)?(\w+)"),
    control=re.compile(
        r"^\s*(\}\s*else\b|if\b|for\b|switch\b|select\b|go\s+func\b|defer\s+func\b)"
        r"|\bfunc\s*\([^)]*\)[^{]*\{\s*$"
    ),
    clause=re.compile(r"^\s*(case\b|default\s*:)"),
    tab_width=1,
)

ELIXIR = Syntax(
    func=re.compile(r"^(\s*)(def|defp|defmacro|defmacrop)\b"),
    name=re.compile(r"(?:def|defp|defmacro|defmacrop)\s+(\w+[?!]?)"),
    control=re.compile(
        r"^\s*(if|unless|case|cond|with|for|receive|try)\b"
        r"|\bfn\b[^\n]*->\s*$"
    ),
    clause=re.compile(r"^\s*(else|after|rescue|catch)\b"),
    tab_width=2,
)

NEVER = re.compile(r"(?!)")
C_COMMENTS = ("//", "/*", "*")
SWITCH_CLAUSE = re.compile(r"^\s*(case\b|default\s*(:|->))")


def method_def(keywords, modifiers):
    """A method or function declaration in a C-family language: a name and an
    open parenthesis, no assignment before it, no semicolon after it, and not
    a type declaration (a record or primary-constructor class has parameters
    too). Group 1 is the name."""
    return re.compile(
        rf"^\s*(?!(?:{keywords})\b)(?![^(]*\b(?:class|record|struct|interface|enum)\b)"
        rf"(?:(?:{modifiers})\s+)*"
        r"[\w$@<>\[\]?,. ]*?\b(\w+)\s*(?:<[^>]*>)?\s*\([^;]*$"
    )


JAVA_DEF = method_def(
    "if|else|for|while|do|switch|case|try|catch|finally|return|new|throw|synchronized|assert|yield",
    "public|protected|private|static|final|abstract|synchronized|native|default|strictfp",
)
JAVA = Syntax(
    func=JAVA_DEF,
    name=JAVA_DEF,
    control=re.compile(
        r"^\s*(\}\s*)?(if|else|for|while|do|switch|try|catch|finally|synchronized)\b"
        r"|->\s*\{\s*$"
    ),
    clause=SWITCH_CLAUSE,
    tab_width=4,
    comment=C_COMMENTS,
)

CSHARP_DEF = method_def(
    "if|else|for|foreach|while|do|switch|case|try|catch|finally|return|new|throw|lock"
    "|using|fixed|checked|unchecked|yield|await|var",
    "public|protected|private|internal|static|virtual|override|abstract|sealed|async"
    "|extern|unsafe|new|partial|readonly",
)
CSHARP = Syntax(
    func=CSHARP_DEF,
    name=CSHARP_DEF,
    control=re.compile(
        r"^\s*(\}\s*)?(if|else|for|foreach|while|do|switch|try|catch|finally|lock|fixed"
        r"|checked|unchecked|unsafe)\b|^\s*using\s*\("
        r"|=>\s*\{?\s*$|\bdelegate\s*(\([^)]*\))?\s*\{?\s*$"  # lambdas, K&R or Allman"
    ),
    clause=SWITCH_CLAUSE,
    tab_width=4,
    comment=C_COMMENTS,
)

RUST_FN = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe|extern(?:\s+\"[^\"]*\")?)\s+)*fn\s+(\w+)"
)
RUST = Syntax(
    func=RUST_FN,
    name=RUST_FN,
    control=re.compile(
        r"^\s*(\}\s*)?(if|else|for|while|loop|match)\b"
        r"|\belse\s*\{\s*$"  # let-else
        r"|\|[^|]*\|\s*(->\s*[^{]*)?\{\s*$"  # closure
        r"|\basync(\s+move)?\s*\{\s*$"
    ),
    clause=NEVER,  # match arms are lines inside the match, not clauses at its indent
    tab_width=4,
    comment=("//", "/*", "*"),
)

TS_DEF = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b\*?\s*(\w*)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)[^=]*=\s*(?:async\s+)?(?:\(|\w+\s*=>|function\b)"
    r"|^\s*(?!(?:if|else|for|while|do|switch|case|try|catch|finally|return|new|throw|await"
    r"|yield|typeof|void|delete|function)\b)"
    r"(?:(?:public|private|protected|static|async|readonly|override|abstract|get|set)\s+)*"
    r"\*?(\w+)\s*(?:<[^>]*>)?\s*(?:\([^;)]*$|\(.*\)\s*(?::\s*[^{;=]+)?\{\s*$)"
)
TYPESCRIPT = Syntax(
    func=TS_DEF,
    name=TS_DEF,
    control=re.compile(
        r"^\s*(\}\s*)?(if|else|for|while|do|switch|try|catch|finally)\b"
        r"|=>\s*\{\s*$|\bfunction\b[^{]*\{\s*$"
    ),
    clause=SWITCH_CLAUSE,
    tab_width=4,
    comment=C_COMMENTS,
)


def is_elif(parent, child):
    return (
        isinstance(parent, ast.If)
        and isinstance(child, ast.If)
        and len(parent.orelse) == 1
        and parent.orelse[0] is child
    )


def deepest(node, depth):
    """Deepest block level under node, and the line where it occurs."""
    best = (depth, getattr(node, "lineno", 0))
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue  # nested functions are reported on their own
        step = 0 if is_elif(node, child) else int(isinstance(child, PY_BLOCKS))
        best = max(best, deepest(child, depth + step), key=lambda c: c[0])
    return best


def python_findings(text, limit):
    """Findings as (line, message) pairs, measured exactly from the ast."""
    try:
        tree = ast.parse(text)
    except SyntaxError as err:
        return [(err.lineno, f"cannot parse: {err.msg}")]
    funcs = (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    out = []
    for node in funcs:
        depth, line = deepest(node, 1)
        if depth > limit:
            out.append((line, f"{node.name}: depth {depth} (limit {limit})"))
    return out


@dataclass
class Function:
    """A function being read: its indent, its open control blocks, its worst depth."""

    name: str
    indent: int
    worst: tuple
    blocks: list = field(default_factory=list)

    def read(self, indent, lineno, opens_block):
        while self.blocks and self.blocks[-1] >= indent:
            self.blocks.pop()
        if not opens_block:
            return
        self.blocks.append(indent)
        self.worst = max(self.worst, (len(self.blocks) + 1, lineno), key=lambda w: w[0])


def step(fn, lineno, line, syntax):
    """Read one line. Returns (the function now open, a function that just ended)."""
    expanded = line.expandtabs(syntax.tab_width)
    indent = len(expanded) - len(expanded.lstrip())
    if syntax.func.match(line) and (fn is None or indent <= fn.indent):
        found = syntax.name.search(line)
        name = next((g for g in found.groups() if g), None) if found else None
        return Function(name or line.strip(), indent, (1, lineno)), fn
    if fn is None:
        return None, None
    if indent <= fn.indent:  # the function's own closing line, or the end of it
        continues = line.strip().startswith(("}", ")", "end"))
        return (fn, None) if continues else (None, fn)
    if not syntax.clause.match(line):  # a case/else clause sits at its opener's indent
        fn.read(indent, lineno, bool(syntax.control.search(line)))
    return fn, None


def heuristic_findings(text, limit, syntax):
    """Findings as (line, message) pairs, from a stack of control-statement indents."""
    out, fn = [], None
    for lineno, line in enumerate(text.splitlines(), 1):
        code = line.strip()
        if code in ("", "{") or code.startswith(syntax.comment):
            continue  # a lone "{" belongs to the line above (Allman style)
        fn, ended = step(fn, lineno, line, syntax)
        out += report(ended, limit)
    return out + report(fn, limit)


def report(fn, limit):
    if fn is None or fn.worst[0] <= limit:
        return []
    return [(fn.worst[1], f"{fn.name}: depth {fn.worst[0]} (limit {limit}, heuristic)")]


MEASURERS = {
    ".py": python_findings,
    ".go": partial(heuristic_findings, syntax=GO),
    ".ex": partial(heuristic_findings, syntax=ELIXIR),
    ".exs": partial(heuristic_findings, syntax=ELIXIR),
    ".java": partial(heuristic_findings, syntax=JAVA),
    ".cs": partial(heuristic_findings, syntax=CSHARP),
    ".rs": partial(heuristic_findings, syntax=RUST),
    ".ts": partial(heuristic_findings, syntax=TYPESCRIPT),
    ".tsx": partial(heuristic_findings, syntax=TYPESCRIPT),
}


class UsageError(Exception):
    pass


def expand(raw):
    """The supported files a command-line PATH names."""
    path = Path(raw)
    supported = ", ".join(MEASURERS)
    if not path.exists():
        raise UsageError(f"path {raw!r} does not exist")
    if path.is_file() and path.suffix not in MEASURERS:
        raise UsageError(
            f"unsupported file type {path.suffix or '(none)'!r} for {raw!r};"
            f" supported: {supported}. Use the language's linter instead"
        )
    if path.is_file():
        return [path]
    found = sorted(f for ext in MEASURERS for f in path.rglob("*" + ext))
    if not found:
        raise UsageError(f"directory {raw!r} has no {supported} files; nothing was measured")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max", type=int, default=3, help="deepest allowed level (default 3)")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    try:
        files = [f for raw in args.paths for f in expand(raw)]
    except UsageError as err:
        print(f"nesting_depth: {err}", file=sys.stderr)
        return 2

    found = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        found += [f"{f}:{line}: {msg}" for line, msg in MEASURERS[f.suffix](text, args.max)]
    for msg in found:
        print(msg)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
