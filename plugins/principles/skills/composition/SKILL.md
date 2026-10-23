---
name: composition
description: Use when reaching for an abstraction, designing how components fit together, or reviewing whether an existing abstraction earns its keep — and when reaching for inheritance, a base class, a mixin, Go struct embedding or an Elixir `use` macro. Covers IO at the edges, the second-implementation test, ordering as a compile error, composition over inheritance, and the symmetric risk of over-abstraction, with Go, Python and Elixir references.
---

# Composition

The summary lives in CLAUDE.md. This is the reasoning, the tests to apply, and
worked examples in both directions.

## The one test that decides most cases

**Does a second implementation exist right now, or in a plan already committed
to?**

- Yes → the abstraction is earned. Build it.
- No → it is speculative generality. Write the concrete thing.

"I can imagine a second one" does not count. Neither does "we might need to
swap this later." Both are how ceremony enters a codebase and never leaves.

## IO at the edges

Push every side effect to the outermost layer:

- Reads take a filesystem abstraction (Go: `io/fs.FS`; elsewhere: an injected
  reader). Never a root path string plus direct `os` calls.
- Writes take a writer. The command layer decides where bytes land.
- Time, randomness and the network are injected, not called.

You get three things at once, and the third is the one people forget:

1. A second source works with no code change — a tarball, a remote fetch, an
   archive — because it is the same interface.
2. Tests run against an in-memory filesystem: no disk, no network, no fixtures
   to clean up. The suite passes on a plane.
3. **A security property.** `io/fs.FS` names reject absolute paths and `..`
   (`fs.ValidPath`), so a user-supplied *name* cannot climb out of the tree.
   That is enforcement, not convention — with two limits: `os.DirFS` still
   follows a symlink inside the tree that points outside it, and a custom
   `fs.FS` is only expected to call `ValidPath`. For real containment on
   disk, use `os.OpenRoot(dir)` and `root.FS()` (Go 1.24+).

Read-only abstractions do not cover writes. Decide the write story at the same
time, or the "no direct IO" rule gets quietly broken the first time someone
needs to create a file — and an absolute rule that has to be broken teaches
contributors to ignore the rules.

## Make ordering a compile error

If stage B requires stage A to have run, B should take A's **return type**.

The failure this prevents is specific and nasty: a method that mutates hidden
state, and accessors that return a valid-looking empty answer when it hasn't
run yet.

```go
// Before: compiles, silently returns zero cycles on an unresolved catalog.
cat.Resolve(scope, collector)
cycles := cat.Cycles()

// After: Cycles is on the value Resolve returns, so the wrong order
// does not compile.
g := cat.Resolve(scope, collector)
cycles := g.Cycles()
```

A silently wrong answer is worse than a crash. If a claim like "ordering bugs
are compile errors" appears in a design doc, verify it for the one constraint
that is not obvious — that is exactly where it tends to be false.

## No package-level mutable state

No singletons, no `init()` self-registration, no `sync.Once` hiding
initialisation. Things that need configuring are values you construct and pass.

The cost of a singleton is not style. It is that two configurations cannot
coexist — so a migration where old and new formats must both be readable
becomes impossible without a rewrite — and that the failure path of
initialisation cannot be tested.

An exported slice or map is still mutable by any importer. If the rule matters,
say what is actually true rather than overclaiming.

## The other direction: over-abstraction

Under-abstraction is not the only failure, and it is not always the one you
have. Signals that an abstraction is not paying rent:

- One implementation, and no committed plan for a second.
- Its only consumer is a test that invents its own subject to justify it.
- A registry, factory or plugin layer where a map literal or a switch would do.
- A stated benefit that is not actually delivered — e.g. "adding one requires
  editing no existing file" when adding one requires editing the registry.

When you catch the last case, fix the claim as well as the code. A criterion
that cannot be met teaches contributors either to believe something false about
the codebase, or to break another rule to satisfy it.

**Worked example.** In one review three abstractions survived attack and one
did not. An `fs.FS` seam survived: three implementations already existed in the
same plan. A validator-as-a-value survived: six lines more than a package
function, and it made a real failure path testable. Four small formatter types
survived: four real implementations, clearly better than a sixty-line switch.
The registry *holding* those four types did not: one instance, ever, and its
only consumer was a test written to justify it. Keep the interface, delete the
registry, use a map.

## Compose capabilities, do not inherit them

Inheritance bundles two things: code reuse and a type contract. The bundle
breaks the first time a new variant needs the contract but not the reuse.

**Worked example.** An abstract `Image` holds pixels, implements `resize` and
`flip`, and declares abstract `load`/`save`; `Jpeg`, `Png`, `Bitmap` subclass
it. Then `DrawableImage` arrives — in memory only, never a file. It must stub
`load`/`save`, or a `FileImage` layer gets wedged into the hierarchy and every
subclass moves. Composed instead: `Image` is a concrete value with
`resize`/`flip`; `Jpeg`, `Png`, `Bitmap` are standalone codecs that take an
`Image` and satisfy a two-method `ImageFile` contract; `ImageDraw` takes an
`Image`. Load a bitmap, flip it, draw on it, save as PNG — no existing type
changed.

The same split by capability, without a class hierarchy: a `user` value plus
separate `auth` and `payment` parts, assembled per tier — paid = user + auth +
payment, trial = user + auth, guest = user. Each tier answers `hasFeature` its
own way; callers depend only on the one-method contract. Three tiers exist, so
the contract passes the second-implementation test.

Signals of inheritance pain in review:

- A subclass method that raises "not supported" or returns a dummy value.
- A new requirement that forces an intermediate base class.
- `protected` fields read by subclasses — the parent's internals are now API.

Where inheritance is unavoidable (a legacy plugin base, a framework that
demands it), seal it: no protected state, one explicit overridable hook API,
everything else private/final.

## Language references

Composition looks different in each language — Go has no inheritance but has
embedding traps; Python has ABCs, Protocols and mixins; Elixir has behaviours,
protocols and `use`. Load the one that matches the code under review:

- **`references/go.md`** — consumer-side interfaces, embedding pitfalls,
  `fs.FS`/`io.Writer` seams, ordering as types, package state.
- **`references/python.md`** — `Protocol` vs `ABC`, mixins and the MRO,
  injecting IO, module-level singletons.
- **`references/elixir.md`** — behaviours vs protocols, `use` as hidden
  inheritance, processes as state, Application env as a global.

Related skills: `dependency-injection` (how a seam gets its implementation),
`flat-code`, `measure-first`, and `principles-audit` to review a change against
all of them.

## Checklist

1. Name the second implementation. Cannot? Stop.
2. Does this unit do IO? Push it outward.
3. Is there an ordering constraint? Make it a type.
4. Any hidden global? Make it a constructed value.
5. Is reuse coming from a parent type? Compose the capability instead.
6. Does every stated benefit actually hold? Test the claim, not the intention.
