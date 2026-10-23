# Flat code in TypeScript

`async`/`await` removed callback pyramids, but the same depth comes back
through a `try` around the whole body, `.then` chains inside `if`s, and
`forEach(async ...)` callbacks. The bonus in TypeScript: a guard clause also
narrows the type, so the code after it needs no `!` or `?.`.

## Guard clauses

```ts
// Avoid
function chargeNested(user: User | undefined): Receipt {
  if (user) {
    if (user.active) {
      if (user.quota > 0) {
        return bill(user);
      } else {
        throw new QuotaExceeded(user.id);
      }
    } else {
      throw new Inactive(user.id);
    }
  } else {
    throw new Error("charge: user is undefined");
  }
}

// Prefer — after the first guard, `user` is narrowed to `User`.
function charge(user: User | undefined): Receipt {
  if (!user) throw new Error("charge: user is undefined");
  if (!user.active) throw new Inactive(user.id);
  if (user.quota <= 0) throw new QuotaExceeded(user.id);
  return bill(user);
}
```

## Early return in async code

```ts
// Avoid: the whole body is in the try; the catch hides which await failed.
async function syncAllNested(path: string): Promise<void> {
  try {
    const cfg = await load(path);
    for (const item of cfg.items) {
      if (item.enabled) {
        await syncItem(item);
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// Prefer: the try wraps only the call whose error is handled.
async function syncAll(path: string): Promise<void> {
  let cfg: Config;
  try {
    cfg = await load(path);
  } catch (err) {
    throw new Error(`load ${path}`, { cause: err });
  }
  for (const item of cfg.items) {
    if (!item.enabled) continue;
    await syncItem(item);
  }
}
```

- `items.forEach(async (i) => ...)` does not await its callbacks: it adds a
  level *and* drops errors. Use `for...of` with `continue`, or
  `await Promise.all(items.filter(isEnabled).map(syncItem))` for concurrency.
- Do not mix `.then()` chains into an `async` function; `await` each step at
  one level.

## Optional chaining and nullish coalescing

```ts
const city = order?.customer?.address?.city ?? "unknown";
```

replaces three nested `if`s for data that may legitimately be absent. `??`
falls back only on `null`/`undefined`; `||` also replaces `0` and `""`. Do not
use `?.` to silence a value that must exist — that is a silent fallback; guard
and throw with the offending value instead.

## Discriminated unions and exhaustive switch

The downloader's state dispatch, flat and checked by the compiler:

```ts
type Download =
  | { state: "pending"; url: string }
  | { state: "inProgress"; url: string; attempts: number }
  | { state: "complete"; path: string };

function step(d: Download): Download {
  switch (d.state) {
    case "pending":
      return processPending(d);
    case "inProgress":
      return processInProgress(d);
    case "complete":
      return d;
    default:
      return assertNever(d);
  }
}

function assertNever(x: never): never {
  throw new Error(`unhandled download state: ${JSON.stringify(x)}`);
}
```

Each case narrows `d`, so `processInProgress` can take the
`{ state: "inProgress" }` member only. Adding a state without a case fails
to compile at `assertNever(d)`. When the cases are data, a lookup object
checked with `satisfies Record<Download["state"], ...>` does the same job.

## Other flattening tools

- `filter` / `some` / `every` / `find` instead of a loop with a flag — but a
  `.map` whose callback holds two `if`s is nesting on one line.
- `node:fs/promises`, `util.promisify`, `events.once` to turn callback APIs
  into one-level `await`s.
- A named function instead of a closure defined inside a loop inside a
  function; pass its state explicitly.

## Linters

| Rule | What | Default |
|---|---|---|
| `max-depth` | nested blocks; the function body is 0, so skill depth 3 = `["error", 2]` | 4 |
| `no-else-return` | `else` after `return`; `{ allowElseIf: false }` also flags `else if` | `allowElseIf: true` |
| `no-lonely-if` | `if` as the only statement in an `else` | — |
| `complexity` | cyclomatic complexity | 20 |
| `sonarjs/cognitive-complexity` | weights nesting | 15 |
| `@typescript-eslint/switch-exhaustiveness-check` | missing union cases (needs type info) | — |
| `@typescript-eslint/prefer-optional-chain` | `a && a.b && a.b.c` (needs type info) | — |

`tsc` flags `noImplicitReturns` and `noFallthroughCasesInSwitch` catch the
branch that forgot to `return` or `break`. `scripts/nesting_depth.py` does not
read `.ts`; use `max-depth` instead.
