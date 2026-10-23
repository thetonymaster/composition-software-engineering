# Measuring Elixir

## Benchmarks: Benchee

```elixir
build = fn n ->
  list = Enum.to_list(1..n)
  {list, MapSet.new(list)}
end

Benchee.run(
  %{
    "list member?" => fn {list, _set} -> Enum.member?(list, 42) end,
    "MapSet member?" => fn {_list, set} -> MapSet.member?(set, 42) end
  },
  inputs: %{"small" => build.(50), "large" => build.(50_000)},
  memory_time: 2
)
```

- Build inputs outside the benchmark functions (as above, or with
  `before_scenario`), or the setup is what gets measured. With `inputs:`,
  each job receives the input as its single argument.
- `memory_time:` reports allocations; `reduction_time:` reports BEAM
  reductions, a CPU-independent work measure.
- Run under `MIX_ENV=prod` — compile-time config, Logger level and debug
  options usually differ from `dev`; check `consolidate_protocols` has not
  been disabled for the env being measured.
- Benchee reports median, deviation and comparison; save runs with
  `save:`/`load:` to compare before and after.

## Profiling

| Question | Tool |
|---|---|
| Call counts, time, or allocations per function | `mix profile.tprof -e "MyApp.run()"` (OTP 27+; unified replacement for `eprof`/`cprof`) |
| Time per function (older OTP) | `mix profile.eprof`, low-overhead counts with `mix profile.cprof` |
| Full call tree with own vs accumulated time | `mix profile.fprof` — detailed but slows the program a lot |
| Flame graph | `eflambe` (writes for speedscope / flamegraph tools) |
| Live system: mailboxes, memory, schedulers | `:observer.start()`, or `observer_cli` / `:recon` on a remote node |
| Which process is hot / leaking | `:recon.proc_count(:reductions, 10)`, `:recon.proc_count(:memory, 10)` |

## BEAM-specific traps

- **A single GenServer as a bottleneck.** Every call serialises through one
  mailbox. Check `:erlang.process_info(pid, :message_queue_len)` before
  optimising the callback; the fix is often reading from ETS or partitioning,
  not faster code.
- **Large binaries and messages** are copied between processes (except
  refc binaries over 64 bytes). Sending big terms to a GenServer and back
  costs more than the work.
- **`length/1` and `++`** are O(n); `Enum.count/1` on a list too. Fine for
  small lists — measure before replacing.
- **String concatenation in loops**: build iodata and write once.
- **N+1 queries in Ecto** are the usual 80% move: `Repo.preload`/joins.
