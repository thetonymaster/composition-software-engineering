# Composition in C#

C# classes are unsealed by default and inheritance is one keyword away, so
the classic failure is a base class holding shared code. The opposite
failure is just as common: an `IFoo` declared next to every `Foo` "for
testability", with one implementation and no fake.

## Interfaces belong to the consumer

C# interfaces are nominal. An implementation must name the interface
(`class S3Storage : IUploader`), so its project must reference the project
that declares it. Declare the interface in the consuming (core) project; the
infrastructure project references core and implements it. Never the reverse.

```csharp
// Attachments/AttachmentHandler.cs (core) — the consumer declares what it calls.
public interface IUploader
{
    Task UploadAsync(string name, Stream data, CancellationToken ct);
}

public sealed class AttachmentHandler(IUploader store)
{
    public Task HandleAsync(string name, Stream data, CancellationToken ct) =>
        store.UploadAsync(name, data, ct);
}

// Storage/S3Storage.cs (infrastructure) — references core, implements its contract.
public sealed class S3Storage(IAmazonS3 client, string bucket) : IUploader
{
    public Task UploadAsync(string name, Stream data, CancellationToken ct) { ... }
}
```

When the implementation lives in a package you cannot change, write a small
adapter class in the edge project instead of leaking the vendor type inward.

Review signals:

- `IFoo` and `Foo` in the same folder, one implementation, no fake in the
  tests, no runtime choice → delete the interface; inject `Foo`.
- An interface with ten members where the consumer calls two → split it at
  the consumer.
- An interface declared in the infrastructure project and referenced by core
  → the dependency points the wrong way.

## Inheritance traps specific to C#

1. **Unsealed by default.** Any public class can be subclassed by anyone.
   Mark classes `sealed` unless inheritance is designed in; CA1852 flags
   internal types that could be sealed.
2. **Virtual calls in constructors.** A base constructor calling a `virtual`
   member runs the derived override before the derived constructor has run
   (CA2214). Fields the override reads are still default.
3. **`new` hides, it does not override.** A method declared `new` in a
   derived class is called only through a reference of the derived type;
   through a base reference the base method runs. Code that relies on
   "replacing" a non-virtual base method is a bug waiting for the second
   call site.
4. **`protected` state is API.** A `protected` field or a
   `protected virtual` hook read by subclasses freezes the parent's
   internals. Treat a subclass touching parent state as a coupling finding;
   CA1051 flags visible instance fields.
5. **`NotSupportedException` overrides.** A subclass that overrides a member
   only to throw is the `DrawableImage` problem. Split the capability out.
6. **Framework-mandated bases** (`ControllerBase`, `BackgroundService`,
   `DbContext`, `Exception`) are fine — the framework is the second
   implementation. Keep the subclass thin; delegate to composed services.

## Interfaces, default members, extension methods, records

- **Default interface members** (C# 8+) add behaviour to a contract without
  breaking implementers. The default is reachable only through the interface
  type, not through a variable of the class type, and it cannot hold state.
  Use them to evolve a published interface, not as a substitute base class.
- **Extension methods** are static functions with instance syntax: no state,
  no virtual dispatch, and an instance method with the same signature wins
  silently. Good for helpers over a small interface; poor as a way to
  "inherit" behaviour.
- **Records** can inherit only from records, and value equality includes
  the runtime type: a `Base` and a `Derived` with equal fields are not
  equal. A record hierarchy is usually composition wanting out
  (`record Paid(User User, Auth Auth, Payment Payment)`).
- **Primary constructors** (C# 12) make constructor-injected composition
  cheap to write; the parameters are captured, not `readonly` fields, so
  assign them to `readonly` fields when mutation must be ruled out.

## Image example, composed

```csharp
public sealed class Image(int[,] pixels)
{
    public void Flip() { ... }
    public void Resize(int w, int h) { ... }
}

public interface IImageFile
{
    Image Load(Stream src);
    void Save(Image img, Stream dst);
}

public sealed class Png : IImageFile { ... }
public sealed class Jpeg : IImageFile { ... }

public sealed class ImageDraw(Image img) { ... }
```

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| Read files | `Stream` / `TextReader` parameter, or `IFileProvider` (`Microsoft.Extensions.FileProviders`) | `MemoryStream`, `StringReader`, a fake `IFileProvider` |
| Write bytes | `Stream` / `TextWriter` parameter | `MemoryStream`, `StringWriter` |
| Time | `TimeProvider` (.NET 8+) | `FakeTimeProvider` (`Microsoft.Extensions.TimeProvider.Testing`) |
| HTTP out | `HttpClient` from `IHttpClientFactory` / typed client | `new HttpClient(new StubHandler())` with an `HttpMessageHandler` subclass |
| Randomness | an injected `Random` instance | `new Random(seed)` |

`PhysicalFileProvider` scopes lookups to its root directory, but the docs
warn it is not a sandbox: a symbolic link under the root can still expose
files outside it. When joining a user-supplied name under a root by hand,
note that `Path.Combine(root, "/etc/passwd")` returns `/etc/passwd`.
Resolve with `Path.GetFullPath(name, root)`, then reject the result when
`Path.GetRelativePath(root, full)` is rooted or starts with `..`.

## Static state

Search with the shared commands in `principles-audit/references/csharp.md`
("Static state and singletons").

- A `static` mutable field, a `static Instance` property or a static
  `Lazy<T>` is a process-wide singleton: two configurations cannot coexist,
  and tests that touch it cannot run in parallel. Register it once in the
  container (`AddSingleton`) and inject it instead.
- `DateTime.UtcNow`, `Random.Shared`, `Environment.GetEnvironmentVariable`
  and `File.*` called from core code are hidden globals — inject
  `TimeProvider`, `Random`, options or a stream.
- `[ModuleInitializer]` is C#'s `init()`; CA2255 warns against it in
  libraries.
- `public static` non-readonly fields are mutable by any caller (CA2211).
  `static readonly` collections are still mutable through their methods;
  expose `FrozenDictionary`/`ImmutableArray` or return a fresh copy.

## Ordering as a type

```csharp
// Before: Cycles() returns an empty list before Resolve() runs.
catalog.Resolve(scope);
var cycles = catalog.Cycles();

// After: only ResolvedGraph has Cycles(); the wrong order does not compile.
ResolvedGraph graph = catalog.Resolve(scope);
var cycles = graph.Cycles();
```

The compiler enforces this with no extra tooling. It pays when the wrong
order produces a plausible empty answer rather than an exception.

## Analyzers

- CA1501 — inheritance depth (default threshold 5; set in
  `CodeMetricsConfig.txt` included as `AdditionalFiles`, e.g. `CA1501: 3`).
- CA1852 seal internal types, CA2214 virtual call in constructor, CA2211
  visible non-constant static fields, CA1051 visible instance fields.
- `Microsoft.CodeAnalysis.BannedApiAnalyzers` (RS0030) with a
  `BannedSymbols.txt` to ban `DateTime.Now`, `File`, `HttpClient`
  construction in core projects.
- Architecture tests (`NetArchTest.Rules`, `ArchUnitNET`) to forbid core
  projects from referencing infrastructure namespaces.
