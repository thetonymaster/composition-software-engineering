# composition-software-engineering

A Claude Code plugin marketplace with one plugin, `principles`: five skills
that steer how Claude designs, refactors and reviews code, and one agent that
audits code against them.

| Skill | Use it when |
|---|---|
| `composition` | reaching for an abstraction, a base class, a mixin, embedding or `use`; deciding whether an abstraction earns its keep |
| `dependency-injection` | code hardcodes a client, global, disk, network or clock; tests need monkeypatching; one function branches per backend |
| `flat-code` | a function nests past depth 3, chains `if`/`else`, or has an `else` after `return` |
| `measure-first` | someone says "make it faster", "optimize" or "is X faster than Y", before trading readability for speed |
| `principles-audit` | auditing a diff or module against the four principles above, or briefing a subagent to work under them |

| Agent | Use it when |
|---|---|
| `principles-auditor` | you want a `principles-audit` report from a fresh context that did not write the code; it reads and runs checks, and does not edit |

Every skill has references for **Go, Python, Elixir, TypeScript, Java, Rust
and C#** (`references/<language>.md`), loaded only when the code under review
is in that language. `flat-code` ships `scripts/nesting_depth.py`, which
measures nesting in all seven (Python exactly from the `ast`, the rest by an
indentation heuristic) and exits 2 on any other file type. Against exact
parsers the heuristic found 87/90 over-nested TypeScript functions and 59/60
Java methods; Rust and C# were spot-checked by hand.

## Install

From GitHub (needs access to this repository):

```
/plugin marketplace add thetonymaster/composition-software-engineering
/plugin install principles@composition-software-engineering
```

From a local clone:

```
/plugin marketplace add /path/to/composition-software-engineering
/plugin install principles@composition-software-engineering
```

Skills are namespaced once installed: `principles:composition`,
`principles:flat-code`, and so on. They trigger from their descriptions; you
can also invoke one by name, e.g. `/principles:principles-audit`. The agent
is `principles:principles-auditor`; ask Claude to "run the principles-auditor
agent on this branch", or pick it from `/agents`.

## How much of the reference material was executed

| Language | Snippets | Tool names, flags, rule IDs |
|---|---|---|
| Go | key claims probed (embedding, nil interface, `b.Loop` benchmark); not every snippet run | audit greps run on a real repo |
| Python | not executed | reviewed; `profiling.sampling` CLI checked |
| Elixir | not executed (Benchee example not run) | reviewed |
| TypeScript | type-checked with `tsc --strict`; DI tests run under vitest | ESLint rules and Node profiler flags run |
| Java | compiled and run on JDK 17 | Checkstyle, PMD, Error Prone, ArchUnit, JMH, JFR run |
| Rust | not compiled | clippy lints and criterion checked against their docs |
| C# | not compiled | analyzer IDs and .NET CLIs checked against Microsoft docs |

Audit `grep` commands were tested against planted samples with BSD grep.

## Development

```
python3 -m unittest discover -s tests          # skills structure + nesting_depth.py
claude plugin validate --strict plugins/principles
claude plugin validate --strict .
```

CI runs the same on every push to `main` and every pull request. See
`AGENTS.md` for the repository rules.
