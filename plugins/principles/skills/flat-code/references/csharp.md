# Flat code in C#

C# nests twice before the first statement — namespace (unless file-scoped)
and class — so every level inside a method is expensive on screen. The
extra traps are `using` and `try` blocks wrapping the whole body, and LINQ
chains that hide nesting inside lambdas.

## Guard clauses

```csharp
// Avoid
public Receipt Charge(User? user)
{
    if (user != null)
    {
        if (user.Active)
        {
            if (user.Quota > 0)
            {
                return Bill(user);
            }
            else
            {
                throw new QuotaExceededException(user.Id);
            }
        }
        else
        {
            throw new InactiveUserException(user.Id);
        }
    }
    throw new ArgumentNullException(nameof(user));
}

// Prefer
public Receipt Charge(User? user)
{
    ArgumentNullException.ThrowIfNull(user);
    if (!user.Active)
        throw new InactiveUserException(user.Id);
    if (user.Quota <= 0)
        throw new QuotaExceededException(user.Id);
    return Bill(user);
}
```

Argument guards are one-liners: `ArgumentNullException.ThrowIfNull` (.NET
6+), `ArgumentException.ThrowIfNullOrEmpty` (.NET 7+),
`ArgumentException.ThrowIfNullOrWhiteSpace` and
`ArgumentOutOfRangeException.ThrowIfNegative` / `ThrowIfZero` (.NET 8+).
They capture the parameter name automatically.

## Flatten `using` and `try`

```csharp
// Avoid: two blocks deep before any work happens.
using (var conn = Open())
{
    using (var tx = conn.BeginTransaction())
    {
        Apply(tx);
        tx.Commit();
    }
}

// Prefer: using declarations (C# 8+) dispose at the end of the scope.
using var conn = Open();
using var tx = conn.BeginTransaction();
Apply(tx);
tx.Commit();
```

Wrap only the call that throws the handled exception; use an exception
filter (`catch (HttpRequestException e) when (e.StatusCode == HttpStatusCode.NotFound)`)
instead of a `catch` containing an `if` that rethrows.

## Pattern matching and switch expressions

A switch expression maps one value to a result at one level; property
patterns replace nested null-and-flag checks.

```csharp
// Avoid
if (download != null)
{
    if (download.State == State.Pending) { StartPending(download); }
    else if (download.State == State.InProgress) { Poll(download); }
}

// Prefer
if (download is null)
    return;
Action<Download> step = download.State switch
{
    State.Pending    => StartPending,
    State.InProgress => Poll,
    State.Complete   => Clear,
    _ => throw new UnreachableException($"download state {download.State}"),
};
step(download);
```

- `if (order is not { Status: Status.Paid, Lines.Count: > 0 }) return;`
  is one guard for three conditions.
- `when` clauses keep each arm a single condition the reader holds.
- The discard arm should throw, naming the value; a silent default hides a
  new enum member.

## Loops: `continue` and LINQ

```csharp
foreach (var e in entities)
{
    if (e.Kind != "service")
        continue;
    if (string.IsNullOrEmpty(e.Owner))
    {
        missing.Add(e.Name);
        continue;
    }
    CheckOwner(e);
}
```

- `Any`, `All`, `FirstOrDefault`, `Where(...).Select(...)` replace search
  loops with a flag and `for` + `if` + `Add`.
- A query with nested `SelectMany`, lambdas containing `if` blocks, or
  side effects inside `Select` is nesting moved onto one line. Use a
  `foreach` or extract a named method.
- Local functions are a cheap extraction, but a local function inside a
  loop inside a method starts deep; lift it to a private method taking
  explicit state, especially for recursive walks.

## Analyzers

| Rule | What |
|---|---|
| CA1502 | cyclomatic complexity per method (default threshold 25; `CodeMetricsConfig.txt` as `AdditionalFiles`, e.g. `CA1502: 10`); off by default |
| IDE0063 | use simple `using` statement |
| IDE0066 | use switch expression (instead of a `switch` statement) |
| IDE0072 | add missing cases to switch expression |
| IDE0078 / IDE0083 | use pattern matching / `not` pattern |
| IDE0046 | `if`/`return` to conditional expression (use judgement) |
| RCS1211 (Roslynator) | remove unnecessary `else` after `return`/`throw` |
| S134, S3776 (SonarAnalyzer.CSharp) | nesting depth, cognitive complexity; check thresholds in the project's quality profile |

IDE rules run on the command line only with
`<EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>` and a severity of
`warning` or `error` in `.editorconfig`
(`dotnet_diagnostic.IDE0063.severity = warning`).

`scripts/nesting_depth.py` does not read `.cs` files. For a lead list over
`dotnet format` output (4-space indent, file-scoped namespace, method body
at 8 spaces), a control statement at 16+ spaces opens depth 4:

```bash
grep -rnE '^ {16,}(if|for|foreach|while|do|switch|try|lock)\b' --include='*.cs' src/
```

With block-scoped namespaces use `{20,}`. Lambdas and local functions are
not counted; read each hit before reporting it.
