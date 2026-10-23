# Measuring C# / .NET

## Benchmarks

```csharp
[MemoryDiagnoser]
public class LoggedInBenchmarks
{
    private int[] _array = [];
    private HashSet<int> _set = [];

    [Params(10, 50, 1000)]
    public int N;

    [GlobalSetup]
    public void Setup()   // excluded from the measurement
    {
        _array = Enumerable.Range(0, N).ToArray();
        _set = _array.ToHashSet();
    }

    [Benchmark(Baseline = true)]
    public bool ArrayScan() => Array.IndexOf(_array, N - 1) >= 0;

    [Benchmark]
    public bool SetLookup() => _set.Contains(N - 1);
}

// Program.cs
BenchmarkRunner.Run<LoggedInBenchmarks>();
```

- Run in Release: `dotnet run -c Release`. Debug builds can be 10–100x
  slower; BenchmarkDotNet's docs also say not to attach a debugger.
- Return the result from each `[Benchmark]` method; an unused result can be
  dead-code-eliminated by the JIT.
- `[MemoryDiagnoser]` adds allocated bytes and GC counts per operation —
  often the real cost in a hot path.
- `[Params]` across sizes shows the crossover point: the array-vs-set
  example flips at some `N`; find it instead of arguing.
- Read `Mean` with `Error`/`StdDev`, and `Ratio` against the baseline.
  Overlapping intervals mean no detectable difference. For before/after
  across commits, run both builds in the same session on the same machine.

## Profiling

| Question | Tool |
|---|---|
| First look: CPU, GC rate, allocation rate, thread pool, lock contention | `dotnet-counters monitor --process-id <PID> --counters System.Runtime` |
| Where is time spent? | `dotnet-trace collect --process-id <PID>` → `.nettrace`; `--format Speedscope` for speedscope.app; open `.nettrace` in PerfView or Visual Studio |
| What allocates? | `dotnet-trace collect --profile gc-verbose`; `[MemoryDiagnoser]` in a benchmark |
| What is on the heap / leaking? | `dotnet-gcdump collect --process-id <PID>`; `dotnet-dump` for a full dump |
| Deep CPU + GC analysis (Windows) | PerfView (ETW) |
| IDE profilers | Visual Studio Performance Profiler, JetBrains dotTrace / dotMemory |

Install the CLI tools with `dotnet tool install --global dotnet-trace`
(same for `dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`); `ps` lists
attachable processes. `dotnet-trace` profile names changed across versions
(`cpu-sampling` was removed); run `dotnet-trace list-profiles` before
copying a command. On Linux and macOS the tool and the target must share
`TMPDIR`.

In production on AKS, a continuous profiler or APM (Dynatrace, Grafana
Pyroscope) gives the profile under real load; compare its hotspot with the
one the local benchmark targets.

## Runtime notes before blaming the code

- Tiered compilation and Dynamic PGO (on by default since .NET 8) mean the
  first calls run unoptimised code. Measure steady state, not the first
  request; BenchmarkDotNet handles warm-up.
- Server vs workstation GC and container CPU/memory limits change
  throughput; note them in the environment line.

## Common 80% moves in .NET

- Algorithmic: `HashSet<T>`/`Dictionary<TKey,TValue>` for large membership
  tests; `FrozenDictionary`/`FrozenSet` (.NET 8+) for read-mostly lookups.
- Remove repeated work: hoist `Regex` construction (or use the
  `[GeneratedRegex]` source generator), serializer options and parsing out
  of loops.
- Batch IO: one query instead of N (EF Core `Include`, projections with
  `Select`, `AsNoTracking` for reads); `Task.WhenAll` for independent
  IO-bound calls; stream with `IAsyncEnumerable<T>` instead of buffering.
- Allocation: `StringBuilder` over `+` in loops, pre-sized collections,
  `Span<T>`/`ArrayPool<T>` only after `[MemoryDiagnoser]` or a trace shows
  allocation pressure.
- LINQ in a measured hot path can cost delegates and enumerators; rewrite
  that loop by hand only with a benchmark showing the gain.
