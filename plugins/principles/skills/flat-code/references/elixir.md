# Flat code in Elixir

Elixir has better tools against nesting than most languages — pattern-matched
function heads, guards, `with`, and pipelines — so nested `case`/`if` is
usually a sign those tools were skipped.

## Multi-clause functions instead of `case` inside a function

```elixir
# Avoid
def process(download) do
  case download.state do
    :pending ->
      if download.retries < 3 do
        start(download)
      else
        fail(download)
      end

    :in_progress ->
      poll(download)
  end
end

# Prefer
def process(%{state: :pending, retries: r} = d) when r < 3, do: start(d)
def process(%{state: :pending} = d), do: fail(d)
def process(%{state: :in_progress} = d), do: poll(d)
```

Each clause is a guard clause. Order clauses from most to least specific.

## `with` for the happy path

```elixir
# Avoid: nested case per step
case fetch(id) do
  {:ok, raw} ->
    case parse(raw) do
      {:ok, doc} -> validate(doc)
      {:error, _} = err -> err
    end
  {:error, _} = err -> err
end

# Prefer
with {:ok, raw} <- fetch(id),
     {:ok, doc} <- parse(raw) do
  validate(doc)
end
```

Without an `else`, a non-matching value is returned as is — usually what you
want. An `else` block that has to work out which step failed from the error
shape is a smell (Elixir docs anti-pattern "Complex `else` clauses in
`with`"): normalise errors inside each step's private function instead.

## Pipelines and extraction

A pipeline is a sequence of extracted steps. Keep anonymous functions in
`Enum.map/2` and friends to one line; a multi-line `fn` with a `case` inside
is the place to extract a named private function, which also gets its own
pattern-matched clauses.

## Credo checks

| Check | Default |
|---|---|
| `Credo.Check.Refactor.Nesting` | `max_nesting: 2` (control structures inside a function body) — matches depth 3 counting the body |
| `Credo.Check.Refactor.CyclomaticComplexity` | `max_complexity: 9` |
| `Credo.Check.Refactor.ABCSize` | opt-in |
| `Credo.Check.Refactor.NegatedConditionsWithElse` | `if !x ... else` → swap branches |
| `Credo.Check.Refactor.CondStatements` | `cond` with one condition plus `true` → `if` |
| `Credo.Check.Refactor.RedundantWithClauseResult` | trailing `{:ok, x} <- f()` with `do {:ok, x}` |

`scripts/nesting_depth.py` reads mix-formatted Elixir by indentation and
counts `if`, `unless`, `case`, `cond`, `with`, `for`, `receive`, `try` and
multi-line `fn ->`; clause lines (`pattern ->`, `else`, `rescue`) do not add
a level.
