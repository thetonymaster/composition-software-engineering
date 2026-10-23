# Measuring Rust

## Build mode first

Never time a debug build. `cargo run` and `cargo test` default to the `dev`
profile (no optimisation); iterator chains and generic code that are free in
release can be an order of magnitude slower there, and the ranking of two
approaches can flip. Measure with `--release`; `cargo bench` uses the `bench`
profile, which inherits from `release`.

## Benchmarks

```rust
// benches/lookup.rs
use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion};
use std::hint::black_box;

fn bench_logged_in(c: &mut Criterion) {
    let mut group = c.benchmark_group("logged_in");
    for n in [10, 50, 1_000] {
        let users: Vec<u32> = (0..n).collect(); // setup outside the timed closure
        group.bench_with_input(BenchmarkId::from_parameter(n), &users, |b, users| {
            b.iter(|| is_logged_in(black_box(users), black_box(42)))
        });
    }
    group.finish();
}

criterion_group!(benches, bench_logged_in);
criterion_main!(benches);
```

```toml
# Cargo.toml
[dev-dependencies]
criterion = "0.8"

[[bench]]
name = "lookup"
harness = false
```

- `std::hint::black_box` (1.66+) stops the compiler from constant-folding
  inputs or discarding results; it is best-effort, not a guarantee.
  `criterion::black_box` is deprecated in its favour.
- Benchmark across sizes (`BenchmarkId::from_parameter(n)`): the Vec-vs-set
  example flips at some `n`; find it instead of arguing.
- `cargo bench --bench lookup -- --save-baseline main` on the base, then
  `cargo bench --bench lookup -- --baseline main` on the change. Criterion
  reports the change with a confidence interval and says "No change in
  performance detected" when the difference is within noise. Pass `--bench
  NAME`: libtest harnesses reject criterion flags such as `--save-baseline`.
- `#[bench]` is nightly-only; `divan` is a stable alternative.

## Profiling

Profilers need symbols: `debug = true` under `[profile.release]` (or
`CARGO_PROFILE_RELEASE_DEBUG=true`); optimisation is unchanged.

| Question | Tool |
|---|---|
| Where is CPU time spent? | `cargo flamegraph --bin app` (crate `flamegraph`; perf on Linux, dtrace on macOS); `samply record ./target/release/app` (opens the Firefox Profiler; macOS and Linux) |
| Same, on Linux with full control | `perf record -g ./target/release/app`; `perf report` |
| What allocates? | the `dhat` crate (heap profiling in-process); `heaptrack` on Linux |
| What did the compiler emit for this function? | `cargo asm` (crate `cargo-show-asm`) |

In production on AKS, a continuous profiler (Pyroscope, Grafana Cloud
Profiles) shows the hotspot under real load; compare it with the benchmark's.

Build knobs (`lto = "fat"`, `codegen-units = 1`, PGO via `cargo-pgo`) cost
build time for a workload-dependent gain: take them after the 80% moves.

## Common 80% moves in Rust

- Buffer IO: wrap `File`/`TcpStream` in `BufReader`/`BufWriter`; unbuffered
  small reads and writes are a syscall each. `println!` in a hot loop locks
  stdout every call — take `stdout().lock()` once.
- Pre-size: `Vec::with_capacity`, `HashMap::with_capacity`,
  `String::with_capacity`.
- Remove repeated work: `.clone()` in loops where a borrow would do;
  compile regexes once.
- Hashing: the std `HashMap` hasher (SipHash) resists HashDoS. A faster
  hasher (`rustc-hash`'s `FxHashMap`, `ahash`) only after a profile names
  hashing, and never for attacker-controlled keys.
- Batch round trips; stream large inputs instead of `read_to_end`.
