# Audit commands: C#

`$FILES` = changed `.cs` files (`git diff --name-only main...HEAD -- '*.cs'`).
Adjust `src/` to the production source root and exclude test projects where
noted. Every hit is a lead to read.

## Analyzers

Code-metrics rules are off by default and are not enabled by
`AnalysisMode=All`; turn them on by ID. For a one-off pass, add this to
`.editorconfig` in a scratch worktree, not on the branch under review:

```ini
[*.cs]
dotnet_diagnostic.CA1501.severity = warning   # inheritance depth (default 5)
dotnet_diagnostic.CA1502.severity = warning   # cyclomatic complexity (default 25)
dotnet_diagnostic.CA1852.severity = warning   # seal internal types
dotnet_diagnostic.CA2211.severity = warning   # visible non-constant static fields
dotnet_diagnostic.CA2214.severity = warning   # virtual call in constructor
dotnet_diagnostic.IDE0063.severity = warning  # simple using statement
dotnet_diagnostic.IDE0066.severity = warning  # switch expression
```

Thresholds go in `CodeMetricsConfig.txt` (`CA1502: 10`, `CA1501: 3`),
included as `<AdditionalFiles Include="CodeMetricsConfig.txt" />`.

```bash
dotnet build --no-incremental -p:EnforceCodeStyleInBuild=true 2>&1 \
  | grep -oE '[^ ]+\.cs\([0-9]+,[0-9]+\): warning (CA|IDE|RCS|S)[0-9]+[^[]*' | sort -u
```

`EnforceCodeStyleInBuild` is required for IDE rules on the command line.
Respect the project's own `.editorconfig`, `Directory.Build.props` and
`AnalysisLevel`; the settings above are a one-off pass. If the project uses
Roslynator or SonarAnalyzer.CSharp, include RCS1211 and S134/S3776.

## Composition / DI

```bash
# Interfaces, then count implementers of each (second implementation?)
grep -rnE '^\s*(public |internal )?(partial )?interface I[A-Z]\w*' --include='*.cs' src/
grep -rnE '(class|record|struct) \w+.*:.*\bINAME\b' --include='*.cs' .   # implementers of INAME, tests included

# Inheritance: abstract bases, overrides that refuse, hiding, protected state
grep -rnE '\babstract (partial )?class\b' --include='*.cs' src/
grep -rnE 'throw new (NotSupportedException|NotImplementedException)' --include='*.cs' src/
grep -rnE '\b(public|protected|internal) new\b|\bnew (public|protected|internal)\b' --include='*.cs' src/
grep -rnE '^\s*protected (readonly |static )*[A-Za-z_][][A-Za-z0-9_<>,.? ]* _?\w+ *(=|;)' --include='*.cs' src/

# Static state and singletons
grep -rnE '^\s*((public|internal|private|protected) )?static [A-Za-z_][][A-Za-z0-9_<>,.? ]* \w+ *(=|;)' --include='*.cs' src/ \
  | grep -vE '\b(readonly|const)\b'
grep -rnE 'static .*\bInstance\b|static readonly Lazy<|ModuleInitializer\]' --include='*.cs' src/

# Service locator and construction below the composition root
grep -rnE 'IServiceProvider|GetRequiredService<|GetService<|ActivatorUtilities' --include='*.cs' src/ | grep -v 'Program.cs'
grep -rnE 'new HttpClient\(|DateTime(Offset)?\.(Utc)?Now\b|Environment\.GetEnvironmentVariable|\bFile\.|\bDirectory\.|Random\.Shared|IConfiguration\b' \
  --include='*.cs' src/ | grep -v 'Program.cs'

# Lifetimes: list registrations, then check singletons for scoped constructor parameters
grep -rnE 'Add(Keyed)?(Singleton|Scoped|Transient)\b' --include='*.cs' src/

# Tests reaching private members
grep -rnE 'BindingFlags\.NonPublic|InternalsVisibleTo' --include='*.cs' --include='*.csproj' .
```

Captive dependencies also surface at startup when
`ValidateScopes`/`ValidateOnBuild` are on; the host enables both only in
the Development environment.

## Flat code

```bash
python3 <plugin-root>/skills/flat-code/scripts/nesting_depth.py --max 3 $FILES
grep -nE -B4 '^\s*else\b' $FILES | grep -E 'return|throw|continue|break'   # then read: else after exit?
```

## Measure first

```bash
# Benchmarks: is there a project, and did the diff add any?
grep -rl 'BenchmarkDotNet' --include='*.csproj' .
git diff main...HEAD -- '*.cs' | grep -nE '^\+.*\[Benchmark'
# Low-level tricks in the diff that need evidence
git diff main...HEAD -- '*.cs' \
  | grep -nE '^\+.*(\bunsafe\b|stackalloc|ArrayPool|MemoryMarshal|Unsafe\.|AggressiveInlining|SkipLocalsInit|\[StructLayout)'
```

If a benchmark covers touched code, run it on both sides in Release:

```bash
dotnet run -c Release --project bench/Bench.csproj -- --filter '*LoggedIn*'
git worktree add --detach /tmp/audit-base main   # --detach: main is usually checked out elsewhere
(cd /tmp/audit-base && dotnet run -c Release --project bench/Bench.csproj -- --filter '*LoggedIn*')
git worktree remove /tmp/audit-base
```

`--filter` requires the bench `Program` to use
`BenchmarkSwitcher.FromAssembly(typeof(Program).Assembly).Run(args)`.
Compare `Mean ± Error` and `Allocated` from each run's
`BenchmarkDotNet.Artifacts/results/`. Use a worktree for the base, never
`git stash`: the stash stack is shared across worktrees and sessions.
