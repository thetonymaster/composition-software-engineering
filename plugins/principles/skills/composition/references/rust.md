# Composition in Rust

Rust has no inheritance, so the inheritance failure modes reappear in
Rust-shaped disguises: `Deref` used to fake subclassing, traits declared next
to their only implementation, trait objects or generics chosen by habit, and
`static` globals behind `LazyLock` or `lazy_static!`.

## Traits at the consumer, concrete types from the implementer

The implementing crate returns a concrete type with inherent methods. The
consuming module declares a trait with only the methods it calls.

```rust
// attach/src/lib.rs — the consumer declares what it calls.
pub trait Uploader {
    fn upload(&self, name: &str, data: &[u8]) -> Result<(), UploadError>;
}
pub struct Handler<U: Uploader> { store: U }

// storage/src/s3.rs — a concrete type, no trait.
pub struct S3 { client: aws_sdk_s3::Client, bucket: String }
impl S3 {
    pub fn new(client: aws_sdk_s3::Client, bucket: String) -> Self { todo!() }
}
```

Rust traits are nominal: something must write `impl Uploader for S3`, and
the orphan rule puts that impl in the crate owning the trait or the type.
Across crates, either `attach` depends on `storage` and holds the impl, or
the binary wraps it in a local newtype (`struct S3Store(storage::S3)`) and
implements the trait there.

Review signals:

- A `pub trait Foo` with exactly one `impl Foo for`, no test fake, no runtime
  choice → speculative. Delete the trait, use the struct.
- `pub fn new(..) -> Box<dyn Foo>` in the implementing crate → return the
  concrete type; let the consumer box it.
- A trait with many methods where each consumer calls one or two → split it
  at the consumer.

## Generics or `dyn Trait`

| | Generic `Handler<U: Uploader>` | `Box<dyn Uploader>` / `Arc<dyn Uploader + Send + Sync>` |
|---|---|---|
| Chosen | at compile time, per call site | at runtime, from data |
| Call cost | static dispatch, inlinable | vtable call |
| Spread | the type parameter appears in every type and fn that names `Handler` | none |
| Mixed collections | no | `Vec<Box<dyn Uploader>>` |
| Trait limits | none | trait must be dyn-compatible (formerly "object safe"): no generic methods; methods returning `Self` need `where Self: Sized`; `async fn` in a trait is not dyn-compatible |

Default to generics when the caller picks once and the parameter stays local.
Switch to `dyn` when a factory picks from config, or when the type parameter
starts infecting signatures that do not care about it. Do not choose on call
cost without a measurement (`measure-first`).

## `Deref` is not inheritance

```rust
struct Image { pixels: Vec<u8>, width: u32, height: u32 }
impl Image { fn flip(&mut self) { todo!() } }

struct Png { image: Image }
impl std::ops::Deref for Png {   // anti-pattern: "Png is-an Image"
    type Target = Image;
    fn deref(&self) -> &Image { &self.image }
}
```

`png.width` and every `&self` method of `Image` now resolve on `Png`. It reads
like inheritance and is not:

1. **Method lookup only, not a subtype.** If `Image` implements a trait,
   `Png` does not; generic bounds (`T: Encode`) do not see through `Deref`.
2. **No override.** A `Png::flip` shadows `Image::flip` when called on a
   `Png`, but code holding the `&Image` that deref coercion produced calls
   `Image::flip`. There is no virtual dispatch.
3. **API leakage.** Every method later added to `Image` silently becomes part
   of `Png`'s API; `DerefMut` does the same for `&mut self` methods.
4. **Against the guidance.** Rust API Guidelines C-DEREF: only smart pointers
   implement `Deref`. The `std::ops::Deref` docs warn that the compiler
   inserts `deref` calls silently.

Use a named field and delegate the few methods the outer type should present.

## Image example, composed

```rust
pub struct Image { pixels: Vec<u8>, width: u32, height: u32 }
impl Image {
    pub fn flip(&mut self) { todo!() }
    pub fn resize(&mut self, w: u32, h: u32) { todo!() }
}

pub trait ImageFile {
    fn load(&self, src: &mut dyn std::io::Read) -> std::io::Result<Image>;
    fn save(&self, img: &Image, dst: &mut dyn std::io::Write) -> std::io::Result<()>;
}

pub struct Png;
impl ImageFile for Png { /* load, save */ }

pub struct ImageDraw<'a> { img: &'a mut Image }
```

`ImageDraw` never touches `ImageFile`; there is nothing to stub.

## Trait defaults, supertraits, enums

- **Default methods** ship behaviour with the contract. Keep them stateless
  (traits have no fields) and written only in terms of the trait's required
  methods. Unlike `Deref`, a default that calls `self.other()` dispatches to
  the implementor's `other`.
- **"Not supported" stubs**: an impl whose method body is `unimplemented!()`,
  `todo!()` or `panic!` in shipped code is the `DrawableImage` problem. Split
  the trait.
- **Supertraits** (`trait ImageFile: Codec`) mean "requires", not "inherits
  fields"; a chain of three is a hierarchy.
- **Closed set → `enum`.** The user tiers compose as fields (`struct
  PaidUser { user: User, auth: Auth, payment: Payment }`) behind a one-method
  `Features` trait — or, known at compile time, as one `enum` with an
  exhaustive `match`. Use the trait when other crates add tiers.

**Newtypes** (`struct UserId(String);`) add invariants and let a local type
implement a foreign trait. Expose only the methods that keep the invariant;
a `Deref<Target = String>` hands the whole inner API back and undoes it.

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| Read bytes | `R: std::io::Read` / `BufRead`, or take `&[u8]` / `&str` content | `&[u8]`, `std::io::Cursor<Vec<u8>>` |
| Write bytes | `W: std::io::Write` | `Vec<u8>` |
| Named files in a tree | a consumer trait (`fn read(&self, name: &str) -> io::Result<Vec<u8>>`) | `HashMap<String, Vec<u8>>` fake |
| Time | `now: fn() -> SystemTime` field, or a small `Clock` trait | `\|\| UNIX_EPOCH`; `tokio::time::pause()` for tokio timers |
| HTTP out | consumer trait over the client, or a configurable base URL | `wiremock` / `httpmock` local server |
| Randomness | `R: rand::Rng` parameter | `StdRng::seed_from_u64(42)` |

`std` has no `fs.FS` equivalent with traversal protection. For a
user-supplied name, accept only paths whose `Path::components()` are all
`Component::Normal`; for containment on disk that also covers symlinks, use
`cap_std::fs::Dir`, which resolves paths relative to an opened directory and
refuses to escape it.

## Ordering as a type

```rust
// Before: cycles() returns an empty Vec before resolve() runs.
cat.resolve(&scope);
let cycles = cat.cycles();

// After: resolve(self, ..) -> Result<Graph, ResolveError> consumes the
// catalog; only Graph has cycles(), and `cat` cannot be used afterwards.
let graph = cat.resolve(&scope)?;
let cycles = graph.cycles();
```

Taking `self` by value makes the old state unusable: any later use of the
moved value does not compile.

## Global state

Search with the shared command in `principles-audit/references/rust.md`
("Global state").

- `static` + `LazyLock`/`OnceLock`/`lazy_static!`/`once_cell::sync::Lazy`
  holding a client, config read from env, or a `Mutex<HashMap>` registry is a
  singleton: two configurations cannot coexist and tests share it.
- A `LazyLock<Regex>` built from a literal is read-only and pure; fine.
- `inventory::submit!` / `linkme::distributed_slice` registration is Go's
  `init()` self-registration; accept it in a plugin boundary, do not copy it.
- `static mut` needs `unsafe` to touch; treat any hit as a finding.

## Factories

A factory earns its place when the implementation is chosen at runtime from
data. It returns a trait object, so it lives where the trait is visible: the
consuming crate or the binary.

```rust
pub fn storage_for(cfg: &StorageConfig) -> anyhow::Result<Box<dyn Uploader>> {
    match cfg.kind.as_str() {
        "s3" => Ok(Box::new(S3Store::new(&cfg.bucket))),
        "sftp" => Ok(Box::new(SftpStore::connect(&cfg.sftp)?)),
        "webdav" => Ok(Box::new(WebDavStore::new(&cfg.webdav_url))),
        other => anyhow::bail!("storage kind {other:?}: want s3, sftp or webdav"),
    }
}
```

Deserialising `kind` into an `enum` moves the error to config load. A
`HashMap<&str, fn() -> Box<dyn Uploader>>` filled by registration macros is
the over-abstraction version of the same thing.

## Linters and boundaries

- clippy `type_complexity` (default 250) — a type that wants a name.
- clippy `too_many_arguments` (`too-many-arguments-threshold`, default 7) —
  often a missing composed struct.
- clippy `disallowed_methods` / `disallowed_types`, configured in a
  `clippy.toml` in the core crate's directory — ban `std::env::var`,
  `std::time::SystemTime::now`, `std::net::TcpStream` there. Inert until
  configured.
- Crate boundaries: a core crate whose `Cargo.toml` does not list `reqwest`,
  `tokio` or `aws-sdk-*` cannot call them. The compiler enforces it; `std::fs`
  and `std::net` still need the clippy ban.
