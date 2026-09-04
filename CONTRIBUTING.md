# Contributing to Bot HQ

Issues and pull requests are welcome. The license is MIT; there is no CLA.

If something in setup or the page confused you, that is a useful PR — this
plugin is meant to be easy to turn on.

## Work from a clone

```bash
git clone https://github.com/the-spirit-realm/hermes-bot-hq.git ~/.hermes/plugins/hermes-bot-hq
```

Then do [README steps 2–4](README.md#set-up): enable **Bot HQ** in Desktop
Plugins, `hermes plugins enable hermes-bot-hq`, fully quit Hermes and reopen.

The desktop page hot-reloads when `desktop/plugin.js` is saved (`Cmd+K` ▸
**Reload desktop plugins** if not). Changes under `dashboard/` need a backend
restart — those routes mount at startup.

## Where to change what

| You are changing | Start here | Tests |
| --- | --- | --- |
| Fleet page, bot detail, empty Home prompt | `desktop/plugin.js` | `tests/*.test.mjs` |
| Home validation, REST, run-routine | `dashboard/plugin_api.py` | `tests/test_home_validation.py` |
| What bots are taught | `skills/bot-home/SKILL.md` | keep [`docs/home-contract.md`](docs/home-contract.md) in sync |
| Example dashboard | `examples/` | — |

The Python half only reads and validates Home files. It never writes them.
Bots publish by writing `home/schema.json` and `home/data.json` in their own
profile.

## Guardrails

These are the design, not leftover constraints:

- The bot owns **data**. This plugin owns **structure**.
- Widget types are a closed set. A new type is a real contribution (schema,
  renderer, skill, contract, tests). Shipping HTML or JavaScript through a
  Home is not.
- Actions are the four named verbs (`run_routine`, `open_chat`, `open_path`,
  `open_url`). Never a command string.

## Tests

From the plugin directory:

```bash
node --test "tests/*.test.mjs"

PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
```

The Python suite is stdlib `unittest`. Run it with the Hermes venv; there is
nothing extra to pip-install.

## Good first work

- **Easier setup.** Two switches, a backend restart, and a yellow banner if
  you miss one — anything that makes the first-run path shorter or obvious.
- **Bot avatars on the fleet page.** Cards currently identify a bot by name
  and color. If Hermes already has an avatar for the profile, show it in Bot
  HQ (fleet card and the bot's own page).
- **A better home in Hermes.** Bot HQ is a sidebar page plus a palette
  command. If it belongs on the main dashboard, in a tab, or somewhere
  people already look, propose it.
- **Hermes web dashboard.** The UI today is Desktop-only. The Home reader is
  already HTTP; extending this to the Hermes web dashboard (not a one-off
  site) is in scope.
- **Another example Home.** `examples/` is one research-desk pair. A second
  complete `schema.json` + `data.json` for a different kind of bot (still
  only the seven widget types) is a good first PR — keep `examples/README.md`
  in sync.
- **A new closed widget type** — if a real bot cannot say what it needs with
  the current seven.

Open an issue if you are unsure whether an idea fits. Better a short
conversation than a PR that has to fight the contract.
