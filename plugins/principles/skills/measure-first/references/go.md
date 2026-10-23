# Measuring Go

## Benchmarks

```go
func BenchmarkLoggedIn(b *testing.B) {
	users := makeUsers(50) // setup is outside the timed loop
	for b.Loop() {         // Go 1.24+: keeps results alive, times only the loop
		isLoggedIn(users, 42)
	}
}
```

- `b.Loop()` (Go 1.24+) replaces `for i := 0; i < b.N; i++`: setup before it
  is excluded automatically and the compiler cannot dead-code-eliminate the
  call. On older Go, assign results to a package-level sink and call
  `b.ResetTimer()` after setup.
- `go test -bench=LoggedIn -benchmem -count=10 ./pkg > new.txt` — `-benchmem`
  reports allocations; `-count` gives `benchstat` samples.
- `benchstat old.txt new.txt` (`golang.org/x/perf/cmd/benchstat`) reports the
  delta and whether it is statistically significant. A `~` means no
  detectable difference: the change did nothing measurable.
- Sub-benchmarks with `b.Run(fmt.Sprintf("n=%d", n), ...)` across sizes
  reveal the crossover point — the array-vs-set example flips at some `n`;
  find it instead of arguing.

## Profiling

| Question | Tool |
|---|---|
| Where is CPU time spent? | `go test -cpuprofile cpu.out` or `net/http/pprof` `/debug/pprof/profile`; `go tool pprof -http=: cpu.out` |
| What allocates? | `-memprofile mem.out`; pprof `-sample_index=alloc_space` |
| Lock contention? | `runtime.SetMutexProfileFraction`, `/debug/pprof/mutex`, `/debug/pprof/block` |
| Latency, scheduling, GC pauses? | `go test -trace trace.out`; `go tool trace` |
| Why does this escape to the heap? | `go build -gcflags=-m` |

In production on AKS, a continuous profiler (Pyroscope, Grafana Cloud
Profiles, Dynatrace) gives the profile under real load; compare the hotspot
there with the one the local benchmark targets.

## Profile-guided optimisation

PGO (Go 1.21+): put a representative CPU profile at `default.pgo` in the
main package; `go build` uses it automatically. Typically a few percent —
exactly the kind of gain to take only after the 80% moves.

## Common 80% moves in Go

- Pre-size slices and maps (`make([]T, 0, n)`) in hot loops.
- Reuse buffers (`bytes.Buffer.Reset`, `sync.Pool` only after a profile shows
  allocation pressure).
- Batch IO and round trips; stream with `io.Reader` instead of `io.ReadAll`.
- `strings.Builder` over repeated `+` in loops.
- Avoid `reflect`/`encoding/json` in a measured hot path; consider generated
  codecs only after measuring.
