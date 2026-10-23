# Audit commands: Go

Run from the module root. Replace `$FILES` with the changed `.go` files
(`git diff --name-only main...HEAD -- '*.go'`). Every hit is a lead to read.

## Linters (if the project has golangci-lint)

```bash
golangci-lint run --enable-only=interfacebloat,ireturn,gochecknoinits,gochecknoglobals,nestif,gocognit,revive ./...
```

Respect the project's `.golangci.yml`; this command is for a one-off pass.

## Composition / DI

```bash
# Interfaces and their implementation count
grep -rnE '^type [A-Za-z_]+ interface' --include='*.go' .
# For each interface I, list types with its methods (second implementation?)
grep -rnE 'func \([a-z]+ \*?[A-Z][A-Za-z]*\) MethodName\(' --include='*.go' .

# Constructors returning interfaces (implementer-side interfaces)
grep -rnE '^func New[A-Za-z]*\(.*\) [A-Z][A-Za-z]*(,|$| \{)' --include='*.go' .

# Package-level state and init registration (var x = ..., var x T, var ( blocks)
grep -rnE '^func init\(\)|sync\.Once|^var( |\()' --include='*.go' . | grep -v _test.go

# IO below the edge (adjust the edge directory: cmd/, main.go)
grep -rnE '"(os|os/exec|net/http|net)"' --include='*.go' internal/ pkg/ | grep -v _test.go
grep -rnE 'time\.Now\(\)|os\.Getenv' --include='*.go' internal/ pkg/ | grep -v _test.go

# Dependencies smuggled through context
grep -rn 'ctx.Value(' --include='*.go' .
```

Ordering: look for exported methods that return nothing and mutate the
receiver, followed by accessors on the same type
(`grep -nE 'func \(.*\) [A-Z][a-zA-Z]*\([^)]*\) \{$'` lists no-return methods).

Embedding: `grep -nE '^\s+\*?[A-Z][A-Za-z.]*$' file.go` inside struct
bodies lists embedded fields; check each for API leakage (`sync.Mutex`)
and reliance on "overriding".

## Flat code

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES
grep -nE '^\s*\} else \{' $FILES   # then check whether the if-branch returns
```

## Measure first

```bash
# Optimisations should come with benchmarks: added or existing ones
git diff main...HEAD -- '*_test.go' | grep -nE '^\+func Benchmark'
grep -rn 'func Benchmark' --include='*_test.go' .
# Low-level tricks in the diff that need evidence
git diff main...HEAD -- '*.go' | grep -nE '^\+.*(unsafe\.|sync\.Pool|//go:noinline|//go:linkname)'
```

If a benchmark exists for touched code, run it on both sides and compare:

```bash
go test -run='^$' -bench=. -benchmem -count=10 ./pkg > /tmp/new.txt
git worktree add --detach /tmp/audit-base main   # --detach: main is usually checked out elsewhere
(cd /tmp/audit-base && go test -run='^$' -bench=. -benchmem -count=10 ./pkg > /tmp/old.txt)
benchstat /tmp/old.txt /tmp/new.txt
git worktree remove /tmp/audit-base
```

Use a worktree for the base, never `git stash`: the stash stack is shared
across worktrees and sessions.
