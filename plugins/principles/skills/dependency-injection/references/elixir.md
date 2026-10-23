# Dependency injection in Elixir

Modules are values. Passing a module (or a function) as an argument is the
injection mechanism; a behaviour is the contract. For Mox and `Req.Test`
setup details and async test pitfalls, see their HexDocs (`Mox` and
`Req.Test` module docs).

## Behaviour + adapter

```elixir
defmodule Attachments.Storage do
  @callback upload(name :: String.t(), data :: iodata(), opts :: keyword()) ::
              :ok | {:error, term()}
end

defmodule Attachments.Storage.S3 do
  @behaviour Attachments.Storage
  @impl true
  def upload(name, data, opts), do: ...
end
```

## Three ways to choose the adapter, in order of preference

1. **Explicit argument or option** — visible, async-test safe, no globals.

   ```elixir
   def handle(upload, opts \\ []) do
     storage = Keyword.get(opts, :storage, Attachments.Storage.S3)
     storage.upload(upload.name, upload.data, opts)
   end
   ```

2. **Struct/state field set at start** — for long-lived processes, pass the
   adapter in `start_link` opts and keep it in GenServer state.

3. **Application env, read at runtime** — common in applications
   (`Application.fetch_env!(:my_app, :storage)`), configured per environment
   in `config/test.exs` to the Mox mock. Acceptable at the application
   boundary; avoid in libraries (the Elixir library guidelines say to avoid
   Application env for library configuration). Use `fetch_env!` so a missing
   key crashes with the key name instead of returning `nil`.

Avoid `Application.compile_env/3` for adapter choice unless the value truly
cannot change between environments: it bakes the module in at compile time
and `Application.put_env` in a test will not change it.

## Factory by data

```elixir
def storage_for(%{kind: "s3"}), do: {:ok, Attachments.Storage.S3}
def storage_for(%{kind: "sftp"}), do: {:ok, Attachments.Storage.SFTP}
def storage_for(%{kind: "webdav"}), do: {:ok, Attachments.Storage.WebDAV}
def storage_for(%{kind: kind}),
  do: {:error, "storage kind #{inspect(kind)}: want \"s3\", \"sftp\" or \"webdav\""}
```

Multi-clause functions are the idiomatic factory: one clause per
implementation, a final clause that names the bad value.

## Test doubles

| Dependency | Double |
|---|---|
| Behaviour | `Mox.defmock(StorageMock, for: Attachments.Storage)`; `expect/3` or `stub/3`; `async: true` works because expectations are per-process (use `allow/3` for spawned processes) |
| HTTP via `Req` | `Req.Test.stub/2` with `plug: {Req.Test, MyStub}` passed as an option |
| HTTP, any client | `Bypass` — a real local server |
| Time | pass `now` or a `DateTime`; avoid `:meck` on `DateTime` |
| A fake | a plain module implementing the behaviour, e.g. an Agent-backed in-memory store |

## Smells

- `Application.put_env` in a test → forces `async: false` and leaks between
  tests; pass an option instead.
- `:meck`/`Mimic` patching a module in tests → hardwired call; inject it.
- `HTTPoison.get/1` or `Req.get!/1` called deep in a context module → the
  HTTP client is hardwired; route it through an adapter or `Req` options.
- A behaviour with one implementation and no mock → call the module directly.
