# Dependency injection in Python

Python can patch anything at runtime, which is exactly why injection gets
skipped: `mock.patch` makes hardwired code *testable* without making it
*decoupled*. Treat each `patch` as a missing constructor parameter.

## Constructor injection with Protocols

```python
from collections.abc import Callable
from datetime import datetime, timezone
from typing import BinaryIO, Protocol

class Uploader(Protocol):
    def upload(self, name: str, data: BinaryIO) -> None: ...

class Scanner(Protocol):
    def is_clean(self, data: BinaryIO) -> bool: ...

class AttachmentService:
    def __init__(
        self,
        store: Uploader,
        scanner: Scanner,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._scanner = scanner
        self._now = now
```

Required collaborators have no defaults. A default is acceptable only when it
is the correct production value and pure-ish (a clock), never a network client
built at import time.

## Factory at the edge

```python
def storage_for(cfg: StorageConfig) -> Uploader:
    match cfg.kind:
        case "s3":
            return S3Storage(boto3.client("s3"), cfg.bucket)
        case "sftp":
            return SftpStorage(cfg.host, cfg.private_key)
        case "webdav":
            return WebDavStorage(cfg.url)
        case _:
            raise ValueError(f"storage kind {cfg.kind!r}: want 's3', 'sftp' or 'webdav'")
```

Web apps: build dependencies in the app factory (`create_app(settings)`) or
the framework's DI hook (FastAPI `Depends`, overridden in tests with
`app.dependency_overrides`). Libraries like `dependency-injector` add a
container; justify it by service count, not by habit.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP via `httpx` | `httpx.Client(transport=httpx.MockTransport(handler))` |
| HTTP via `requests` | `responses` library, or inject a session |
| AWS | `moto` — but injecting the client still matters, so tests choose the endpoint |
| Files | `io.BytesIO` / `io.StringIO`; `tmp_path` only for code at the edge |
| Clock | `now=lambda: FIXED` |
| Protocol | a small class in the test module; `pytest` fixtures to build it |

```python
class InMemoryStore:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
    def upload(self, name: str, data: BinaryIO) -> None:
        self.files[name] = data.read()

def test_upload_stores_clean_file():
    store = InMemoryStore()
    svc = AttachmentService(store, scanner=AlwaysClean(), now=lambda: FIXED)
    svc.handle("a.txt", io.BytesIO(b"hi"))
    assert store.files == {"a.txt": b"hi"}
```

`unittest.mock.create_autospec(S3Storage)` is the right tool when a mock is
genuinely needed: unlike a bare `Mock`, it fails on misspelled methods and
wrong signatures.

## Smells

- `mock.patch("app.service.boto3")` or `monkeypatch.setattr(module, "client", ...)`
  in tests → the module constructs its own dependency.
- Module-level `client = SomeClient(os.environ["URL"])` → import has side
  effects and reads env; move into the factory.
- `os.environ[...]` read inside business logic → read settings once
  (e.g. `pydantic-settings`) at startup and pass values.
- Tests calling `obj._private_method()` → the logic wants extracting into its
  own injectable unit.
- A `**kwargs` constructor forwarding credentials for several backends → the
  if/else upload function in disguise.
