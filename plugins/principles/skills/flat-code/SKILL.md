---
name: flat-code
description: This skill should be used when writing or reviewing a function with deep nesting (if inside for inside if), long if/else chains, an else after a return, a loop body doing several jobs, or when the user asks to "flatten this", "de-nest", "reduce nesting", "use guard clauses", "early return", "this function is too long/complex", or "refactor this loop". Covers the depth-3 limit, inversion (guard clauses), extraction, and per-language idioms for Go, Python and Elixir, with a script that finds over-nested functions.
---

# Flat code

Each nesting level is a condition the reader must hold in their head while
reading the line. Keep functions at **depth 3 or less**, counting the
function body as 1. The Linux kernel style guide puts it bluntly: needing
more than three levels of indentation means the program needs fixing.

Two moves remove almost all nesting: **inversion** and **extraction**.

## Inversion: guard clauses

Check the unhappy path first and leave. The happy path stays at the
function's root indentation; there is no `else` after a `return`.

```
// Nested                          // Inverted
if user != nil {                   if user == nil {
    if user.Active {                   return ErrNoUser
        if hasQuota(user) {        }
            return send(user)      if !user.Active {
        } else {                       return ErrInactive
            return ErrQuota        }
        }                          if !hasQuota(user) {
    } else {                           return ErrQuota
        return ErrInactive         }
    }                              return send(user)
}
return ErrNoUser
```

The top of the function becomes a validation gate; everything after it may
assume valid input. The same move inside loops is `continue`.

## Extraction

Pull a loop body or a branch into a named function with one job. The caller
reads as a list of steps; the helper is testable alone.

**Worked example — background downloader.** One `run` loop handled a queue
of downloads: per item it switched on state (`Pending`, `InProgress`,
`Complete`), checked HTTP errors, retried up to three times, moved failures
to a failure queue, and disabled the connection after repeated connection
errors — five levels deep. Flattened:

- `run` became four calls: `processIncoming()`, `processDownloads()`,
  `clearCompleted()`, `waitForSignal()`.
- `processDownloads` dispatches on state to `processPending(d)` and
  `processInProgress(d)`.
- HTTP error handling became `handleHTTPError(d, err)`, returning early for
  the retry, failure-queue and disable-connection cases.

No logic changed; every function fits on a screen and sits at depth ≤ 3.

## When not to flatten

- Do not extract a three-line block into a helper used once whose name is
  longer than the block. Extraction must name a concept.
- Do not trade nesting for a boolean flag threaded through the function;
  that hides the same state in a variable.
- Do not split a function whose steps share a lot of local state into helpers
  taking six parameters. Introduce a small value type, or accept depth 4 and
  say why.
- A `switch`/`case`/`match` that maps one value to results is flat in
  meaning even if it indents; judge by conditions held, not by whitespace.

## Finding over-nested code

Run the bundled script (stdlib Python 3.10+, no install):

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/flat-code/scripts/nesting_depth.py --max 3 path/to/src
```

It prints `file:line: function: depth N` for each function deeper than the
limit and exits 1 if any are found. Python is measured from the `ast`
(an `elif` chain counts as one level);
Go and Elixir use an indentation heuristic over gofmt / mix format output —
read the function before reporting it. Prefer the language's linter when the
project already runs one (see references).

## Checklist

1. Deepest point of the function ≤ 3? If not, which condition can be inverted?
2. Any `else` after `return`/`continue`/`raise`? Remove it.
3. Does each loop body do one job? Extract the rest.
4. Does each extracted function name a concept, not a location ("part2")?
5. Did flattening change behaviour? Run the tests before and after.

## Language references

- **`references/go.md`** — `if err != nil` indent-error-flow, `switch true`,
  `nestif`/`gocognit` settings, closures.
- **`references/python.md`** — guard clauses, `continue`, comprehensions,
  `match`, ruff rules (`RET505`, `SIM102`, `PLR1702`, `C901`).
- **`references/elixir.md`** — multi-clause functions and guards, `with`,
  pipelines, Credo `Refactor.Nesting` (default max 2).
- **`references/typescript.md`** — guard clauses with narrowing, `?.`/`??`,
  discriminated unions with `assertNever`, ESLint `max-depth`/`no-else-return`.
- **`references/java.md`** — guard clauses, chaining `Optional`, switch
  expressions/patterns, streams vs loops, Checkstyle/PMD nesting rules.
- **`references/rust.md`** — `?`, `let ... else`, `continue` guards, iterator
  chains, `match` vs nested `if let`, clippy `excessive_nesting`.
- **`references/csharp.md`** — `ThrowIfNull` guards, `using` declarations,
  switch expressions and property patterns, CA1502/IDE analyzers.

## Scripts

- **`scripts/nesting_depth.py`** — report functions past a depth limit in
  `.py`, `.go`, `.ex`, `.exs` files. Any other file type, or a directory with
  none of these, exits 2; for those languages use the linter rules in their
  reference file.

Related: `principles-audit` runs this check alongside the others.
