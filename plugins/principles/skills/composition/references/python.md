# Composition in Python

Python makes inheritance cheap and duck typing free, so both failure
directions are common: deep class hierarchies with mixins, and "interfaces"
(ABCs) declared for a single implementation.

## Protocol at the consumer, not ABC at the implementer

`typing.Protocol` is structural: any class with matching methods satisfies it
without importing or subclassing anything. That is Go's consumer-side
interface. `abc.ABC` is nominal: implementations must inherit from it, which
couples them to the declaring module.

```python
# attachments/handler.py — the consumer declares what it calls.
from typing import BinaryIO, Protocol

class Uploader(Protocol):
    def upload(self, name: str, data: BinaryIO) -> None: ...

class AttachmentHandler:
    def __init__(self, store: Uploader) -> None:
        self._store = store

    def handle(self, name: str, data: BinaryIO) -> None:
        self._store.upload(name, data)

# storage/s3.py — knows nothing about Uploader.
class S3Storage:
    def __init__(self, client, bucket: str) -> None: ...
    def upload(self, name: str, data: BinaryIO) -> None: ...
```

Use an ABC when shared *behaviour* must ship with the contract and
`TypeError` at instantiation for a missing method is wanted — and then it is
inheritance, so the rules below apply. `@runtime_checkable` makes `isinstance`
work against a Protocol but only checks method *names*, not signatures.

Review signals:

- An `ABC` with one subclass and no plan for a second → delete the ABC.
- `class FooInterface(ABC)` living next to its only `Foo` → same.
- A Protocol with ten methods where the consumer calls two → narrow it.

## Inheritance traps specific to Python

1. **Mixins and the MRO.** `class Service(LoggingMixin, CacheMixin, Base)`
   resolves methods by C3 linearisation; a mixin calling `super().save()`
   calls whichever class comes next *in the instance's MRO*, not its own
   parent. Behaviour depends on base-class order at every subclass. Replace
   with composed collaborators (`self._cache = cache`) unless the mixin is
   stateless and has no `super()` calls.
2. **`NotImplementedError` stubs.** A subclass that overrides a parent method
   only to raise `NotImplementedError` is the `DrawableImage` problem. Split
   the capability out.
3. **"Protected" by convention.** `_attr` read by subclasses is API. Treat a
   subclass touching `self._parent_state` as a coupling finding.
4. **Framework-mandated inheritance** (Django models/views, `unittest.TestCase`,
   `Exception`) is fine — the framework is the second implementation. Keep the
   subclass thin and delegate logic to plain functions or composed objects.
5. **Dataclass inheritance** with defaults fails once a base field has a
   default and a child field does not (`kw_only=True` works around it); a
   sign the fields want composition (`@dataclass class Paid: user: User;
   auth: Auth; payment: Payment`).

## Image example, composed

```python
@dataclass
class Image:
    pixels: list[list[int]]
    def flip(self) -> None: ...
    def resize(self, w: int, h: int) -> None: ...

class ImageFile(Protocol):
    def load(self, src: BinaryIO) -> Image: ...
    def save(self, img: Image, dst: BinaryIO) -> None: ...

class Png:   # satisfies ImageFile structurally
    def load(self, src: BinaryIO) -> Image: ...
    def save(self, img: Image, dst: BinaryIO) -> None: ...

class ImageDraw:
    def __init__(self, img: Image) -> None:
        self._img = img
```

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| Read files | pass `pathlib.Path` **root** plus a reader callable, or a file-like object | `io.BytesIO`, `tmp_path` fixture only at the edge |
| Write bytes | `typing.BinaryIO` / `TextIO` parameter | `io.BytesIO` / `io.StringIO` |
| Time | `now: Callable[[], datetime]` parameter | `lambda: FIXED` |
| HTTP out | an injected client (`httpx.Client`) | `httpx.MockTransport` |
| Randomness | `random.Random` instance | seeded instance |

Python has no `fs.FS` equivalent with traversal protection. When joining a
user-supplied path under a root, resolve it and check
`resolved.is_relative_to(root.resolve())` (3.9+) — do not rely on string
prefix checks.

## Module-level state

Search with the shared commands in `principles-audit/references/python.md`
("Module-level clients / singletons / cached config").

- A module-level client (`client = boto3.client("s3")`) is a singleton
  created at import time: import order now has side effects and tests need
  `monkeypatch`. Construct it in `main`/app factory and pass it down.
- `@functools.cache` on a function that reads config or env is `sync.Once`.
- Needing `unittest.mock.patch("pkg.module.thing")` to test something is the
  signal: the dependency is hardwired. Inject it instead.

## Ordering as a type

```python
# Before: cycles() returns [] before resolve() runs.
cat.resolve(scope)
cycles = cat.cycles()

# After: only ResolvedGraph has cycles(); mypy/pyright reject the wrong order.
graph = cat.resolve(scope)   # -> ResolvedGraph
cycles = graph.cycles()
```

Only a type checker enforces this; run `mypy --strict` or `pyright` in CI or
the claim is aspirational.

## Linters

- `ruff`: `PLR0904` too-many-public-methods, `PLR0913` too-many-arguments
  (often a missing composed object), `PLW0603` global-statement.
- `pyright`/`mypy --strict` to make Protocol conformance and type-state
  ordering checked rather than hoped for.
- `import-linter` contracts to forbid `requests`/`boto3`/`os` imports in core
  packages.
