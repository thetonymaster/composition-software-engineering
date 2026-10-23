---
name: dependency-injection
description: This skill should be used when code hardcodes a dependency (a client constructed inline, a global, a direct call to disk/network/clock), when a test needs monkeypatching or mocking of private internals, when one function grows if/else branches per backend ("upload to S3, or SFTP, or WebDAV"), or when the user asks to "make this testable", "inject this", "add a fake", "swap the implementation", "add a factory", or "decouple this". Covers constructor injection, where to choose the implementation, fakes vs mocks, and when NOT to inject — in Go, Python, Elixir, TypeScript, Java, Rust and C#.
---

# Dependency injection

Pass a dependency in instead of constructing or calling it from inside. The
caller decides *which* implementation; the code only knows the contract.

This is the mechanism behind the `composition` skill's seams. It is subject to
the same discipline: a seam must name its second implementation.

## What counts as a second implementation

Inject when at least one holds:

1. **The dependency is outside the process** — network, disk, clock,
   randomness, a third-party API, a queue. The real one is slow,
   non-deterministic or costs money, so a fake is a genuine second
   implementation, not an invented one.
2. **The implementation is chosen at runtime from data** — tenant config, file
   MIME type, environment (dev scanner vs prod scanner).
3. **Two implementations exist today** or in a committed plan.

Do not inject pure in-process logic (a parser, a formatter, a validator)
just to mock it. Test it directly. A mock of pure logic tests the mock.

## The shape

```
main / app start            ← reads config, builds concrete dependencies
  └── factory(config)        ← only if the choice depends on data
        └── Handler(store)   ← receives the contract, calls store.upload()
```

- **Construct at the edge.** One place — `main`, the application supervisor,
  the app factory — builds real clients. Configuration lives there and nowhere
  else.
- **Constructor/parameter injection** over setters, service locators or
  containers. A dependency passed to the constructor is visible in the
  signature; a looked-up one is hidden.
- **Factory only when selection depends on data.** A factory is a function
  with a switch over the config value that returns the contract. Not a
  registry, not reflection.
- **Fail at construction.** A factory given an unknown kind returns an error
  naming the value and the accepted ones (`storage kind "ftp": want s3, sftp
  or webdav`). Never fall back silently to a default implementation.

## The multi-destination example

Before: `upload(file, aws_key=None, sftp_key=None, webdav_url=None)` with one
branch per destination; every new destination edits this function and widens
its signature.

After: an `AttachmentStorage` contract with `upload`; `S3`, `SFTP`, `WebDAV`
implement it, each holding only its own credentials; `storage_for(company)`
reads company config and returns one; the request handler receives it and
calls `upload` without knowing the destination.

The same shape covers environment swaps (inject the new virus scanner in dev,
the old one in prod, same contract) and data-driven choice (a factory maps a
MIME type to a preview generator, which itself receives an injected image
scaler — earned because the scaler is a native library (Sharp/libvips), i.e.
outside the process's own code, and is shared by several generators).

## Fakes over mocks

- A **fake** is a small working implementation (in-memory store, local S3
  stand-in, an encryptor that returns the input). It survives refactors and
  lets tests assert on outcomes.
- A **mock** asserts calls. Use it for the one interaction that *is* the
  behaviour (an email was sent exactly once), not for every collaborator.
- Isolate one thing at a time: to test the S3 adapter, inject a fake S3 server
  and a pass-through encryptor so corruption is visible; to test encryption,
  inject a fake key store into the real encryptor.

## Signals that injection is missing

- A test needs `monkeypatch`, `mock.patch("pkg.mod.Client")`, `Application.put_env`
  in a test, a package var swapped in Go, or reflection to reach a private
  field.
- A test wants to call a private method. Extract that logic into its own
  unit and inject it, or test it through the public API.
- A constructor with optional parameters for each backend's credentials.
- Code reads env vars or config files below the entry point.

## Signals that injection is excessive

- An interface/behaviour/Protocol with one implementation and no test fake,
  no runtime choice, and no outside-the-process dependency.
- A DI container or registry in a codebase with a handful of services.
- Injected dependencies that are never varied anywhere, including tests.
- More than ~5 injected parameters: the unit probably has two jobs. Split it
  rather than bundling the parameters into a "context" bag.

## Checklist

1. Which of the three conditions makes this seam real? Name it.
2. Where is the implementation constructed? It should be one edge location.
3. If chosen by data, is there exactly one factory, failing loudly on unknown
   input?
4. Can the unit's tests run with no network, no disk, no real clock?
5. Did any test need monkeypatching to pass? That is the next seam.

## Language references

- **`references/go.md`** — consumer interfaces, constructor functions,
  functional options, `httptest`, func-typed dependencies.
- **`references/python.md`** — constructor params with Protocols, app
  factories, pytest fixtures, `httpx.MockTransport`, why `mock.patch` is a
  smell.
- **`references/elixir.md`** — behaviours + Mox, adapter via options vs
  Application env, `Req.Test`, compile-time vs runtime config.
- **`references/typescript.md`** — constructor params typed by interface,
  composition root with an exhaustive `never` factory, fakes vs `vi.fn`, why
  `vi.mock` is a smell.
- **`references/java.md`** — constructor injection into final fields, `Clock`,
  wiring in `main` vs Spring/Guice, field-injection pitfalls, fakes vs Mockito.
- **`references/rust.md`** — generic params vs `Box`/`Arc<dyn Trait>`, `new`
  constructors, wiring in `main`, hand-written fakes vs `mockall`.
- **`references/csharp.md`** — constructor injection, composition root in
  `Program.cs`, lifetimes and captive dependencies, keyed services,
  `FakeTimeProvider`, the service-locator smell.

Related: `composition` (whether the seam should exist), `principles-audit`.
