# Dependency injection in Java

Java DI is usually discussed as a framework feature (Spring, Guice, Dagger),
but the mechanism is a constructor parameter stored in a `final` field. The
framework only automates the wiring in `main`. Get the class shape right and
the choice of container becomes a detail.

## Constructor injection, final fields

```java
public interface Uploader { void upload(String name, InputStream data) throws IOException; }
public interface Scanner { boolean isClean(byte[] data); }

public final class AttachmentService {
    private final Uploader store;
    private final Scanner scanner;
    private final Clock clock;

    public AttachmentService(Uploader store, Scanner scanner, Clock clock) {
        this.store = Objects.requireNonNull(store, "store");
        this.scanner = Objects.requireNonNull(scanner, "scanner");
        this.clock = Objects.requireNonNull(clock, "clock");
    }
}
```

- `final` fields: the object is complete after construction, safe to publish
  across threads, and a missing dependency fails at `new`, not at first use.
- `java.time.Clock` is the JDK's clock seam. Call `clock.instant()` or
  `LocalDate.now(clock)`, never `Instant.now()` / `System.currentTimeMillis()`
  in logic.
- A one-method dependency can be a functional interface; tests pass a lambda
  (`data -> true`).

## Composition root in main

```java
public static void main(String[] args) {
    var cfg = Config.load(System.getenv());            // the only env read
    var svc = new AttachmentService(storageFor(cfg.storage()),
                                    new ClamScanner(cfg.clamHost()),
                                    Clock.systemUTC());
    new HttpApi(svc).start(cfg.port());
}

static Uploader storageFor(StorageConfig cfg) {
    return switch (cfg.kind()) {
        case "s3" -> new S3Storage(cfg.bucket());
        case "sftp" -> new SftpStorage(cfg.host());
        case "webdav" -> new WebDavStorage(cfg.url());
        default -> throw new IllegalArgumentException(
            "storage kind \"" + cfg.kind() + "\": want s3, sftp or webdav");
    };
}
```

Hand wiring in `main` is the default for libraries, CLIs and small services.
A container earns its place when the graph is large, or when the framework
(Spring Boot, Quarkus, Micronaut) already owns startup.

## With Spring or Guice

The class above needs no change. Spring calls a class's single constructor
without `@Autowired` (Spring 4.3+); Guice needs `@Inject` on it.

```java
// Spring: data-driven choice lives in one @Bean method.
@Configuration
class StorageConfiguration {
    @Bean Uploader uploader(StorageConfig cfg) { return storageFor(cfg); }
    @Bean Clock clock() { return Clock.systemUTC(); }
}

// Guice
final class StorageModule extends AbstractModule {
    private final StorageConfig cfg;
    StorageModule(StorageConfig cfg) { this.cfg = cfg; }
    @Override protected void configure() { bind(Clock.class).toInstance(Clock.systemUTC()); }
    @Provides Uploader uploader() { return storageFor(cfg); }
}
```

Keep framework annotations out of the core where cheap: a `@Bean` method can
construct a plain class that imports nothing from Spring.

## Field injection pitfalls

```java
@Service
class Billing {
    @Autowired private Uploader store;   // avoid
}
```

1. **Hidden dependencies.** The constructor signature says nothing; seven
   `@Autowired` fields look as cheap as one, so the "too many dependencies"
   signal never fires.
2. **No `final`.** The field is mutable and `null` between construction and
   injection; `new Billing()` in a test gives an object that NPEs later.
3. **Tests need the container or reflection** (`ReflectionTestUtils.setField`,
   `@InjectMocks`) to set a private field.
4. **Cycles hide.** A constructor cycle cannot be built, so plain Spring
   fails at startup (`Requested bean is currently in creation`); a field
   cycle starts fine with half-built beans. Spring Boot 2.6+ rejects circular
   references by default (`spring.main.allow-circular-references`).

ArchUnit ships `GeneralCodingRules.NO_CLASSES_SHOULD_USE_FIELD_INJECTION`.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP via `java.net.http.HttpClient` | inject the client; serve a JDK `HttpServer` on port 0, or WireMock |
| Files | Jimfs `FileSystem`, `ByteArrayInputStream`/`ByteArrayOutputStream`; `@TempDir` (JUnit 5) only at the edge |
| Clock | `Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC)` |
| Database | Testcontainers for the real engine; an in-memory fake for the repository interface |
| Consumer interface | a small hand-written class in the test source set |

```java
final class InMemoryStore implements Uploader {
    final Map<String, byte[]> files = new HashMap<>();
    @Override public void upload(String name, InputStream data) throws IOException {
        files.put(name, data.readAllBytes());
    }
}

@Test void storesCleanFile() throws IOException {
    var store = new InMemoryStore();
    var svc = new AttachmentService(store, data -> true, FIXED_CLOCK);
    svc.handle("a.txt", "hi".getBytes());
    assertArrayEquals("hi".getBytes(), store.files.get("a.txt"));
}
```

Use Mockito for the interaction that *is* the behaviour:
`verify(mailer, times(1)).send("q@example.com", "welcome")`. A test that
stubs five collaborators with `when(...).thenReturn(...)` and verifies each
call tests the implementation's call order, not its outcome. Mockito 5 mocks
`final` classes by default (inline mock maker), so "make it non-final for
Mockito" is no longer a reason to open a class.

## Smells

- `Mockito.mockStatic(...)`, `@InjectMocks` on private fields,
  `ReflectionTestUtils.setField` → the class builds or looks up its own
  dependency.
- `new HttpClient`/`HttpClient.newHttpClient()`, `DriverManager.getConnection`
  inside a method → construct at the edge, inject.
- `System.getenv` / `System.getProperty` below `main` or the config class →
  read once, pass values.
- `applicationContext.getBean(...)` in business code → service locator;
  inject the bean.
- `@SpringBootTest` for a class that could be built with `new` → the unit
  test is starting a container to work around a hidden dependency.
- A constructor with more than ~5 parameters → two jobs; split the class.
