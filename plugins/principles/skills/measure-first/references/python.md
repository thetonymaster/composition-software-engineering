# Measuring Python

## Benchmarks

- **`timeit`** for a one-off: `python -m timeit -s "users=list(range(50))" "42 in users"`.
  Compare with `-s "users=set(range(50))"` — measure the logged-in example
  rather than assume.
- **`pyperf`** for real comparisons: runs worker processes, calibrates loops,
  reports mean ± std dev, and `python -m pyperf compare_to old.json new.json`
  says whether a difference is significant.
- **`pytest-benchmark`** to keep benchmarks in the test suite:
  `def test_lookup(benchmark): benchmark(is_logged_in, users, 42)`;
  `--benchmark-compare` against a saved run.

Disable CPU frequency scaling noise where possible (`pyperf system tune` on
Linux); on a laptop, compare A/B in the same session.

## Profiling

| Question | Tool |
|---|---|
| Which functions take time (deterministic)? | `python -m cProfile -o out.prof script.py`; view with `snakeviz` or `pstats`. In 3.15 the module also lives at `profiling.tracing`. |
| Low-overhead sampling, including a running process | 3.15+: `python -m profiling.sampling run script.py` / `attach PID` (PEP 799). Any version: `py-spy record -o flame.svg --pid PID` or `py-spy top`. |
| CPU vs native vs memory per line | `scalene script.py` |
| Allocations, leaks | `memray run script.py`; `memray flamegraph` |
| Line-level hotspot in one function | `line_profiler` (`kernprof -l`) |
| Native frames in `perf` | 3.12+: `python -X perf` makes Python frames visible to Linux `perf` |

Deterministic profilers (`cProfile`) inflate the cost of many small calls;
confirm a surprising hotspot with a sampling profiler before rewriting.

## Common 80% moves in Python

- Algorithmic: `set`/`dict` membership for large collections, `heapq`,
  `bisect`, avoiding quadratic `list.remove`/`in` in loops.
- Remove repeated work: hoist parsing/compiling out of loops (`re.compile`,
  the GTA-style repeated JSON parse), `functools.cache` on pure functions
  with bounded inputs.
- Batch IO: one query instead of N (ORM `select_related`/`prefetch`),
  `executemany`, concurrent requests with `asyncio`/`httpx.AsyncClient` for
  IO-bound fan-out.
- Push loops into C: `numpy`/`polars` vectorisation, `str.join`, built-ins.
- CPU-bound parallelism: processes (`concurrent.futures.ProcessPoolExecutor`);
  free-threaded builds (3.13t+) only after measuring that the workload and
  its C extensions benefit.
