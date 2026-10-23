# Flat code in Java

Java nests fast: a method inside a class, a `try` around the body, a `for`
over a collection, an `if` per condition. Checked exceptions add a `try`
level wherever IO happens, and `Optional` used as a null check adds
`isPresent()` blocks. Modern Java (14+) has the tools to flatten most of it.

## Guard clauses

```java
// Avoid
String charge(User user) {
    if (user != null) {
        if (user.active()) {
            if (user.quota() > 0) {
                return bill(user);
            } else {
                throw new QuotaExceeded(user.id());
            }
        } else {
            throw new Inactive(user.id());
        }
    } else {
        throw new IllegalArgumentException("charge: user is null");
    }
}

// Prefer
String charge(User user) {
    if (user == null) {
        throw new IllegalArgumentException("charge: user is null");
    }
    if (!user.active()) {
        throw new Inactive(user.id());
    }
    if (user.quota() <= 0) {
        throw new QuotaExceeded(user.id());
    }
    return bill(user);
}
```

In loops, `continue` is the guard. Disable "single exit point" rules
(PMD `OnlyOneReturn`, a tight Checkstyle `ReturnCount`): they forbid exactly
this shape.

## Narrow `try`

```java
// Prefer: the try wraps only the call that throws the handled exception.
Config cfg;
try {
    cfg = load(path);
} catch (IOException e) {
    throw new ConfigException("load " + path + ": " + e.getMessage(), e);
}
for (Item item : cfg.items()) {
    if (!item.enabled()) {
        continue;
    }
    process(item);
}
```

A `try` around the whole body pushes everything down a level and hides which
call failed. Use try-with-resources with several resources in one header
(`try (var in = ...; var out = ...)`) instead of stacked `try` blocks.

## Optional: chain, do not unwrap

```java
// Avoid: Optional used as a null check, one level per step.
if (user.email().isPresent()) {
    String e = user.email().get();
    if (e.contains("@")) {
        return e.substring(e.indexOf('@') + 1);
    }
}
return "unknown";

// Prefer
return user.email()
    .filter(e -> e.contains("@"))
    .map(e -> e.substring(e.indexOf('@') + 1))
    .orElse("unknown");
```

- `orElse(x)` evaluates `x` even when a value is present; use
  `orElseGet(() -> ...)` when the default is computed.
- `orElseThrow(() -> new NotFound(id))` is a guard clause in one line.
- `Optional` is for return values. As a field or parameter it adds a third
  state (`null`, empty, present) and more branches.

## switch expressions and patterns

```java
// Enum switch expression (14+): no fall-through, and a missing constant
// without `default` is a compile error.
String step(Download d) {
    return switch (d.state()) {
        case PENDING -> processPending(d);
        case IN_PROGRESS -> processInProgress(d);
        case COMPLETE -> clearCompleted(d);
    };
}

// instanceof pattern (16+) as a guard
if (!(o instanceof String s)) {
    return 0;
}
return s.length();
```

Pattern-matching `switch` on types and sealed hierarchies is final in Java
21; on 17 it is a preview feature (`--enable-preview`). Prefer an enum
switch expression or polymorphism over an `if (x instanceof A) ... else if
(x instanceof B)` ladder.

## Streams vs loops

- `filter`/`map`/`toList()` replaces `for` + `if` + `add`;
  `anyMatch`/`findFirst` replace search loops with a flag.
- A lambda with a block body containing `if`/`try` is nesting inside a
  pipeline. Extract it to a named method (`.map(this::toInvoice)`).
- Checked exceptions do not cross lambdas; wrapping each call in
  `try/catch` inside `map` is worse than a plain loop. Use the loop.
- Stream code is not automatically faster or slower; the choice here is
  readability. See `measure-first` before arguing performance.

Anonymous inner classes and multi-line lambdas inside a loop inside a method
start at depth 3. Lift them to a named method; when extracted helpers need
the same five locals, pass one record instead of five parameters.

## Linters

| Tool | Rule | Default |
|---|---|---|
| Checkstyle | `NestedIfDepth` | `max` 1 (flags a third nested `if`) |
| Checkstyle | `NestedForDepth`, `NestedTryDepth` | `max` 1 each |
| Checkstyle | `CyclomaticComplexity` / `NPathComplexity` | 10 / 200 |
| Checkstyle | `MethodLength` / `ReturnCount` | 150 lines / `max` 2 (loosen it, see above) |
| PMD | `design.xml/AvoidDeeplyNestedIfStmts` | `problemDepth` 3 (flags a third nested `if`) |
| PMD | `design.xml/CognitiveComplexity` | `reportLevel` 15 |
| PMD | `design.xml/CyclomaticComplexity`, `NPathComplexity` | per-method thresholds |

Checkstyle's and PMD's nested-if counts ignore loops and `try`. A method
body of `for` → `if` → `for` → `if` (depth 5) passes all of the rules above
at their defaults; `CognitiveComplexity`, which weights all nesting, scores it
10 against a default threshold of 15. Lower `reportLevel` (around 8) or read
indentation to catch it. No Checkstyle or PMD rule flags
`else` after `return`; grep for it (`principles-audit/references/java.md`).

`scripts/nesting_depth.py` does not read `.java` files: it reports nothing
and exits 0. Use the linters above for Java.
