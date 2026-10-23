# Measuring Java

## Why a `System.nanoTime()` loop lies

The JVM starts interpreted, then the JIT compiles hot methods (C1, then C2)
using profiles gathered so far. A hand-rolled timing loop measures a moving
target:

- **Warmup.** Early iterations run interpreted or C1 code; the number
  depends on how many iterations ran before the timer started.
- **Dead-code elimination.** If the result is unused, C2 may delete the
  work. Measured with JMH (JDK 17.0.20, Apple Silicon): 100 `Math.sqrt`
  steps took 177 ns/op when the result was returned and 3.4 ns/op when it was
  discarded.
- **Constant folding and loop hoisting** of inputs the JIT can see are
  constant; on-stack replacement compiling the loop body differently from
  the real call site.
- **GC and one JVM.** One run in one JVM, with GC pauses landing anywhere,
  has no variance estimate.

## JMH

```java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@State(Scope.Benchmark)
@Fork(1) @Warmup(iterations = 3, time = 1) @Measurement(iterations = 5, time = 1)
public class LoggedInBench {
    @Param({"10", "50", "1000"}) int n;   // sweep sizes to find the crossover
    int[] array; Set<Integer> set; int target;

    @Setup public void setup() {           // not timed
        array = IntStream.range(0, n).toArray();
        set = IntStream.range(0, n).boxed().collect(Collectors.toSet());
        target = n * 4 / 5;
    }

    @Benchmark public boolean arrayScan() {
        for (int id : array) if (id == target) return true;
        return false;
    }

    @Benchmark public boolean hashSet() { return set.contains(target); }
}
```

- Return the result, or pass it to a `Blackhole` parameter
  (`bh.consume(x)`), so the JIT cannot drop it. Read inputs from `@State`
  fields, not constants.
- Run from the JMH Maven archetype (`org.openjdk.jmh:jmh-java-benchmark-archetype`)
  or the `me.champeau.jmh` Gradle plugin; `java -jar target/benchmarks.jar
  LoggedInBench -rf json`.
- JMH prints `Score ± Error` (99.9% confidence interval). Overlapping
  intervals between A and B mean no detectable difference. Use more forks
  (`-f 3`) before trusting a small delta.
- `-prof gc` adds `gc.alloc.rate.norm` (bytes per operation). In the
  benchmark above `hashSet` allocated 16 B/op: `contains(target)` boxes an
  `int` outside the `Integer` cache. Allocation like this is invisible
  without measuring.
- In the same run: at n=50 the array scan took 4.8 ns and the `HashSet`
  1.2 ns; at n=10 they were within error (1.5 vs 1.2 ± 0.3). Benchmark the
  case at hand.

## Profiling

| Question | Tool |
|---|---|
| Where is CPU time spent, low overhead, in production? | JFR: `java -XX:StartFlightRecording=duration=60s,filename=rec.jfr,settings=profile ...`; on a running JVM `jcmd <pid> JFR.start name=r settings=profile`, then `jcmd <pid> JFR.dump name=r filename=rec.jfr` |
| Read a recording on the command line | `jfr summary rec.jfr`; `jfr print --events jdk.ExecutionSample rec.jfr` (`--json` for tooling). `jfr view` exists only from JDK 21 |
| Read a recording in a GUI | JDK Mission Control (`jmc`), separate download |
| CPU / allocation / lock flame graph | async-profiler: `asprof -d 30 -e cpu -f flame.html <pid>` (`-e alloc`, `-e lock`); as an agent `-agentpath:/path/libasyncProfiler.so=start,event=cpu,file=flame.html` |
| Profile inside a JMH run | `-prof async:libPath=/path/libasyncProfiler.so`; `-prof jfr`; `-prof gc` |
| Heap contents, leak suspects | `jcmd <pid> GC.heap_dump heap.hprof`, open in VisualVM or Eclipse MAT |
| Quick look at threads, CPU, heap of a local JVM | VisualVM (separate download since JDK 9): sampler, heap dump, thread dump |

async-profiler avoids the safepoint bias of JMX-based samplers (VisualVM's
sampler, JMH `-prof stack`): those can only observe threads at safepoints, so
hot loops without one are under-reported. Confirm a surprising VisualVM
hotspot with JFR or async-profiler before rewriting.

On AKS, a continuous profiler (Pyroscope's Java agent, which wraps
async-profiler; Dynatrace) gives the profile under real load; compare its
hotspot with the one the benchmark targets.

## Common 80% moves in Java

- Algorithmic: `HashMap`/`HashSet` for large membership tests, no
  `List.contains`/`remove` inside loops over the same list.
- Remove repeated work: hoist `Pattern.compile`, `DateTimeFormatter.ofPattern`,
  `ObjectMapper` construction out of hot paths; they are thread-safe and
  reusable.
- Batch IO: one query instead of N (JPA `JOIN FETCH`, JDBC `addBatch`),
  buffered streams, connection pooling.
- Boxing in hot loops: `int[]`/`IntStream` over `List<Integer>` once a
  profile shows allocation pressure.
- `StringBuilder` over `+=` in loops; size collections when the count is
  known.
- GC and heap flags (`-Xmx`, collector choice) only after JFR shows GC time
  matters.
