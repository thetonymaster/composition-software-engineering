# AGENTS.md

Guidance for coding agents working in this repository. `CLAUDE.md` imports this file, so Claude Code reads the same rules.

## Checks

| Covers | Command |
|---|---|
| skill structure, indexes, local paths, `nesting_depth.py` | `python3 -m unittest discover -s tests` |
| plugin manifest and skills | `claude plugin validate --strict plugins/principles` |
| marketplace manifest | `claude plugin validate --strict .` |

Single test: `python3 -m unittest tests.test_skills.SkillsTest.<method>`.

CI (`.github/workflows/ci.yml`) runs the unittest suite on Python 3.10 and 3.13 and both validations on every push to `main` and every PR. The Claude Code version in CI is pinned; bump it deliberately, after validating locally.

## Layout

The repo is a **plugin marketplace** (`.claude-plugin/marketplace.json`, name `composition-software-engineering`) with one plugin, `plugins/principles`, holding five skills:
- `composition`, `dependency-injection`, `flat-code`, `measure-first` — one principle each.
- `principles-audit` — runs the four as a review, in both directions (too little and too much structure).

The plugin also has one agent, `agents/principles-auditor.md`. It runs `principles-audit` in a fresh, read-only context and returns its report. `tests/test_skills.py` checks its frontmatter.

Each skill has `SKILL.md` plus `references/<lang>.md` for `go`, `python`, `elixir`, `typescript`, `java`, `rust`, `csharp`. `SKILL.md` lists every reference under "Language references"; `tests/test_skills.py` fails if one is missing or unlisted.

`flat-code/scripts/nesting_depth.py` is stdlib-only Python 3.10+. It measures `.py` exactly (ast) and Go, Elixir, Java, C#, Rust and TypeScript by an indentation heuristic, and exits 2 on any other file type. Each heuristic language is a `Syntax` value registered in `MEASURERS`; adding one is data plus a test, not a new code path. Its tests are `tests/test_nesting_depth.py`, including one that runs the script on itself at depth 3.

## Conventions

- Refer to bundled files as `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/...`, never `~/.claude/...` or an absolute path; `test_no_machine_local_paths` enforces it.
- Adding a language: add `references/<lang>.md` to all five skills, list each in its `SKILL.md`, add the language to `LANGUAGES` in `tests/test_skills.py`, update the skill `description` fields, the plugin and marketplace descriptions, and the README verification table. Add a `Syntax` for it to `nesting_depth.py` with a fixture test, and check it against an exact parser or a real formatted corpus before claiming coverage.
- Reference files mirror the existing ones: same section headings, imperative voice, Avoid/Prefer pairs. State only what was checked; say in the README table what was run and what was not.
- Test audit `grep` commands with `/usr/bin/grep -E` (BSD) or GNU grep, not a `grep` alias such as ugrep, which accepts patterns the others silently fail to match.
- Skills cross-reference each other by name (`composition`, `principles-audit`); keep the names stable.
- Bump `version` in `plugins/principles/.claude-plugin/plugin.json` when the plugin changes. Keep its `description` identical to the marketplace entry (tested).
