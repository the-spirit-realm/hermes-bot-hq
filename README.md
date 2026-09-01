# Bot HQ

A Hermes Desktop page that lists every bot on your machine and, for each one,
the dashboard that bot maintains for itself.

Bots are useful because they run without you. That is also the problem: the only
way to find out what yours have been doing is to open Hermes, pick a bot, and
read a chat transcript. This adds the missing surface — one page, every bot,
status and routines at a glance, and a real dashboard behind each name.

The bot owns the data. The plugin owns the structure. A bot refreshes its numbers
whenever it likes, but the widget vocabulary is fixed and small, so the page
cannot rearrange itself every morning and no agent-authored HTML or JavaScript
ever executes.

## What you get

- **Fleet page** at `/control-center` and in the command palette. Every bot
  appears automatically — a bot is a Hermes profile, so there is nothing to
  register.
- Per card: name and role from Bot Mode, live status (working, active, routine
  failed, stale, idle), whether a dashboard is published and how fresh it is,
  and the next routine that will fire.
- **Per-bot dashboard** built from two JSON files the bot writes into its own
  profile: `home/schema.json` (layout) and `home/data.json` (values).
- **Declared actions** — `run_routine`, `open_chat`, `open_path`, `open_url`.
  Never a command string.
- **Optional composer**, only for bots that ask for one: a single input that
  sends a prompt and refreshes the dashboard instead of opening a transcript.
- Bots without a dashboard still work here: status, routines, and a chat link.

## Install

```bash
hermes plugins install the-spirit-realm/hermes-bot-hq
```

That accepts a Git URL, `owner/repo`, or a community-index name.

From Hermes Desktop, the same Git remote is:

```text
hermes://plugin/install?repo=the-spirit-realm/hermes-bot-hq
```

Or clone by hand:

```bash
git clone <repo> ~/.hermes/plugins/hermes-bot-hq
```

Then flip both switches — they are independent and both default off:

1. **The UI.** Hermes Desktop ▸ Settings ▸ Plugins ▸ enable *Bot HQ*.
   It hot-reloads on save; `Cmd+K ▸ Reload desktop plugins` if not.
2. **The Home reader.** `hermes plugins enable hermes-bot-hq`, then
   **restart the Hermes backend** — plugin routes mount at startup. A
   "Dashboards unavailable" banner on the fleet page means this step is
   pending; everything else still works.

## Teaching a bot to publish

The package ships a `bot-home` skill, registered under the qualified name
`hermes-bot-hq:bot-home` (Hermes namespaces every plugin skill). Ask a bot
to build its dashboard and it will find the contract; to make it automatic,
attach the skill to a routine and tell that routine to rewrite `data.json` at
the end of each run:

```bash
hermes cron edit <job-id> --add-skill hermes-bot-hq:bot-home
```

Or hand-write the two files yourself to see the shape — `examples/` has a
complete pair. The full reference is [`docs/home-contract.md`](docs/home-contract.md).

## Layout

```text
hermes-bot-hq/
├── plugin.yaml            # agent half — ships the skill
├── __init__.py            # register(ctx): registers skills/
├── skills/bot-home/       # how a bot publishes its dashboard
├── dashboard/
│   ├── manifest.json      # tab hidden: this plugin's UI is the desktop half
│   └── plugin_api.py      # reads + validates Home JSON, triggers routines
├── desktop/plugin.js      # the Bot HQ page (plain ESM, no build step)
├── docs/home-contract.md  # the data contract
├── examples/              # a complete schema.json + data.json pair
└── tests/                 # node:test for the UI, unittest for the reader
```

Why a Python half at all, when bots write plain files: the gateway exposes no
file-read RPC and a disk plugin may only import `@hermes/plugin-sdk`, so
something server-side has to hand those files to the UI. `plugin_api.py` is a
reader and a validator — it never writes a Home.

## Tests

```bash
node --test "tests/*.test.mjs"

PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
```

The Python suite uses stdlib `unittest`, so it runs with the Hermes venv as-is.

## Known limits

- Desktop only. The contract lives in files behind a REST endpoint, so a browser
  surface stays possible later, but it does not exist today.
- `~/.hermes/plugins` is scanned locally, so bots on remote gateways get roster
  and status but no dashboard.
- The desktop SDK moves quickly; optional capabilities are feature-detected and
  degrade rather than throw.

## License

MIT — see [LICENSE](LICENSE).
