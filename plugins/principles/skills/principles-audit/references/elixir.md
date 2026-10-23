# Audit commands: Elixir

`$FILES` = changed `.ex`/`.exs` files
(`git diff --name-only main...HEAD -- '*.ex' '*.exs'`). Every hit is a lead.

## Linters

```bash
mix credo --strict $FILES
mix credo explain lib/foo.ex:42          # reasoning for one finding
mix xref graph --label compile-connected  # compile-time coupling from use/macros
mix dialyzer                              # behaviour callbacks vs specs
```

Credo's `Refactor.Nesting` defaults to `max_nesting: 2`, which matches
depth 3 counting the function body.

## Composition / DI

```bash
# Behaviours and their implementations
grep -rn '@callback' lib/
grep -rn '@behaviour' lib/            # count implementers per behaviour

# `use` that injects code (inheritance analogue)
grep -rn 'defmacro __using__' lib/
grep -rn 'defoverridable' lib/

# Global state and singletons
grep -rnE 'name: __MODULE__' lib/
grep -rnE 'Application\.(get_env|fetch_env!|compile_env)' lib/
grep -rnE ':persistent_term|:ets\.new\(.*named_table' lib/

# Hardwired HTTP clients deep in contexts
grep -rnE '(HTTPoison|Req|Finch|Tesla)\.(get|post|request)' lib/

# Tests that patch instead of inject
grep -rnE 'Application\.put_env|:meck|Mimic\.' test/
grep -rn 'async: false' test/
```

## Flat code

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES
grep -nE '^\s*if .* do$' $FILES     # if-inside-function candidates for clause heads
```

## Measure first

```bash
grep -rln 'Benchee' bench/ test/ 2>/dev/null
git diff main...HEAD -- '*.ex' | grep -nE '^\+.*(:ets\.|:persistent_term|@compile|NIF|Rustler)'
```

For a claimed speedup, run the Benchee script on both sides under
`MIX_ENV=prod` and compare medians and deviation.
