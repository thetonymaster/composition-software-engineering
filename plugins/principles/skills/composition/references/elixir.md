# Composition in Elixir

Elixir has no inheritance and no objects, so composition is the default: data
is plain structs, behaviour is functions. The failure modes move to three
places — `use` macros, process state, and Application env.

## Behaviours vs protocols: pick by who varies

| | Behaviour (`@callback`) | Protocol (`defprotocol`) |
|---|---|---|
| Dispatch on | a module chosen by the caller/config | the **data type** of the first argument |
| Example | `Storage` with `S3`, `SFTP`, `WebDAV` adapters | `ImageFile.save/2` for `%Png{}`, `%Jpeg{}` |
| Second implementation | another adapter module | another struct |
| Testing | Mox mock of the behaviour | a test struct implementing it |

The tier example maps to a protocol, because the variation is the data:

```elixir
defprotocol Features do
  @spec has_feature?(t, String.t()) :: boolean
  def has_feature?(user, feature)
end

defmodule PaidUser, do: defstruct [:user, :auth, :payment]
defmodule TrialUser, do: defstruct [:user, :auth]
defmodule GuestUser, do: defstruct [:user]

defimpl Features, for: PaidUser do
  def has_feature?(%{user: u, auth: a, payment: p}, f),
    do: Auth.logged_in?(a) and Payment.valid?(p) and Lookup.user(u.id, f)
end

defimpl Features, for: TrialUser do
  def has_feature?(%{user: u, auth: a}, f), do: Auth.logged_in?(a) and Lookup.user(u.id, f)
end

defimpl Features, for: GuestUser do
  def has_feature?(_guest, f), do: Lookup.guest(f)
end
```

A behaviour with exactly one implementing module and no Mox mock or second
adapter planned is speculative — call the module directly.

## `use` is the inheritance analogue

`use Foo` runs `Foo.__using__/1`, which can inject functions, imports,
attributes and `defoverridable` defaults into the caller. That is a base class
with overridable methods, and it brings the base-class problems: the reader
must open `Foo` to know what the module contains, and injected definitions can
conflict with local ones.

The Elixir docs list "`use` instead of `import`" as a macro anti-pattern: when
`alias` or `import` suffices, use those (lexically scoped, inject nothing).

Review signals:

- `use MyApp.Base` whose `__using__` defines functions with
  `defoverridable` → a template-method hierarchy. Prefer a behaviour plus
  explicit delegation, or plain functions the caller invokes.
- A `__using__` that only does `import`/`alias` → replace with those lines.
- Framework `use` (`use GenServer`, `use Phoenix.Controller`, `use Ecto.Schema`)
  is fine; it is the framework's documented contract.

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| External service | behaviour + adapter passed as an argument or option | `Mox` mock (`async: true` safe) |
| HTTP | `Req` with a `:plug` option | `Req.Test` stubs |
| Time | `now` function/option, or `DateTime` passed in | fixed value |
| Files | path passed from the edge; core functions take binaries/streams | in-memory binaries |

Prefer passing the adapter explicitly (`opts[:storage] || default`) at the
boundary to reading it from Application env deep inside a function — see the
`dependency-injection` skill for the trade-off.

## Process and global state

- **A named GenServer is a singleton.** `GenServer.start_link(__MODULE__, arg,
  name: __MODULE__)` means two configurations cannot coexist and tests must
  run `async: false`. Accept a `:name` option and pass the pid/name through.
- **`Application.get_env` inside library functions** is a global read at call
  time. Read config once at the edge (application start, or the caller's
  options) and pass values down. Library guidelines in the Elixir docs say to
  avoid Application env for library configuration.
- **`:persistent_term` and ETS named tables** are global; acceptable for
  read-mostly caches with an owner process, a finding otherwise.
- **Processes for code organisation** (a GenServer that holds no state, or
  serialises calls for no reason) is an anti-pattern in the Elixir docs'
  process anti-patterns: use plain modules and functions.

## Ordering as data

Pattern matching makes type-state cheap: return a distinct struct after each
stage and match on it.

```elixir
%Catalog{} = cat
{:ok, %ResolvedGraph{} = graph} = Catalog.resolve(cat, scope)
cycles = ResolvedGraph.cycles(graph)
```

`ResolvedGraph.cycles/1` cannot accept a `%Catalog{}` — a `FunctionClauseError`
at runtime, and with Elixir 1.18+ set-theoretic types, increasingly a compile
warning. It is never a silently empty answer.

## Tooling

- `credo`: `Credo.Check.Refactor.ModuleDependencies`, `Readability.Specs`.
- `mix xref graph --label compile-connected` — `use` and macros create
  compile-time dependencies; this finds the ones that cascade recompiles.
- `dialyzer` (via `dialyxir`) to check behaviour callbacks are implemented
  with matching specs.
