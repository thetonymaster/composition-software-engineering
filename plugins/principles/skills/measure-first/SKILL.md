---
name: measure-first
description: This skill should be used when performance comes up — the user says "make this faster", "optimize", "this is slow", "is X faster than Y", "should I use a set/map here", "profile this", "benchmark this", or a review comment demands a micro-optimization — and before trading readability for speed. Covers the velocity/adaptability/performance trade-off, the measure-first workflow, and profiling and benchmarking tools for Go, Python, Elixir, TypeScript, Java, Rust and C#.
---

# Measure first

Performance is one corner of a triangle with **velocity** (how fast features
ship) and **adaptability** (how easily the code changes). Early in a project,
favour the other two. Spend readability on speed only where a measurement
says the speed matters.

Intuition about what is fast is unreliable:

- `++i` vs `i++` in C++ — compiled with optimisation, identical assembly.
- A set vs an array for "is this user logged in" — the common intuition is
  that a linear scan of a small array beats a hash set, because contiguous
  integers are cache-friendly and need no hashing. In Go 1.27 on an M-series
  Mac it lost: a 50-element `map[int]bool` lookup measured 3.5 ns against
  11.8 ns for a slice scan to element 42. The answer depends on language,
  size and data layout; that is the point — benchmark the case at hand
  instead of quoting either result.
- GTA V Online loading — a player profiled the binary without source and
  found startup dominated by processing one JSON file: `sscanf` re-scanning
  the whole string per token, plus a linear-scan dedup of the parsed items.
  Fixing those two quadratic hotspots cut load times by about 70%.
- Facebook shipped on PHP. The cost came later and was paid with a compiler
  (HipHop) and a language (Hack) — after velocity had already won the market.

## The workflow

Follow in order; do not skip to step 5.

1. **Confirm a real problem.** A user-visible latency, a missed SLO, a cost
   line, a timeout. "This looks slow" is not one. Write down the target
   ("p99 under 200 ms", "batch under 10 min").
2. **Measure it** in conditions resembling production: realistic data sizes,
   warm caches where production has them. Record the baseline number.
3. **Look for an 80% move first** — a better algorithm or data structure,
   removing repeated work (the GTA JSON), batching IO, caching a pure result.
   These dwarf micro-tuning.
4. **Profile to find the hotspot.** Optimise the function the profiler names,
   not the one that looks expensive.
5. **Only then think about the machine** — allocations, cache locality,
   copying, lock contention — and only inside the hotspot.
6. **Re-measure** against the baseline with enough runs to see variance.
   Keep the change only if it moves the number that mattered in step 1.

## In code review

- A comment like "use X, it's faster" without a measurement is a style
  opinion. Ask for the benchmark or the profile, or drop it.
- Readability wins ties. A 3% gain in a function that is 1% of runtime is a
  0.03% gain.
- Asymptotics still matter where input is unbounded: an O(n²) loop over
  user-controlled input is a correctness risk (timeouts, DoS), not a
  premature-optimisation question. Flag it.
- An optimisation that lands should carry its evidence: the benchmark in the
  repo, numbers in the commit message.

## Benchmarks that lie

- The compiler removed the work (result unused) — use the language's sink /
  keep-alive mechanism.
- Measuring the setup, not the operation.
- One run, no variance. Compare distributions (`benchstat`, Benchee's
  statistics, `pyperf`), not single numbers.
- Laptop on battery, thermal throttling, a noisy neighbour. Note the
  environment; prefer comparing A/B in the same session.
- Microbenchmark data that fits in L1 when production data does not.

## Checklist

1. What is the measured problem and the target number?
2. What did the profiler name as the hotspot?
3. Is there an algorithm/data-structure/IO-batching fix before micro-tuning?
4. Before/after numbers, with variance, from the same environment?
5. What readability was spent, and is the gain worth it?

## Language references

- **`references/go.md`** — `testing.B` and `b.Loop()`, `benchstat`, `pprof`
  (CPU, heap, mutex), `-benchmem`, escape analysis, PGO, trace.
- **`references/python.md`** — `timeit`, `pyperf`, `pytest-benchmark`,
  `cProfile` / `profiling.tracing`, the 3.15 sampling profiler, `py-spy`,
  `scalene`, `memray`.
- **`references/elixir.md`** — Benchee, `mix profile.tprof` / `eprof` /
  `fprof`, `:observer`, `recon`, flame graphs, BEAM-specific traps.
- **`references/typescript.md`** — mitata/tinybench, V8 traps (dead code,
  monomorphic benchmarks, deopts), `--cpu-prof`/`--prof`, 0x, clinic.
- **`references/java.md`** — why `nanoTime` loops lie, JMH (`@Param`,
  `Blackhole`, `-prof gc`), JFR/`jcmd`, async-profiler, VisualVM.
- **`references/rust.md`** — release vs debug, criterion with
  `std::hint::black_box` and baselines, cargo-flamegraph, samply, dhat.
- **`references/csharp.md`** — BenchmarkDotNet (`[MemoryDiagnoser]`, Release
  builds), dotnet-counters, dotnet-trace, PerfView, tiered compilation/PGO.

Related: `principles-audit`.
