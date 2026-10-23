# Audit commands: Rust

Run from the workspace root. Replace `$FILES` with the changed `.rs` files
(`git diff --name-only main...HEAD -- '*.rs'`). Every hit is a lead to read.
Unit tests live inline (`#[cfg(test)] mod tests`), so a file-level
`grep -v test` does not separate test code; read the hit.

## Linters (clippy)

```bash
cargo clippy --all-targets -- \
  -W clippy::too_many_arguments -W clippy::type_complexity \
  -W clippy::too_many_lines -W clippy::redundant_else \
  -W clippy::needless_continue -W clippy::manual_let_else \
  -W clippy::collapsible_else_if
```

| Lint | Group | Config key (clippy.toml) | Default |
|---|---|---|---|
| `too_many_arguments` | complexity | `too-many-arguments-threshold` | 7 |
| `type_complexity` | complexity | `type-complexity-threshold` | 250 |
| `too_many_lines` | pedantic | `too-many-lines-threshold` | 100 |
| `excessive_nesting` | complexity | `excessive-nesting-threshold` | 0 (never fires) |
| `cognitive_complexity` | restriction | `cognitive-complexity-threshold` | 25 |
| `disallowed_methods` / `disallowed_types` | style | `disallowed-methods` / `disallowed-types` | empty (never fires) |

`cognitive_complexity`'s own docs disown it as a measure; prefer
`excessive_nesting` and `too_many_lines`. Respect the project's `clippy.toml`
and `[lints.clippy]` table; the selection above is a one-off pass.

## Composition / DI

```bash
# Traits, then the implementations of each (second implementation?)
grep -rnE '^\s*(pub(\([a-z]+\))? )?trait [A-Z][A-Za-z0-9_]*' --include='*.rs' .
grep -rnE 'impl(<[^>]*>)? +([a-z_]+::)*NAME(<[^>]*>)? +for ' --include='*.rs' .

# Constructors returning trait objects (implementer-side abstraction)
grep -rnE 'fn [a-z_]+\(.*\) *-> *(Box|Arc|Rc)<dyn ' --include='*.rs' .

# Deref as inheritance: check each Target is not a smart-pointer pattern
grep -rnE 'impl(<[^>]*>)? +([a-z_]+::)*Deref(Mut)? +for ' --include='*.rs' .

# "Not supported" stubs (DrawableImage smell) outside tests
grep -rnE 'unimplemented!\(|todo!\(' --include='*.rs' src/

# Global state and self-registration
grep -rnE '^\s*(pub(\([a-z]+\))? )?static |lazy_static!|thread_local!|OnceLock|LazyLock|once_cell::|inventory::submit|distributed_slice' --include='*.rs' . \
  | grep -vE ':[0-9]+:\s*use '

# IO below the edge (adjust: core crate dir, exclude src/main.rs / src/bin/)
grep -rnE 'std::(fs|net|env|process)\b|SystemTime::now|Instant::now|reqwest::|tokio::(fs|net)\b' --include='*.rs' crates/core/src/

# Tests that work around hardwired dependencies
grep -rnE 'env::set_var|#\[serial|cfg!\(test\)|cfg\(not\(test\)\)' --include='*.rs' .

# Mocks: does the mocked trait have a second real implementation?
grep -rnE 'automock|mock! *\{' --include='*.rs' .
```

The IO grep matches `use std::fs;` and fully qualified calls, not grouped
imports like `use std::{env, fs};` — check `use` lines at the top of each
core file. A `static` holding a `Regex` or a lookup table built from literals
is read-only; a client, env-derived config or `Mutex` registry is a
singleton. `static mut` is a finding on sight.

Ordering: look for `&mut self` methods returning `()` followed by accessors
on the same type; the fix is `fn resolve(self, ..) -> Graph`.

## Flat code

```bash
python3 <plugin-root>/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES
```

The script reads rustfmt output by indentation (match arms are not a level;
closures and `let ... else` are). For a compiler-backed second opinion, run
clippy with a temporary threshold (`CLIPPY_CONF_DIR` replaces the project's
own `clippy.toml` for this run):

```bash
mkdir -p /tmp/clippy-nesting
printf 'excessive-nesting-threshold = 5\n' > /tmp/clippy-nesting/clippy.toml
CLIPPY_CONF_DIR=/tmp/clippy-nesting cargo clippy --all-targets -- -W clippy::excessive_nesting
```

`excessive_nesting` counts `mod`, `impl` and `fn` blocks, so its numbers run
higher than the skill's depth. Else after an exit:

```bash
grep -nE '^\s*\} else \{' $FILES  # then check whether the if-branch returns
```

## Measure first

```bash
# Optimisations should come with benchmarks
grep -rlE 'criterion|divan' --include='*.rs' benches/ 2>/dev/null
git diff main...HEAD -- '*.rs' | grep -nE '^\+.*(criterion_group!|#\[divan::bench|#\[bench\])'
# Low-level tricks in the diff that need evidence
git diff main...HEAD -- '*.rs' | grep -nE '^\+.*(unsafe|#\[inline|get_unchecked|MaybeUninit|FxHash|ahash|SmallVec)'
# Build-profile changes
git diff main...HEAD -- '*Cargo.toml' | grep -nE '^\+ *(lto|codegen-units|opt-level|panic) *='
```

If a criterion benchmark covers touched code, run it on both sides into one
shared results directory and let criterion compare:

```bash
export CRITERION_HOME=/tmp/audit-criterion
git worktree add --detach /tmp/audit-base main   # --detach: main is usually checked out elsewhere
(cd /tmp/audit-base && cargo bench --bench NAME -- --save-baseline base)
cargo bench --bench NAME -- --baseline base
git worktree remove /tmp/audit-base
```

Use a worktree for the base, never `git stash`: the stash stack is shared
across worktrees and sessions. `--bench NAME` is required: libtest harnesses
reject `--save-baseline`.
