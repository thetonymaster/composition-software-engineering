# Flat code in Go

Go's error handling makes inversion the house style. The Go Code Review
Comments wiki ("Indent Error Flow"): keep the normal code path at minimal
indentation and handle the error first.

## Indent error flow

```go
// Avoid
if err != nil {
	return err
} else {
	use(x)
}

// Prefer
if err != nil {
	return fmt.Errorf("load %s: %w", path, err)
}
use(x)
```

Also avoid the scoped-assignment form when the variable is used after the
`if`, because it forces the happy path into an `else`:

```go
// Avoid
if x, err := f(); err != nil {
	return err
} else {
	use(x)
}

// Prefer
x, err := f()
if err != nil {
	return err
}
use(x)
```

## Loops: continue as the guard

```go
for _, e := range entities {
	if e.Kind != "service" {
		continue
	}
	if e.Owner == "" {
		missing = append(missing, e.Name)
		continue
	}
	checkOwner(e)
}
```

## Replace if/else chains

- `switch` with no tag (`switch { case a: ...; case b: ... }`) for a chain
  of unrelated conditions.
- A `map[Kind]func(...)` only when the set of cases is data; otherwise a
  `switch` reads better and is checked by `exhaustive` for enum-like types.

## Closures and goroutines

A closure inside a loop inside a function starts at depth 3 before it does
anything. Name it: lift `visit := func(...)` to a method or a top-level
function taking explicit state (a small struct), especially for recursive
walks (DFS cycle detection, tree traversal). The state struct also makes the
walk testable.

## Linters

| Linter | What | Default |
|---|---|---|
| `nestif` | complexity of nested `if` statements | `min-complexity: 5` |
| `gocognit` | cognitive complexity (weights nesting) | `min-complexity: 30`; 10–20 is the commonly recommended setting |
| `gocyclo` / `cyclop` | cyclomatic complexity | `gocyclo` 30 |
| `revive` rules `indent-error-flow`, `superfluous-else` | `else` after `return` | in revive's default rule set |
| `revive` rule `early-return` | inversion opportunities | opt-in |
| `funlen` | function length | 60 lines / 40 statements |

gofmt indentation is a reliable proxy for nesting, which is why
`scripts/nesting_depth.py` reads Go by indentation. It counts `if`, `for`,
`switch`, `select`, `else` and `func` literals; `case` clauses do not add a
level.
