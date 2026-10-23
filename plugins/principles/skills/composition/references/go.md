# Composition in Go

Go has no inheritance, so the inheritance failure modes reappear in Go-shaped
disguises: embedding used as subclassing, interfaces declared by the
implementer, and package-level registries.

## Interfaces belong to the consumer

The Go Code Review Comments wiki is explicit: interfaces generally belong in
the package that *uses* values of the interface type; the implementing package
returns concrete types; do not define an interface before it is used, and do
not define one on the implementor side "for mocking".

```go
// storage/s3.go — the implementer returns a concrete type.
type S3 struct{ client *s3.Client; bucket string }
func NewS3(c *s3.Client, bucket string) *S3 { ... }
func (s *S3) Upload(ctx context.Context, name string, r io.Reader) error { ... }

// attach/handler.go — the consumer declares only what it calls.
// Exported only because a factory in cmd/ must name it (see Factories).
type Uploader interface {
	Upload(ctx context.Context, name string, r io.Reader) error
}

type Handler struct{ store Uploader }
```

Review signals:

- An exported interface in the same package as its only implementation, with a
  `New...` returning the interface → speculative. Return the struct.
- An interface with many methods where each consumer calls one or two → split
  it at the consumer. `golangci-lint`'s `interfacebloat` (default `max: 10`)
  catches the extreme case; the real target is "methods the consumer uses".
- `ireturn` flags functions returning interfaces; useful as a nudge, not a law
  (`error`, `io.Reader` returns are fine).

## Embedding is not inheritance

Embedding promotes the embedded type's methods onto the outer type. That is
delegation with automatic forwarding — not an is-a relation, and not a
virtual dispatch.

```go
type auth struct{ token string }
func (a auth) LoggedIn() bool { return a.token != "" }

type payment struct{ status string }
func (p payment) Valid() bool { return p.status == "active" }

type user struct{ id string }

type paidUser struct {
	user
	auth
	payment
}

func (u paidUser) HasFeature(f string) bool {
	return u.LoggedIn() && u.Valid() && lookup(u.id, f)
}

type trialUser struct {
	user
	auth
}

func (u trialUser) HasFeature(f string) bool { return u.LoggedIn() && lookup(u.id, f) }

type guestUser struct{ user }

func (guestUser) HasFeature(f string) bool { return guestFeatures[f] }

// The consumer depends on one method; three implementations earn it.
type features interface{ HasFeature(string) bool }
```

Pitfalls to check in review:

1. **No virtual dispatch.** If `auth.Describe()` calls `a.Name()`, it calls
   `auth.Name`, never the outer type's `Name`. Code that relies on "overriding"
   a method of an embedded type is a bug waiting for the second call site.
2. **API leakage.** Every exported method of an embedded type becomes part of
   the outer type's exported API. Embedding `sync.Mutex` in an exported struct
   exposes `Lock`/`Unlock` to every caller. Use a named field (`mu
   sync.Mutex`) unless promotion is the point.
3. **Ambiguous selectors.** Two embedded types with the same method name at the
   same depth compile until someone calls it, then fail. Adding a method to an
   embedded type can break the outer type's callers.
4. **Embedding an interface in a struct** gives a type that satisfies the
   interface with nil methods that panic. Acceptable only for test fakes that
   implement a subset deliberately; never in production code.
5. **Pointer vs value embedding.** Embedding `*T` shares state between copies
   of the outer struct; embedding `T` copies it. Pick on purpose.

Prefer a named field when the outer type should *use* a capability; embed when
it should *present* that capability as its own.

## IO at the edges: the standard seams

| Concern | Seam | In-memory implementation |
|---|---|---|
| Read files | `io/fs.FS` | `testing/fstest.MapFS` |
| Write bytes | `io.Writer` | `bytes.Buffer` |
| Time | `func() time.Time` field, or a small `Clock` interface | fixed func; `testing/synctest` (Go 1.25+) for timers |
| HTTP out | `*http.Client` with a custom `Transport`, or consumer interface | `httptest.Server`, `RoundTripper` func |
| Randomness | `*rand.Rand` or `io.Reader` | seeded source |

`fs.FS` names are checked by `fs.ValidPath` (no rooted paths, no `..`), so a
user-supplied name cannot climb out of the tree. Two limits: `os.DirFS` does
not stop a symlink inside the directory from pointing outside it, and a custom
`fs.FS` is only *expected* to call `ValidPath`. For containment on disk, build
the edge's filesystem with `os.OpenRoot(dir)` then `root.FS()` (Go 1.24+),
which refuses to follow links out of the root.

## Ordering as a type

```go
// Before: Cycles compiles before Resolve and silently returns nil.
cat.Resolve(scope)
cycles := cat.Cycles()

// After: only a resolved graph has Cycles.
g, err := cat.Resolve(scope)
if err != nil { return err }
cycles := g.Cycles()
```

The type-state pattern costs one extra type. It pays when the wrong order
produces a plausible zero value rather than an error.

## Package-level state

Search with the shared command in `principles-audit/references/go.md`
("Package-level state"); it catches `var x = ...`, `var x T` and `var (`
blocks. Every hit needs reading — constants-by-convention and `//go:embed`
vars are fine.

- `init()` self-registration (`database/sql` drivers, `image` decoders) is the
  standard library's own singleton; accept it at the boundary, do not copy it.
- `//go:embed` forces a package-level var; that is a read-only exception.
- An exported `var Defaults = map[...]` is mutable by any importer. Return a
  fresh value from a function instead.

## Factories

A factory earns its place when the implementation is chosen at runtime from
data (config, MIME type, tenant). In Go it is usually a plain function with a
switch, not a registry.

Place it where the consumer's interface can be named: at the edge (`main`,
`cmd/`) or in the consuming package — not in the `storage` package, which
would then need an implementer-side interface. This is the one place the
"consumer declares the interface" rule bites: a data-driven factory must
return *some* interface, so it lives with the consumer. (Python's structural
`Protocol` sidesteps this; Elixir returns a module.)

```go
// cmd/server/storage.go, or package attach
func newStorage(cfg Config) (attach.Uploader, error) {
	switch cfg.Kind {
	case "s3":
		return storage.NewS3(cfg.S3Client, cfg.Bucket), nil
	case "sftp":
		return storage.NewSFTP(cfg.SFTP)
	case "webdav":
		return storage.NewWebDAV(cfg.WebDAVURL), nil
	default:
		return nil, fmt.Errorf("storage kind %q: want s3, sftp or webdav", cfg.Kind)
	}
}
```

A `map[string]func() T` registry filled by `init()` is the over-abstraction
version of the same thing.

## Linters that support these rules

- `interfacebloat`, `ireturn` — interface size and returns.
- `gochecknoinits`, `gochecknoglobals` — `init()` and package vars.
- `forbidigo` / `depguard` — ban `os`, `net/http` imports in pipeline packages.
