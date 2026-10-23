---
name: principles-audit
description: This skill should be used when auditing a diff, branch or module specifically against design principles (composition, dependency injection, nesting, premature optimization), when briefing a subagent to implement or review work under those principles, or when the user asks to "audit this against our principles", "check composition / DI / nesting / premature optimization", "is this over-engineered", or "is this abstraction worth it". Not for a general bug or security review. Runs four checks — composition, dependency injection, flat code, measure-first — in both directions (too little and too much structure), with evidence-backed findings, for Go, Python, Elixir, TypeScript, Java, Rust and C#.
---

# Principles audit

Audit a change against four principles, each with its own skill holding the
reasoning. This skill is the procedure and the report format; load a
principle's skill only when a finding needs its depth.

| Principle | Under-applied looks like | Over-applied looks like | Skill |
|---|---|---|---|
| Composition | inheritance for reuse, IO in the core, hidden ordering, globals | interface/registry/factory with one implementation | `composition` |
| Dependency injection | hardwired clients, monkeypatched tests, if/else per backend | containers and seams nothing varies | `dependency-injection` |
| Flat code | depth > 3, `else` after `return`, multi-job loop bodies | one-use helpers that name nothing, flag-threading | `flat-code` |
| Measure first | O(n²) on unbounded input | readability spent on unmeasured speed | `measure-first` |

Every principle fails in two directions. Report the direction actually
present; do not split the difference to sound balanced.

## Two modes

**Follow** (while implementing, or briefing a subagent that implements):
run the per-principle checklist below before writing each new abstraction,
function or optimisation, and again before declaring the work done.

**Audit** (reviewing finished work): run the procedure, produce the report.
Stay read-only — report findings; do not fix them unless asked.

## Audit procedure

1. **Scope.** List the changed files: `git diff --name-only <base>...HEAD`
   (or the files named). Identify languages. Read the project's
   CLAUDE.md/CONTRIBUTING for local rules that override defaults here.
2. **Mechanical pass.** Run the detection commands for each language from the
   references (linters the project already uses first, then greps and
   `flat-code/scripts/nesting_depth.py`). These produce *leads*, not findings.
   Run them in bash (`bash -c '...'`): they rely on an unquoted `$FILES`
   splitting into one argument per file. zsh does not split it, so each tool
   receives a single nonexistent path, and some report a pass anyway (ruff
   prints "All checks passed!"). A tool that ran on nothing is not a pass.
3. **Judgement pass.** For each lead and each new abstraction in the diff:
   - Composition / DI: name the second implementation and where it lives. If
     none exists now or in a committed plan, and the dependency is not outside
     the process, it is over-abstraction. If a test needs patching to work,
     it is under-abstraction.
   - Flat code: read the function. Is depth driven by conditions the reader
     must hold, or by a flat `switch`? Can a guard clause or extraction remove
     a level without inventing a meaningless helper?
   - Measure first: for each optimisation in the diff, find its evidence
     (benchmark, profile, numbers in the commit). For each loop over input,
     ask whether the input is bounded.
4. **Verify claims.** Where the code, a comment, a doc or a commit message
   states a property ("no IO below cmd/", "adding a backend touches one
   file", "2x faster"), test it: grep for the import, count the files a new
   implementation would touch, run the benchmark. A false claim is a finding
   even when the code is fine.
5. **Report** in the format below. Rank by impact. Drop anything that cannot
   cite a location and evidence.

## Report format

```
## Principles audit: <scope>

Verdict: <ship | ship with follow-ups | fix first> — <one sentence>

### Findings (ranked)
1. [<principle> · <under|over|false-claim>] <file>:<line> — <one-line defect>
   Evidence: <command output, quoted code, or count>
   Fix: <smallest change that resolves it>

### Survived scrutiny
- <abstraction or choice examined and kept> — <why: e.g. "3 implementations
  in internal/fetch">

### Not checked
- <what was out of scope or could not be run, and why>
```

"Survived scrutiny" matters as much as findings: it shows each abstraction
was attacked, and it stops the next reviewer re-litigating it. "Not checked"
must list anything skipped — a check that did not run is not a pass.

## Per-principle checklists (follow mode)

**Composition**
1. Second implementation named? Otherwise write the concrete thing.
2. IO pushed to the outermost layer?
3. Ordering constraint expressed as a type / distinct struct?
4. No package/module-level mutable state or named singleton process?
5. Reuse via composed parts, not a parent type or `use` macro?

**Dependency injection**
1. Implementation constructed at one edge location?
2. Factory only where the choice depends on data, failing loudly on unknown
   input?
3. Tests run with no network, disk or real clock, and no monkeypatching?

**Flat code**
1. Depth ≤ 3 counting the body as 1?
2. No `else` after `return`/`raise`/`continue`?
3. Each loop body one job; each extracted function names a concept?

**Measure first**
1. Is there a measured problem and a target number?
2. Was the hotspot found by a profiler?
3. Before/after numbers with variance accompany the change?

## Briefing a subagent

When dispatching review or implementation to a subagent, include in its
prompt: the scope (files or `git diff` range), the instruction to load the
`principles-audit` skill (or read
`${CLAUDE_PLUGIN_ROOT}/skills/principles-audit/SKILL.md`), the mode (follow or audit),
and that it must return the report format above. Do not include a suspected
conclusion; an auditor handed a hypothesis tends to confirm it.

## Language references

- **`references/go.md`** — detection commands and linters for Go.
- **`references/python.md`** — detection commands and linters for Python.
- **`references/elixir.md`** — detection commands and Credo/xref for Elixir.
- **`references/typescript.md`** — detection commands, tsc flags and ESLint
  rules for TypeScript.
- **`references/java.md`** — detection commands and Checkstyle/PMD/Error
  Prone/ArchUnit for Java.
- **`references/rust.md`** — detection commands and clippy lints/config for
  Rust.
- **`references/csharp.md`** — detection commands and Roslyn analyzers
  (.editorconfig, `CodeMetricsConfig.txt`) for C#.
