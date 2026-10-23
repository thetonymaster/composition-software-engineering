# Measuring TypeScript (Node)

## Benchmarks

- **`performance.now()`** (global, no import) for a one-off timing only. A
  single loop measures V8's interpreter and baseline tiers before the
  optimising compiler kicks in; use a library for comparisons.
- **`mitata`** for A/B comparisons: warms up, reports avg/min/max and
  percentiles, sweeps input sizes with `.args()`, and `do_not_optimize()`
  keeps results alive. Run with `node --expose-gc` so it can collect garbage
  between benchmarks.
- **`tinybench`** (`new Bench().add(name, fn)`, `await bench.run()`,
  `console.table(bench.table())`) reports mean ± margin of error and
  percentiles. Keep benchmark files in the repo next to the code they
  measure, with a `bench` script in `package.json`.

```ts
import { bench, do_not_optimize, run } from "mitata";

for (const n of [10, 50, 1_000]) {
  const list = Array.from({ length: n }, (_, i) => i); // setup: not timed
  const set = new Set(list);
  bench(`array.includes n=${n}`, () => do_not_optimize(list.includes(n - 8)));
  bench(`set.has n=${n}`, () => do_not_optimize(set.has(n - 8)));
}

await run(); // top-level await: an ES module (.mts, or "type": "module")
```

Only the closure is timed. Sweeping `n` finds the crossover instead of
arguing about it.

## V8 traps

- **Dead code.** A result nobody reads can be optimised away; pass it to
  `do_not_optimize` or accumulate it.
- **Monomorphic benchmarks.** A benchmark that feeds one object shape
  measures an inline-cached fast path; production call sites that see many
  shapes deoptimise. Feed realistic, varied data.
- **Deopts.** `node --trace-opt --trace-deopt script.js` prints what V8
  optimised and why it bailed out. `--allow-natives-syntax` intrinsics
  (`%OptimizeFunctionOnNextCall`) are for experiments, never for numbers.
- **GC.** Allocation cost lands in GC pauses, not in the line that allocates:
  `node --trace-gc` shows them.
- **Wrong code under test.** Benchmark the JavaScript Node actually runs (the
  build output, or Node's built-in type stripping), not a dev loader that
  type-checks or transpiles on the fly.

## Profiling

| Question | Tool |
|---|---|
| Where is CPU time spent? | `node --cpu-prof app.js` writes a `.cpuprofile`; open it in Chrome DevTools (Performance) or VS Code |
| Same, interactively | `node --inspect app.js`, then `chrome://inspect` |
| Flame graph of a server under load | `npx 0x -- node app.js`; `clinic flame -- node app.js` driven by `autocannon` |
| Event loop blocked? IO or CPU? | `clinic doctor -- node app.js`; `monitorEventLoopDelay()` from `node:perf_hooks` |
| V8 tick profile | `node --prof app.js`, then `node --prof-process isolate-*.log` |
| Allocations, leaks | `node --heap-prof` (`.heapprofile`); `--heapsnapshot-signal=SIGUSR2` or `v8.writeHeapSnapshot()` |

In production on AKS, a continuous profiler (Pyroscope, Grafana Cloud
Profiles, Dynatrace) gives the profile under real load; compare its hotspot
with the one the local benchmark targets.

## Common 80% moves in Node

- `Set`/`Map` membership instead of `includes`/`find` inside a loop over
  unbounded input — that is O(n²).
- `Promise.all` for independent awaits instead of `await` in a loop; one
  query instead of N.
- Hoist `new RegExp`, `JSON.parse` of constant data and `Intl.*Format`
  construction out of loops — the GTA-style repeated parse.
- Stream (`fs.createReadStream`, `stream/promises` `pipeline`) instead of
  reading whole files into memory.
- CPU-bound work off the event loop with `worker_threads` — only after
  event-loop delay shows the loop is blocked.
