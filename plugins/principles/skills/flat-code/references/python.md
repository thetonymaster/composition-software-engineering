# Flat code in Python

Python's indentation *is* its nesting, so depth is visible — and so is the
cost. The extra trap is exception handling: `try` blocks add a level, and
wrapping a whole function body in `try` pushes everything down one.

## Guard clauses

```python
# Avoid
def charge(user):
    if user is not None:
        if user.active:
            if user.quota > 0:
                return bill(user)
            else:
                raise QuotaExceeded(user.id)
        else:
            raise Inactive(user.id)
    else:
        raise ValueError("charge: user is None")

# Prefer
def charge(user):
    if user is None:
        raise ValueError("charge: user is None")
    if not user.active:
        raise Inactive(user.id)
    if user.quota <= 0:
        raise QuotaExceeded(user.id)
    return bill(user)
```

## Narrow `try`

```python
# Avoid: the whole body is in the try, and the handler hides which call failed.
try:
    cfg = load(path)
    for item in cfg.items:
        if item.enabled:
            process(item)
except OSError as err:
    ...

# Prefer: the try wraps only the call that raises the handled error.
try:
    cfg = load(path)
except OSError as err:
    raise ConfigError(f"load {path}: {err}") from err
for item in cfg.items:
    if not item.enabled:
        continue
    process(item)
```

## Other flattening tools

- **Comprehensions** replace `for` + `if` + `append` — but a comprehension
  with two `for`s and two `if`s is nesting in one line; use a loop or a
  generator function instead.
- **`match`** (3.10+) for dispatch on shape; each `case` is a guard-like
  branch at one level.
- **`contextlib.ExitStack`** or parenthesised multi-item `with` (3.10+)
  instead of stacked `with` blocks.
- **`any()` / `all()` / `next(..., None)`** instead of search loops with a
  flag.
- **Dict dispatch** (`HANDLERS[state](download)`) when the cases are data —
  the downloader's `processPending` / `processInProgress` split is this.

## Linters (ruff)

| Rule | What |
|---|---|
| `RET505`–`RET508` | `else`/`elif` after `return`, `raise`, `continue`, `break` |
| `SIM102` | collapsible nested `if` |
| `SIM108` | if/else assignment → ternary (use judgement) |
| `C901` | McCabe complexity (`lint.mccabe.max-complexity`, default 10) |
| `PLR1702` | too many nested blocks (`lint.pylint.max-nested-blocks`, default 5; preview rule, needs `--preview`) |
| `PLR0912` / `PLR0915` | too many branches / statements |

`scripts/nesting_depth.py` measures Python from the `ast`: `if`, `for`,
`while`, `with`, `try`, `match` each add a level; an `elif` does not (it is a
sibling branch); nested functions are measured separately.
