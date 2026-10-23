# Composition in Java

Java grew up on class hierarchies, so both failure directions are common:
abstract base classes reused for code sharing, and `FooService` interfaces
declared next to their only `FooServiceImpl`. *Effective Java* (Item 18,
"Favor composition over inheritance") is the canonical statement of the rule.

## The fragile base class

Subclassing a concrete class couples the subclass to the parent's
*implementation*, not its contract. The textbook case:

```java
class InstrumentedHashSet<E> extends HashSet<E> {
    private int addCount = 0;
    @Override public boolean add(E e) { addCount++; return super.add(e); }
    @Override public boolean addAll(Collection<? extends E> c) {
        addCount += c.size();
        return super.addAll(c);   // HashSet.addAll calls add() per element
    }
}
// addAll(List.of("a", "b", "c")) → addCount == 6, not 3.
```

Nothing in `HashSet`'s contract says `addAll` calls `add`; the subclass broke
on an implementation detail, and a JDK upgrade could break it the other way.
The fix is a wrapper holding a `Set<E>` and forwarding to it: the same
`addAll` call counts 3, and it works over any `Set`, not just `HashSet`.

## Interface at the consumer, delegation for reuse

Declare the interface in the package that *calls* it, sized to what that
package calls. Implementations live elsewhere and stay concrete.

```java
// attach/AttachmentHandler.java — the consumer declares what it calls.
public interface Uploader {
    void upload(String name, InputStream data) throws IOException;
}

public final class AttachmentHandler {
    private final Uploader store;
    public AttachmentHandler(Uploader store) { this.store = Objects.requireNonNull(store); }
    public void handle(String name, InputStream data) throws IOException {
        store.upload(name, data);
    }
}

// storage/S3Storage.java — implements Uploader, holds only its own client.
public final class S3Storage implements Uploader { ... }
```

Java interfaces are nominal: `S3Storage` must name `Uploader`, so the
implementer imports the consumer's package. When that dependency direction is
wrong, adapt with a lambda or method reference at the edge
(`Uploader u = s3::put;`) — any single-method interface is a functional
interface.

Review signals:

- `FooService` + `FooServiceImpl`, one implementation, no test fake → delete
  the interface; inject the class.
- An `abstract class` whose subclasses share code but not a contract →
  extract the shared code into a collaborator the subclasses hold.
- An interface with ten methods where each consumer calls two → split it.

## Default methods and abstract classes

- **Abstract class**: shares state and code, allows one parent, and every
  `protected` member becomes API for subclasses. Use it only when the
  framework demands it or when sealing a hook API (below).
- **Default methods** cannot hold state, which limits the damage, but a
  default that calls other interface methods is a template method again:
  implementors silently depend on the call graph between them.
- Two interfaces with the same default method do not compose: `class S
  implements Audited, Cached` fails with `types Audited and Cached are
  incompatible` until `S` overrides the method. Adding a default to a widely
  implemented interface can break implementors that never changed.

## Inheritance traps specific to Java

1. **`UnsupportedOperationException` stubs.** An override that only throws is
   the `DrawableImage` problem. Split the capability out. (The JDK does this
   with immutable collections; that is a known wart, not a model.)
2. **`protected` fields.** A subclass reading `this.target` set by the parent
   has made the parent's internals API. Checkstyle `VisibilityModifier` flags
   non-private fields.
3. **Overridable calls in a constructor.** The subclass override runs before
   the subclass's fields are initialised. Call only `private`/`final` methods
   from constructors.
4. **Framework-mandated inheritance** (`Exception`, `HttpServlet`,
   `TestCase`, JPA `@MappedSuperclass`) is fine — the framework is the second
   implementation. Keep the subclass thin and delegate to composed objects.
5. **Unsealed by default.** A non-`final` public class is open for
   extension. Make classes `final` unless designed for it; Checkstyle
   `DesignForExtension` and `FinalClass` push in that direction.

## Sealed interfaces and records (Java 17)

Records give immutable composed values; a `sealed` interface makes the set of
implementations closed and visible. The tier example:

```java
record User(String id) {}
record Auth(String token) { boolean loggedIn() { return !token.isEmpty(); } }
record Payment(String status) { boolean valid() { return status.equals("active"); } }

sealed interface Features permits Paid, Trial, Guest {
    boolean hasFeature(String f);
}
record Paid(User user, Auth auth, Payment payment) implements Features {
    public boolean hasFeature(String f) {
        return auth.loggedIn() && payment.valid() && lookup(user.id(), f);
    }
}
record Trial(User user, Auth auth) implements Features {
    public boolean hasFeature(String f) { return auth.loggedIn() && lookup(user.id(), f); }
}
record Guest(User user) implements Features {
    public boolean hasFeature(String f) { return GUEST_FEATURES.contains(f); }
}
```

Records cannot extend classes, so reuse *has* to be composition. With Java
21+ pattern-matching `switch`, a `switch` over a sealed type needs no
`default` and fails to compile when a new permitted type is added.

## Image example, composed

```java
final class Image {                       // concrete value: pixels + operations
    void flip() { ... }
    void resize(int w, int h) { ... }
}
interface ImageFile {                     // two-method contract
    Image load(InputStream src) throws IOException;
    void save(Image img, OutputStream dst) throws IOException;
}
final class Png implements ImageFile { ... }
final class ImageDraw {
    private final Image img;
    ImageDraw(Image img) { this.img = img; }
}
```

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| Read files | `java.nio.file.Path` from an injected `FileSystem`, or an `InputStream` | Jimfs (`com.google.jimfs`) in-memory `FileSystem`; `ByteArrayInputStream` |
| Write bytes | `OutputStream` / `Writer` parameter | `ByteArrayOutputStream` / `StringWriter` |
| Time | `java.time.Clock` | `Clock.fixed(instant, ZoneOffset.UTC)` |
| HTTP out | an injected `java.net.http.HttpClient` or consumer interface | JDK `com.sun.net.httpserver.HttpServer` on port 0, WireMock |
| Randomness | `java.util.random.RandomGenerator` (17+) / `Random` | seeded `new Random(42)` |

Java has no `fs.FS`-style traversal guard. When joining a user-supplied name
under a root, compare `Path`s, not strings:

```java
Path base = root.toRealPath();
Path p = base.resolve(name).normalize();
if (!p.startsWith(base)) throw new IllegalArgumentException("path " + name + " escapes " + base);
```

`Path.startsWith` compares name elements, so `/srv/root-evil` does not match
`/srv/root` (a `String.startsWith` check does). `normalize()` does not resolve
symlinks: a link inside the root still escapes unless the final path is
checked again after `toRealPath()`.

## Static state

Search with the shared commands in `principles-audit/references/java.md`
("Static state and singletons").

- `private static Foo instance` + `getInstance()` is a singleton: two
  configurations cannot coexist and tests cannot reset it. Construct one in
  `main` and pass it.
- `public static final List<String> X = new ArrayList<>()` is `final`, not
  immutable. Use `List.of(...)` / `Map.of(...)`.
- Static initialisers that register into a global map are `init()`
  self-registration. `ServiceLoader` is the JDK's sanctioned version; accept
  it at the boundary, do not copy the pattern internally.

## Ordering as a type

```java
// Before: cycles() returns an empty list before resolve() runs.
cat.resolve(scope);
List<Cycle> cycles = cat.cycles();

// After: only ResolvedGraph has cycles(); the wrong order does not compile.
ResolvedGraph graph = cat.resolve(scope);
List<Cycle> cycles = graph.cycles();
```

## Linters

- Checkstyle: `DesignForExtension`, `FinalClass`, `VisibilityModifier`,
  `ClassFanOutComplexity` (default max 20), `ParameterNumber` (default max 7).
- PMD: `design.xml/MutableStaticState`, `bestpractices.xml/AbstractClassWithoutAbstractMethod`.
- ArchUnit: forbid `java.net.http..`, `java.sql..` dependencies from core
  packages (`noClasses().that().resideInAPackage("..core..").should().dependOnClassesThat()...`).
