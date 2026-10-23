# Dependency injection in Go

Go needs no framework: a struct field of interface or func type, set by a
constructor, is the whole mechanism. Wire-up happens in `main` (or
`cmd/<name>/`). Generators like `google/wire` and containers like `uber/fx`
exist; reach for them only when hand wiring in `main` passes a few hundred
lines.

## Constructor injection

```go
type Uploader interface { // exported: the factory in cmd/ returns it
	Upload(ctx context.Context, name string, r io.Reader) error
}

type scanner interface {
	Scan(ctx context.Context, r io.Reader) (clean bool, err error)
}

type Handler struct {
	store Uploader
	scan  scanner
	now   func() time.Time
}

func NewHandler(store Uploader, scan scanner, now func() time.Time) *Handler {
	return &Handler{store: store, scan: scan, now: now}
}
```

- Interfaces are declared by the consumer (`attach` package), unexported if
  only it uses them.
- A single-method dependency can be a func type (`now func() time.Time`,
  `type LastEditFunc func(ctx context.Context, path string) (time.Time, error)`). No interface
  needed; tests pass a closure.
- Return concrete types from constructors (`*Handler`, `*S3`).

## Wiring in main

```go
func run(ctx context.Context, cfg Config, stdout io.Writer) error {
	store, err := newStorage(cfg.Storage) // factory in cmd/: switch on Kind, returns attach.Uploader
	if err != nil {
		return fmt.Errorf("storage: %w", err)
	}
	h := attach.NewHandler(store, virus.New(cfg.Scanner), time.Now)
	return serve(ctx, h, stdout)
}

func main() {
	if err := run(context.Background(), loadConfig(), os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

The `run` function taking its dependencies (including `stdout`, args, env
lookups) makes `main` itself testable.

## Functional options — only for optional knobs

```go
type Option func(*Client)

func WithHTTPClient(c *http.Client) Option { return func(cl *Client) { cl.http = c } }

func NewClient(base string, opts ...Option) *Client {
	c := &Client{base: base, http: http.DefaultClient}
	for _, o := range opts { o(c) }
	return c
}
```

Required dependencies stay positional. Options hiding a required dependency
behind a default (`http.DefaultClient`, `time.Now`) are acceptable only when
the default is correct in production.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP API | `httptest.NewServer` with a handler; or `http.Client{Transport: roundTripFunc(...)}` |
| Filesystem read | `fstest.MapFS` |
| Writer | `bytes.Buffer` |
| Clock | `func() time.Time { return fixed }`; `testing/synctest` for timers and sleeps (Go 1.25+) |
| Consumer interface | a hand-written fake struct in `_test.go` |

Hand-written fakes are usually shorter than generated mocks (`gomock`,
`mockery`) for interfaces of 1–3 methods, and they do not break on argument
reordering. Generated mocks pay off for wide third-party interfaces.

## Smells

- A package-level `var httpClient = &http.Client{}` or `var now = time.Now`
  swapped in tests → not parallel-safe; move it to a field.
- `os.Getenv` below `cmd/` → read once in `main`, pass the value.
- An interface in `internal/foo` with `NewFoo() Foo` returning it and one
  implementation → return `*Foo`, let consumers declare interfaces.
- `context.Context` used to carry dependencies (`ctx.Value(dbKey)`) → hidden
  injection; pass them explicitly. Context values are for request-scoped
  data such as trace IDs.
