# Audit commands: TypeScript

Run from the package root. `$FILES` = changed TypeScript files
(`git diff --name-only main...HEAD -- '*.ts' '*.tsx'`). Adjust `src/` and the
core directories to the project layout. Every hit is a lead to read.

## Compiler and linters

```bash
# Project config plus the flags these principles rely on (CLI flags override tsconfig)
npx tsc --noEmit -p . --noImplicitOverride --noImplicitReturns --noFallthroughCasesInSwitch

# One-off rule pass on top of the project's ESLint config (needs its TS parser setup)
npx eslint --rule '{"max-depth":["error",2],"no-else-return":["error",{"allowElseIf":false}],"no-lonely-if":"error","complexity":["error",10],"max-params":["error",4]}' $FILES
```

`max-depth: 2` is the skill's depth 3 (ESLint does not count the function
body). Type-aware rules — `@typescript-eslint/switch-exhaustiveness-check`,
`prefer-optional-chain`, `no-floating-promises` — need `parserOptions.projectService`
in the config; add them there, not on the CLI. `sonarjs/cognitive-complexity`
(default 15) if the plugin is installed. Respect the project's config; this
is a one-off pass.

## Composition / DI

```bash
# Interfaces and abstract classes, then count implementations of each
/usr/bin/grep -rnE '^export (interface|abstract class|type) [A-Za-z_$][A-Za-z0-9_$]*' --include='*.ts' src/
/usr/bin/grep -rnE '(implements|extends) ([A-Za-z0-9_$]+, *)*NAME\b' --include='*.ts' src/
/usr/bin/grep -rnE '^export interface I[A-Z]' --include='*.ts' src/   # IFoo beside its only Foo?

# Inheritance, stub overrides, protected state, decorators
/usr/bin/grep -rnE 'class [A-Za-z_$][A-Za-z0-9_$]*(<[^>]*>)? extends ' --include='*.ts' src/
/usr/bin/grep -rniE 'throw new Error\(.(not (supported|implemented))' --include='*.ts' src/
/usr/bin/grep -rnE '^[[:space:]]*protected ' --include='*.ts' src/
/usr/bin/grep -rnE '^[[:space:]]*@[A-Za-z]+\(' --include='*.ts' src/

# Module-level clients / singletons / mutable module state
/usr/bin/grep -nE '^(export )?(const|let) [A-Za-z_$][A-Za-z0-9_$]* *= *new [A-Z]' $FILES
/usr/bin/grep -nE '^(export )?let ' $FILES
/usr/bin/grep -nE 'process\.env' $FILES

# IO below the edge (core directories should import none of these)
/usr/bin/grep -rnE "from ['\"](node:)?(fs|fs/promises|http|https|net|child_process)['\"]" --include='*.ts' src/core/
/usr/bin/grep -rnE '(^|[^.])fetch\(|new Date\(\)|Date\.now\(\)|Math\.random\(\)' --include='*.ts' src/core/

# Tests that mock modules or reach into privates
/usr/bin/grep -rnE '(vi|jest)\.mock\(' --include='*.ts' --exclude-dir=node_modules .
/usr/bin/grep -rnE 'as any\)\.[a-zA-Z_#]+\(|\[["'"'"'][_a-zA-Z]+["'"'"']\]\(' --include='*.test.ts' --include='*.spec.ts' --exclude-dir=node_modules .
```

Ordering: look for methods returning `void` that mutate `this`, followed by
getters on the same class that return a plausible empty value (`[]`, `0`,
`undefined`) before the mutation has run.

## Flat code

```bash
npx eslint --rule '{"max-depth":["error",2]}' $FILES
/usr/bin/grep -nE '^[[:space:]]*\} else \{' $FILES   # then check whether the if-branch returns
/usr/bin/grep -nE '\.forEach\(async' $FILES          # unawaited callbacks, extra level
```

`python3 ${CLAUDE_PLUGIN_ROOT}/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES`
gives the skill's own count (block callbacks are a level; ESLint
`max-depth` resets at each function). Against the TypeScript compiler's AST
it found 87 of 90 over-nested functions with 1 false positive; it misses a
function whose template literal starts lines at column 0.

## Measure first

```bash
# Benchmarks added or existing
git diff main...HEAD -- '*.ts' '*.mts' | /usr/bin/grep -nE "^\+.*from ['\"](mitata|tinybench)['\"]"
/usr/bin/grep -rlE "from ['\"](mitata|tinybench)['\"]" --include='*.ts' --include='*.mts' --exclude-dir=node_modules .
# Low-level tricks in the diff that need evidence
git diff main...HEAD -- '*.ts' | /usr/bin/grep -nE '^\+.*(%[A-Z][A-Za-z]+\(|allow-natives-syntax|new Function\(|SharedArrayBuffer|Atomics\.|worker_threads)'
```

If a benchmark exists for touched code, run it on both sides in the same
session:

```bash
node --expose-gc bench/lookup.bench.mts > /tmp/new.txt
git worktree add --detach /tmp/audit-base main   # --detach: main is usually checked out elsewhere
(cd /tmp/audit-base && npm ci && node --expose-gc bench/lookup.bench.mts > /tmp/old.txt)
git worktree remove /tmp/audit-base
```

Compare the distributions (avg and p75/p99), not single numbers. Use a
worktree for the base, never `git stash`.
