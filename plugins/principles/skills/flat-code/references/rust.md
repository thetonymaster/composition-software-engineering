# Flat code in Rust

Rust gives inversion first-class syntax — `?`, `let ... else`, `match` with
guards — so deep nesting is usually a missed idiom. The Rust-specific trap is
rightward drift: `if let` inside `match` inside `for` inside a method inside
an `impl`, or a closure body inside an iterator chain.

## `?` instead of matching on `Result`

```rust
// Avoid
fn load(path: &Path) -> Result<Config, ConfigError> {
    match fs::read_to_string(path) {
        Ok(text) => match toml::from_str(&text) {
            Ok(cfg) => Ok(cfg),
            Err(e) => Err(ConfigError::Parse(e)),
        },
        Err(e) => Err(ConfigError::Io(e)),
    }
}

// Prefer
fn load(path: &Path) -> Result<Config, ConfigError> {
    let text = fs::read_to_string(path)?;   // needs From<io::Error> for ConfigError
    let cfg = toml::from_str(&text)?;       // needs From<toml::de::Error>
    Ok(cfg)
}
```

`?` converts the error with `From` (`thiserror`'s `#[from]` derives it). Add
context without nesting: `.map_err(..)?`, or with `anyhow`
`.with_context(|| format!("load {}", path.display()))?`.

## Guard clauses with `let ... else`

```rust
// Avoid
fn charge(user: Option<&User>) -> Result<Receipt, ChargeError> {
    if let Some(user) = user {
        if user.active {
            if user.quota > 0 {
                bill(user)
            } else {
                Err(ChargeError::Quota(user.id))
            }
        } else {
            Err(ChargeError::Inactive(user.id))
        }
    } else {
        Err(ChargeError::NoUser)
    }
}

// Prefer
fn charge(user: Option<&User>) -> Result<Receipt, ChargeError> {
    let Some(user) = user else {
        return Err(ChargeError::NoUser);
    };
    if !user.active {
        return Err(ChargeError::Inactive(user.id));
    }
    if user.quota == 0 {
        return Err(ChargeError::Quota(user.id));
    }
    bill(user)
}
```

`let ... else` (Rust 1.65+) binds on the happy path; its `else` block must
diverge (`return`, `break`, `continue`, panic). For an `Option` to `Result`
guard, `let user = user.ok_or(ChargeError::NoUser)?;` is shorter still. Use
`return` only for early exits; the final value is the tail expression
(clippy `needless_return`).

## Loops: `continue` as the guard

```rust
for e in &entities {
    if e.kind != Kind::Service {
        continue;
    }
    let Some(owner) = &e.owner else {
        missing.push(e.name.clone());
        continue;
    };
    check_owner(e, owner);
}
```

**Iterator chains** (`filter`, `filter_map`, `any`, `all`, `find`,
`position`) replace a loop plus a flag. Two limits:

- A chain whose closures contain `if let` and `match` is nesting written on
  fewer lines. Name the closure as a function, or use a `for` loop.
- `?` inside a closure returns from the closure, not the function. To stop on
  the first error, `collect::<Result<Vec<_>, _>>()?`; for side effects with
  early exit, a `for` loop reads better.

## `match` instead of nested `if let`

- Match on a tuple to flatten two options at once:
  `match (a, b) { (Some(x), Some(y)) => .., (Some(x), None) => .., _ => .. }`.
- Match guards (`Some(n) if n > limit => ..`) keep a condition at the arm's
  level instead of an `if` inside it.
- Let chains (`if let Some(x) = a && let Some(y) = b { .. }`) are stable from
  Rust 1.88 in edition 2024 only; check the crate's edition first.
- A `match` that maps one value to results is flat in meaning even when it
  indents — the downloader's state dispatch is a `match` calling
  `process_pending(d)` / `process_in_progress(d)`.

## Counting depth in Rust

Count the function body as 1; the surrounding `impl` and `mod` do not count.
With rustfmt's 4-space indent, depth 4 starts at 16 spaces in a free
function and 20 in an `impl` method. Method chains and struct literals also
indent; read the function before reporting it. `scripts/nesting_depth.py`
does not read `.rs` files; use clippy.

## Linters (clippy)

| Lint | Group | What |
|---|---|---|
| `excessive_nesting` | complexity (warn) | blocks nested past `excessive-nesting-threshold` (clippy.toml; default 0 = never fires). Counts `mod`, `impl` and `fn` blocks too: the docs' own example flags an `if` in a method in an `impl` in a `mod` at threshold 3, so start at 5–6 |
| `collapsible_if` / `collapsible_else_if` | style / pedantic | nested `if` that `&&` or `else if` removes |
| `redundant_else` | pedantic | `else` after `return`, `break`, `continue` |
| `needless_continue` | pedantic | `else { continue }` and similar |
| `question_mark` / `manual_let_else` | style / pedantic | manual `match` or `if let` that `?` or `let ... else` replaces |
| `too_many_lines` | pedantic | `too-many-lines-threshold`, default 100 |

Skip `cognitive_complexity` (restriction group): its own docs say it does
not measure what its name claims.
