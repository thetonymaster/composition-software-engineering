# Dependency injection in C#

.NET ships a container (`Microsoft.Extensions.DependencyInjection`) in every
host, so injection is the default — and so is over-injection: an interface
per class, every class registered, and `IServiceProvider` passed around as a
service locator. The container is the composition root's tool, not the
application's.

## Constructor injection

```csharp
public interface IUploader
{
    Task UploadAsync(string name, Stream data, CancellationToken ct);
}

public interface IScanner
{
    Task<bool> IsCleanAsync(Stream data, CancellationToken ct);
}

public sealed class AttachmentService(IUploader store, IScanner scanner, TimeProvider time)
{
    public async Task HandleAsync(string name, Stream data, CancellationToken ct)
    {
        if (!await scanner.IsCleanAsync(data, ct))
            throw new InfectedFileException(name, time.GetUtcNow());
        data.Position = 0;
        await store.UploadAsync(name, data, ct);
    }
}
```

- One public constructor, every required collaborator a parameter. Optional
  parameters with defaults are for knobs, never for a missing dependency.
- `TimeProvider` (.NET 8+) is the clock seam; register
  `TimeProvider.System` once.
- A single-method dependency can be a delegate (`Func<DateTimeOffset>`), but
  delegates are awkward to register; prefer a small interface once the
  container builds the consumer.

## Composition root and lifetimes

`Program.cs` is the edge. It reads configuration and registers concrete
types; nothing below it reads `IConfiguration` or environment variables.

```csharp
var builder = WebApplication.CreateBuilder(args);
var storage = builder.Configuration.GetSection("Storage").Get<StorageOptions>()
    ?? throw new InvalidOperationException("missing config section 'Storage'");

builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<IScanner, ClamAvScanner>();
builder.Services.AddSingleton<IUploader>(_ => storage.Kind switch
{
    "s3"     => new S3Storage(new AmazonS3Client(), storage.Bucket),
    "sftp"   => new SftpStorage(storage.Host, storage.PrivateKeyPath),
    "webdav" => new WebDavStorage(new Uri(storage.Url)),
    _ => throw new InvalidOperationException(
        $"storage kind '{storage.Kind}': want s3, sftp or webdav"),
});
builder.Services.AddScoped<AttachmentService>();
```

| Lifetime | One instance per | Use for |
|---|---|---|
| `AddSingleton` | app | stateless or thread-safe services, clients, `TimeProvider` |
| `AddScoped` | scope (an HTTP request) | `DbContext`, unit-of-work state |
| `AddTransient` | resolution | cheap, stateful-per-use helpers |

**Captive dependency:** a singleton that takes a scoped service holds that
one instance for the app's life (a `DbContext` shared across requests). The
host enables scope validation and build-time validation in the Development
environment only; turn them on everywhere so it fails at startup:

```csharp
builder.Host.UseDefaultServiceProvider(o => { o.ValidateScopes = true; o.ValidateOnBuild = true; });
```

A `BackgroundService` (a singleton) that needs scoped services takes
`IServiceScopeFactory` and creates a scope per unit of work — the one place
resolving from a provider is correct.

Keyed services (.NET 8+: `AddKeyedSingleton<IUploader, S3Storage>("s3")`,
`[FromKeyedServices("s3")]`) fit when several implementations are live at
once. When one is chosen from config, a factory with a `switch` is simpler
and fails loudly.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP | `new HttpClient(new StubHandler(...))` — subclass `HttpMessageHandler`, override `SendAsync` |
| Clock | `FakeTimeProvider` (`Microsoft.Extensions.TimeProvider.Testing`): `SetUtcNow`, `Advance` |
| Streams | `MemoryStream`, `StringReader` / `StringWriter` |
| Options | `Options.Create(new StorageOptions { ... })` |
| Consumer interface | a hand-written fake class in the test project |
| Whole app | `WebApplicationFactory<Program>` + `ConfigureTestServices` to swap registrations |

```csharp
sealed class InMemoryStore : IUploader
{
    public Dictionary<string, byte[]> Files { get; } = new();
    public async Task UploadAsync(string name, Stream data, CancellationToken ct)
    {
        using var buffer = new MemoryStream();
        await data.CopyToAsync(buffer, ct);
        Files[name] = buffer.ToArray();
    }
}

[Fact]
public async Task Upload_stores_clean_file()
{
    var store = new InMemoryStore();
    var svc = new AttachmentService(store, new AlwaysClean(), new FakeTimeProvider());
    await svc.HandleAsync("a.txt", new MemoryStream("hi"u8.ToArray()), CancellationToken.None);
    Assert.Equal("hi"u8.ToArray(), store.Files["a.txt"]);
}
```

Hand-written fakes of 1–3 member interfaces are usually shorter than Moq or
NSubstitute setups and survive refactors. Use a mocking library for the one
interaction that *is* the behaviour (`Received(1).SendAsync(...)` in
NSubstitute, `Verify(..., Times.Once())` in Moq), and for wide third-party
interfaces.

## Smells

- `IServiceProvider` or `GetRequiredService<T>()` inside a domain class →
  service locator; the real dependencies are hidden. Take them in the
  constructor.
- `new HttpClient()` / `new SqlConnection(...)` / `new AmazonS3Client()`
  inside business logic → hardwired; move construction to `Program.cs`.
- `IConfiguration`, `Environment.GetEnvironmentVariable` or `DateTime.UtcNow`
  read below the composition root → bind options once, inject
  `IOptions<T>` or the value, inject `TimeProvider`.
- A singleton whose constructor takes a `DbContext` or other scoped service
  → captive dependency.
- Tests using reflection or `InternalsVisibleTo` to call private methods →
  the logic wants extracting into its own injectable unit.
- An interface per class, every one registered, none faked or varied → the
  container is ceremony; inject concrete types.
