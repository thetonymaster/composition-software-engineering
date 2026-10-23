# Dependency injection in TypeScript

`vi.mock` and `jest.mock` can replace any imported module, which is exactly
why injection gets skipped: module mocking makes hardwired code *testable*
without making it *decoupled*. Treat each module mock as a missing
constructor parameter.

## Constructor injection with interfaces

```ts
export interface Uploader {
  upload(name: string, data: Uint8Array): Promise<void>;
}

export interface Scanner {
  isClean(data: Uint8Array): Promise<boolean>;
}

export class AttachmentService {
  private readonly store: Uploader;
  private readonly scanner: Scanner;
  private readonly now: () => Date;

  constructor(store: Uploader, scanner: Scanner, now: () => Date = () => new Date()) {
    this.store = store;
    this.scanner = scanner;
    this.now = now;
  }

  async handle(name: string, data: Uint8Array): Promise<void> {
    if (!(await this.scanner.isClean(data))) {
      throw new Error(`attachment ${name}: failed virus scan`);
    }
    await this.store.upload(`${this.now().toISOString()}/${name}`, data);
  }
}
```

- Interfaces are structural and erased at runtime: the fake needs no
  `implements`, and nothing about the interface exists to look up later.
- Required collaborators have no defaults. A default is acceptable only when
  it is the correct production value and pure-ish (a clock), never a client
  built at import time.
- A single-function dependency is a function type (`now: () => Date`,
  `fetch: typeof fetch`). No interface needed; tests pass a closure.
- Parameter properties (`constructor(private readonly store: Uploader)`) are
  TypeScript-only syntax. Node's built-in type stripping rejects them, as
  does `erasableSyntaxOnly`; write explicit fields where that matters.

## Composition root and factory

```ts
type StorageConfig =
  | { kind: "s3"; bucket: string }
  | { kind: "sftp"; host: string; privateKey: string }
  | { kind: "webdav"; url: string };

export function storageFor(cfg: StorageConfig): Uploader {
  switch (cfg.kind) {
    case "s3":
      return new S3Storage(new S3Client({}), cfg.bucket);
    case "sftp":
      return new SftpStorage(cfg.host, cfg.privateKey);
    case "webdav":
      return new WebDavStorage(cfg.url);
    default: {
      const kind: never = cfg; // compile error if a kind is unhandled
      throw new Error(`storage kind ${JSON.stringify(kind)}: want s3, sftp or webdav`);
    }
  }
}
```

Config read from JSON or env is not checked by the type: parse it at the edge
(`zod`, `valibot`, or a hand-written check) before it reaches `storageFor`.
`main.ts` reads `process.env` once, builds the clients, calls the factory and
passes results into the services. Nothing below it reads env.

Containers (`tsyringe`, `inversify`) need runtime tokens because interfaces
are erased, and resolve dependencies from legacy-decorator metadata
(`emitDecoratorMetadata` + `reflect-metadata`). Justify one by service count,
not by habit. In NestJS the container is framework-mandated; keep logic in
classes that unit tests construct with `new Service(fake)`.

## When a plain import is fine

Pure in-process code — a parser, a formatter, `date-fns`, a validation
schema — is imported and called directly, and tested directly. Inject only
what meets one of the SKILL.md conditions: outside the process, chosen from
data, or two implementations today.

## Test doubles

| Dependency | Double |
|---|---|
| HTTP via `fetch` | inject `fetch`; the test passes `async () => new Response(body, { status: 200 })` |
| HTTP at the edge | undici `MockAgent` with `setGlobalDispatcher`; `msw` `setupServer` |
| AWS SDK v3 | inject the client; `aws-sdk-client-mock` |
| Files | `Map`-backed fake; `memfs`; `fs.mkdtemp` only for edge code |
| Clock | `now: () => FIXED`; `vi.useFakeTimers()` / `vi.setSystemTime()` for timers |
| Interface | an object literal or small class in the test file |

```ts
import { expect, test, vi } from "vitest";

class InMemoryStore {
  readonly files = new Map<string, Uint8Array>();
  async upload(name: string, data: Uint8Array): Promise<void> {
    this.files.set(name, data);
  }
}

test("stores a clean file under a timestamped name", async () => {
  const store = new InMemoryStore();
  const svc = new AttachmentService(store, { isClean: async () => true }, () => FIXED);
  await svc.handle("a.txt", new Uint8Array([104, 105]));
  expect([...store.files.keys()]).toEqual(["2026-01-01T00:00:00.000Z/a.txt"]);
});

test("a dirty file is never uploaded", async () => {
  const upload = vi.fn<Uploader["upload"]>();
  const svc = new AttachmentService({ upload }, { isClean: async () => false });
  await expect(svc.handle("x.exe", new Uint8Array())).rejects.toThrow("virus scan");
  expect(upload).not.toHaveBeenCalled();
});
```

`vi.fn<Uploader["upload"]>()` (jest: `jest.fn<...>()` from `@jest/globals`)
is type-checked against the real signature; use it for the one interaction
that *is* the behaviour, not for every collaborator.

## Smells

- `vi.mock("../storage/s3")` / `jest.mock(...)` → the module constructs its
  own dependency.
- `export const db = new Pool({ connectionString: process.env.DATABASE_URL })`
  → importing has side effects and reads env; move it to the composition root.
- `process.env.X` read inside business logic → parse settings once at
  startup and pass values.
- `(svc as any).privateMethod()` or `svc["privateMethod"]()` in tests → the
  logic wants extracting into its own injectable unit.
- An options object with optional credentials per backend
  (`{ awsKey?: string; sftpKey?: string; webdavUrl?: string }`) → the if/else
  upload function in disguise.
