# agent-vs-graph — AI assistant context

An open benchmark: the same tasks run as a workflow graph and as agent loops, every model request
metered at the wire, priced afterwards from sourced price sheets. The design and the reasons
behind each decision are in [docs/design.md](docs/design.md); read it before changing what is
measured.

## Rules that matter

- **The meter is the only source of token counts.** Never read usage from a framework's own
  accounting; every arm goes through `/t/<run>/<arm>/<task>/<item>/...`.
- **The ledger stores tokens, never money.** Costs come from `prices/*.yaml` at report time.
- **Every price names its source URL and checked date.** A number not confirmed on the vendor's
  own page carries `verify:` and the report prints it as unverified.
- **Fair to agents.** Harnesses run at their defaults, pinned by version; prompts and tools are
  shared by every arm; results report cost per successful item beside raw cost. Don't tune the
  graph and leave the agents untuned.
- **Inputs are public datasets with checked licenses.**
- **Nothing about the machine a run happened on is committed.** GPU, paths and binaries go in the
  gitignored `local.toml`.
- Tests need no network, GPU or API key (`task test`). Async tests use pytest-aiohttp with
  `asyncio_mode = auto`.

## Commands

`task setup`, `task test`, `task lint`, `task fmt`, `task check`, `task meter`, `task stub`,
`task report`, `task serial`, `task publish`.

`runs/` is scratch and gitignored; `results/` is the committed record of published runs, written
only by `avg publish` (never edit a report by hand).
