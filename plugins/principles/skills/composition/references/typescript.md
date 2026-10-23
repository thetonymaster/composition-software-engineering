# Composition in TypeScript

TypeScript types are structural, so Go-style consumer-side interfaces come for
free. JavaScript classes make `extends` cheap, and frameworks (NestJS,
Angular, TypeORM) add base classes and decorators. Both failure directions are
common: deep class hierarchies, and `IFoo` interfaces declared next to their
only `Foo`.

## Interfaces at the consumer

Any value with matching members satisfies an interface; no `implements`, no
import of the declaring module. Declare the interface where it is called.

```ts
// attachments/handler.ts — the consumer declares what it calls.
export interface Uploader {
  upload(name: string, data: Uint8Array): Promise<void>;
}

export class AttachmentHandler {
  constructor(private readonly store: Uploader) {}

  handle(name: string, data: Uint8Array): Promise<void> {
    return this.store.upload(name, data);
  }
}

// storage/s3.ts — knows nothing about Uploader.
export class S3Storage {
  constructor(private readonly bucket: string) {}
  async upload(name: string, data: Uint8Array): Promise<void> { /* ... */ }
}
```

`implements Uploader` is optional: it moves the error to the class instead of
the call site, at the cost of the implementer importing the consumer's type.

Review signals:

- `interface IFoo` plus one `class Foo implements IFoo`, no fake, no second
  implementation → delete the interface; use `Foo`.
- An `abstract class` with one subclass → same.
- A wide interface where the consumer calls two members → declare a narrow
  one, or `Pick<Wide, "a" | "b">`.

## Structural typing cuts both ways

Two types with the same shape are interchangeable. Type-state ordering and
"distinct ID" types only hold if the shapes differ. A class with a `private`
or `#private` member is compared nominally for that member, so it cannot be
forged by a lookalike object; a plain `interface` can.

## Inheritance traps specific to TypeScript

1. **Methods are virtual.** Unlike Go embedding, a base method calling
   `this.validate()` runs the subclass override. A base *constructor* calling
   an overridable method runs it before the subclass's field initialisers:
   `this.tags.push(...)` throws on `undefined`. `tsc --strict` does not catch
   it.

   ```ts
   class Base {
     constructor() { this.init(); }
     protected init(): void {}
   }
   class Child extends Base {
     private readonly tags: string[] = [];
     protected override init(): void { this.tags.push("x"); } // TypeError at new Child()
   }
   ```

2. **`protected` is API.** Every subclass can read it. Treat a subclass
   touching parent state as a coupling finding. Enable `noImplicitOverride`
   so every override is marked `override` and a renamed base method breaks
   the build instead of silently orphaning the override.
3. **Stub overrides.** A method that only `throw new Error("not supported")`
   is the `DrawableImage` problem. Split the capability out.
4. **Mixins** (`const Timestamped = <T extends Ctor>(B: T) => class extends
   B {...}`) insert classes into the prototype chain. `super.save()` reaches
   whichever mixin was applied next, so behaviour depends on application
   order — Python's MRO problem. Private members in an exported mixin also
   fail declaration emit (`TS4094`). Prefer a composed field
   (`this.clock = clock`).
5. **Decorators are hidden behaviour.** `@Retry()`, `@Cacheable()`,
   `@Transactional()` change what a method does with nothing at the call
   site; stacked decorators apply bottom-up. Legacy `experimentalDecorators`
   and TC39 decorators (TS 5.0+) are incompatible, and `emitDecoratorMetadata`
   exists only for the legacy form. Node's built-in type stripping rejects
   decorator syntax. Prefer an explicit wrapper:
   `const fetchUser = withRetry(rawFetchUser, { attempts: 3 })`.
6. **Framework-mandated inheritance** (`extends Error`, NestJS/Angular base
   classes) is fine — the framework is the second implementation. Keep the
   subclass thin and delegate to plain functions.

## Image example, composed

```ts
class Image {
  constructor(public pixels: number[][]) {}
  flip(): void { this.pixels.reverse(); }
}

interface ImageFile {
  load(src: Uint8Array): Image;
  save(img: Image): Uint8Array;
}

const png: ImageFile = {
  load: (src) => new Image([[...src]]),
  save: (img) => Uint8Array.from(img.pixels.flat()),
};

class ImageDraw {
  constructor(private readonly img: Image) {}
  dot(x: number, y: number): void { this.img.pixels[y]![x] = 1; }
}
```

A codec is a plain object; no class hierarchy is needed for a two-method
contract.

## IO at the edges

| Concern | Seam | Test implementation |
|---|---|---|
| Read files | `read: (name: string) => Promise<Uint8Array>` or a small interface | `Map`-backed fake; `memfs` |
| Write bytes | `Writable` / `WritableStream` / `(chunk: Uint8Array) => void` | collect into an array; `PassThrough` |
| Time | `now: () => Date` | `() => FIXED`; `vi.useFakeTimers()` for timers |
| HTTP out | `fetch: typeof fetch` parameter | `async () => new Response(...)`; undici `MockAgent`; `msw` |
| Randomness | `random: () => number` | fixed sequence |

Node has no `fs.FS` equivalent. When joining a user-supplied name under a
root, `path.resolve(root, name)`, then reject when
`path.relative(root, resolved)` starts with `..` or is absolute; call
`fs.realpath` first if symlinks can exist. For process-wide containment, run
with `node --permission --allow-fs-read=<dir>`.

## Module-level state

Search with the shared commands in `principles-audit/references/typescript.md`
("Module-level clients / singletons").

- `export const s3 = new S3Client({...})` is a singleton: the module loader
  caches it, it is built at import time, and tests need `vi.mock`/`jest.mock`.
  Construct it in the composition root and pass it down.
- `let cached: Config | undefined` plus `getConfig()` lazy-init is Go's
  `sync.Once`.
- `export const DEFAULTS = {...} as const` is readonly to the type checker
  only; any importer can still mutate it at runtime. `Object.freeze` it or
  return a fresh value from a function.
- Needing `vi.mock("./s3")` to test something is the signal: the dependency
  is hardwired.

## Ordering as a type

```ts
class Catalog {
  resolve(scope: string): ResolvedGraph { return new ResolvedGraph([scope]); }
}

class ResolvedGraph {
  readonly #edges: string[];          // private member: not forgeable
  constructor(edges: string[]) { this.#edges = edges; }
  cycles(): string[][] { return this.#edges.length > 1 ? [this.#edges] : []; }
}

// cat.cycles() does not exist; only the resolved graph has it.
const graph = new Catalog().resolve("svc");
graph.cycles();
```

## Linters and compiler flags

- `tsc`: `strict`, `noImplicitOverride`. Set `strict: true` explicitly in
  `tsconfig.json`; older compilers default it to false.
- ESLint `max-params` (default 3) — many constructor parameters often mean a
  missing composed object, or a unit with two jobs.
- `@typescript-eslint/no-extraneous-class` — static-only classes used as
  namespaces or singletons.
- `no-restricted-imports` per directory (flat-config `files` glob) to ban
  `node:fs`, `node:http`, SDK clients in core code; `dependency-cruiser` or
  `eslint-plugin-import`'s `no-restricted-paths` for layer rules.
