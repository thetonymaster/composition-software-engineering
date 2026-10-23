# Audit commands: Python

`$FILES` = changed `.py` files (`git diff --name-only main...HEAD -- '*.py'`).
Every hit is a lead to read.

## Linters

```bash
ruff check --select C901,PLR0912,PLR0913,PLR0915,PLW0603,RET505,RET506,RET507,RET508,SIM102 $FILES
ruff check --preview --select PLR1702 $FILES      # too-many-nested-blocks (preview)
pyright $FILES   # or: mypy --strict $FILES — Protocol conformance, type-state ordering
```

Respect `pyproject.toml` settings; the selection above is a one-off pass.

## Composition / DI

```bash
# ABCs and Protocols, then count implementations of each
grep -rnE 'class [A-Za-z_]+\((ABC|abc\.ABC|Protocol)' --include='*.py' .
grep -rnE 'class [A-Za-z_]+\([^)]*\bNAME\b' --include='*.py' .   # subclasses of NAME

# Inheritance depth and mixins
grep -rnE 'class [A-Za-z_]+\([^)]*Mixin' --include='*.py' .
grep -rn 'raise NotImplementedError' --include='*.py' .           # DrawableImage smell

# Module-level clients / singletons / cached config
grep -rnE '^[a-z_]+ *= *[A-Za-z_.]+\(' $FILES
grep -rnE '^_instance|@(functools\.)?(lru_)?cache' $FILES
grep -rn 'os\.environ\|os\.getenv' $FILES

# Tests that patch hardwired dependencies
grep -rnE 'mock\.patch\(|monkeypatch\.setattr\(' tests/ | grep -v 'os\.environ'
# Tests calling private methods
grep -rnE '\._[a-z][a-z_]*\(' tests/
```

## Flat code

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES
```

## Measure first

```bash
git diff main...HEAD -- '*.py' | grep -nE '^\+.*(lru_cache|cache\b|__slots__|cython|numba|ctypes)'
grep -rln 'benchmark\|pyperf\|timeit' tests/ benchmarks/ 2>/dev/null
```

For a claimed speedup, rerun the benchmark on both sides with `pyperf`
(`compare_to`) or `pytest --benchmark-compare`.
