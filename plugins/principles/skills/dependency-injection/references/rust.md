# Dependency injection in Rust

Rust needs no framework: a struct field of a generic type or a trait object,
set by `new`, is the whole mechanism. Wire-up happens in `main` (or a `run`
function it calls). DI containers exist as crates; reach for one only when
hand wiring in `main` passes a few hundred lines.

## Constructor injection: generic or trait object

```rust
use std::time::SystemTime;

pub trait Uploader {
    fn upload(&self, name: &str, data: &[u8]) -> Result<(), UploadError>;
}

pub trait Scanner {
    fn is_clean(&self, data: &[u8]) -> Result<bool, ScanError>;
}

// Static dispatch: implementations fixed at compile time.
pub struct Handler<U, S> {
    store: U,
    scanner: S,
    now: fn() -> SystemTime,
}

impl<U: Uploader, S: Scanner> Handler<U, S> {
    pub fn new(store: U, scanner: S, now: fn() -> SystemTime) -> Self {
        Self { store, scanner, now }
    }
}
```

```rust
// Dynamic dispatch: implementation chosen at runtime, shared across tasks.
pub struct Handler {
    store: Arc<dyn Uploader + Send + Sync>,
    scanner: Arc<dyn Scanner + Send + Sync>,
    now: fn() -> SystemTime,
}
```

- **Generic** when the implementation is fixed per build or per test.
  **`Box<dyn Trait>`** for one owner and a runtime choice. **`Arc<dyn Trait +
  Send + Sync>`** when shared across threads or async tasks (axum state,
  spawned tokio tasks).
- `Box<dyn Uploader>` does not implement `Uploader` by itself. Passing one
  into a generic `Handler<U: Uploader>` needs a forwarding impl:
  `impl<T: Uploader + ?Sized> Uploader for Box<T>`.
- A single-function dependency can be a `fn` pointer or closure, no trait:
  `now: fn() -> SystemTime` takes `SystemTime::now` in production and
  `|| UNIX_EPOCH` in tests (non-capturing closures coerce to `fn`).
- Constructors are inherent `new` functions returning `Self` (API Guidelines
  C-CTOR). Implementation crates return concrete types, not `Box<dyn Trait>`.
- `async fn` in traits is stable (1.75+) but not dyn-compatible. With
  `Arc<dyn Trait>`, use the `async-trait` crate or return boxed futures.

## Wiring in main

With the trait-object `Handler`:

```rust
fn main() -> anyhow::Result<()> {
    let cfg = Config::from_env()?;                // env read once, here
    let store = storage_for(&cfg.storage)?;      // -> Arc<dyn Uploader + Send + Sync>; Err on unknown kind
    let scanner = Arc::new(ClamAv::new(&cfg.scanner_url));
    let handler = Handler::new(store, scanner, SystemTime::now);
    run(handler, std::io::stdout().lock())
}
```

`run` taking its dependencies (including the writer and parsed config) makes
`main` itself testable.

## Builders — only for optional knobs

Rust has no default arguments; the builder pattern plays the role of Go's
functional options. Required dependencies stay positional in `new`; the
builder sets optional knobs (timeouts, retry policy) whose default is correct
in production. A builder whose `build()` returns `Err` because a "required"
field was never set is a required dependency hidden behind a default.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP API | `wiremock` or `httpmock` local server; point the client's base URL at it |
| Reader / writer | `&[u8]`, `std::io::Cursor`; `Vec<u8>` as a `Write` |
| Filesystem | a consumer-trait fake; `tempfile::TempDir` only for code at the edge |
| Clock | `\|\| UNIX_EPOCH`; `#[tokio::test(start_paused = true)]` for tokio timers (feature `test-util`) |
| Consumer trait | a hand-written fake in `#[cfg(test)] mod tests` |

```rust
#[derive(Default)]
struct InMemoryStore {
    files: Mutex<HashMap<String, Vec<u8>>>,
}

impl Uploader for InMemoryStore {
    fn upload(&self, name: &str, data: &[u8]) -> Result<(), UploadError> {
        self.files.lock().unwrap().insert(name.to_owned(), data.to_vec());
        Ok(())
    }
}
```

Trait methods taking `&self` force the fake to use interior mutability:
`RefCell` for single-threaded generics, `Mutex` when the trait object must be
`Send + Sync`.

`mockall` is the right tool when the interaction *is* the behaviour:
`#[cfg_attr(test, mockall::automock)]` on the trait generates `MockUploader`,
and `expect_upload().times(1).returning(|_, _| Ok(()))` asserts the call.
The `cfg_attr(test, ..)` form only exists in that crate's unit tests. A mock
for every collaborator tests the wiring, not the outcome; prefer fakes.

## Smells

- `static CLIENT: LazyLock<reqwest::Client>` or a `OnceLock` set in `main`
  and read deep in the code → hidden global; pass it.
- `std::env::var` below `main` → read config once, pass values. Tests that
  call `std::env::set_var` (which is `unsafe` from edition 2024) or need
  `#[serial]` to avoid racing each other → a missing parameter.
- `if cfg!(test) { fake } else { real }` or `#[cfg(not(test))]` on a
  production code path → a hardwired dependency with a test switch; inject.
- `pub fn new() -> Box<dyn Foo>` with one implementation → return `Foo`.
- A struct with `Option<S3Creds>`, `Option<SftpKey>`, `Option<Url>` fields →
  the if/else upload function in disguise.
