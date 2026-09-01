# Bot HQ

One page in Hermes Desktop for every bot on your machine. Open it to see who
is working, what runs next, and each bot's own dashboard — without hunting
through chat transcripts.

## Set up

Do these in order. Skip nothing; the page and the dashboard reader are
separate switches, and both start off.

**1. Install the plugin**

```bash
hermes plugins install the-spirit-realm/hermes-bot-hq
```

**2. Turn on the page**

In Hermes Desktop: **Settings → Plugins → Bot HQ**.

**3. Turn on the dashboard reader**

```bash
hermes plugins enable hermes-bot-hq
```

Then fully quit Hermes and open it again. The reader only starts with the
backend, so a reload of the page is not enough.

**4. Open it**

Click **Bot HQ** in the sidebar. (If it is missing, press `Cmd+K`, run
**Reload desktop plugins**, and look again.)

You should see every local bot. If a yellow **Dashboards unavailable** bar
appears at the top, step 3 did not take — enable the plugin and quit/reopen
once more.

## Get a dashboard on a bot

1. Click the bot.
2. If it has no dashboard yet, click **Copy and open chat**.
3. Paste into the chat and send.

The bot writes its own Home. Come back to Bot HQ and refresh if it does not
show up right away.

To refresh that dashboard on a schedule, add the skill to the routine that
already does the work:

```bash
hermes cron edit <job-id> --add-skill hermes-bot-hq:bot-home
```

## Other ways to install

- **From Desktop, no terminal:** paste
  `hermes://plugin/install?repo=the-spirit-realm/hermes-bot-hq`
  into Hermes. That is an install link the app handles, not a website.
- **From a git clone:** put the repo at `~/.hermes/plugins/hermes-bot-hq`,
  then do steps 2–4 above.

## What you get

- A fleet page: every Hermes profile, no signup or register step.
- Per bot: status, next routine, and a dashboard the bot publishes as
  `home/schema.json` + `home/data.json` in its profile.
- Buttons the bot declares (`run_routine`, `open_chat`, `open_path`,
  `open_url`) and an optional one-line composer.
- The widget list is fixed on purpose, so a dashboard cannot rearrange
  itself overnight and no bot-authored HTML or JavaScript ever runs.

The data contract is [`docs/home-contract.md`](docs/home-contract.md).
A complete file pair lives in `examples/`.

## Contribute

Issues and pull requests are welcome. MIT, no CLA.

Clone into `~/.hermes/plugins/hermes-bot-hq`, then do steps 2–4 above so you
are running your checkout. How to map a change to a file, what the contract
forbids, and ideas that would help: [CONTRIBUTING.md](CONTRIBUTING.md).

Helpful starting points: shorter setup, a better place for Bot HQ inside
Hermes, the Hermes web dashboard, or a new closed widget type.

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

The Python half exists because the gateway has no file-read RPC and a disk
plugin may only import `@hermes/plugin-sdk`. `plugin_api.py` reads and
validates Home files. It never writes them.

## Tests

```bash
node --test "tests/*.test.mjs"

PYTHONPATH=~/.hermes/hermes-agent \
  ~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests
```

The Python suite uses stdlib `unittest`, so it runs with the Hermes venv as-is.

## Known limits

- The fleet UI is Desktop-only today. The Home reader is already HTTP, so the
  Hermes web dashboard is the natural next surface — it does not exist yet.
- `~/.hermes/plugins` is scanned locally, so bots on remote gateways get roster
  and status but no dashboard.
- The desktop SDK moves quickly; optional capabilities are feature-detected and
  degrade rather than throw.

## License

MIT — see [LICENSE](LICENSE).
