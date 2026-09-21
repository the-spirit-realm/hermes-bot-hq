# The Home contract

A **Home** is a bot's dashboard. The bot owns the data; Bot HQ owns
the structure. That split is the whole design: a bot can refresh its numbers
every morning without permission, but it cannot invent new UI on every load,
so the page stays something you can learn once and trust.

## Operator buttons

A Hermes bot is purpose-built. It does a small, known job — research,
writing, monitoring, ops — and the user's next steps on that job are also
small and known. Chat is the right interface when the next sentence is
unpredictable. A Home is the opposite: the bot already did the work, the
page already shows it, and the next step is one of a few named moves the
user repeats. Clicking is the product working. Retyping that into the
composer every day is the product failing.

The composer stays for the exception: a novel ask that is not worth a
declared button. A monitoring bot (review / mark genuine / escalate) is one
illustration, not the scope — any specialist dashboard that is an ops
console for a fixed task uses the same pattern.

Label and prompt live in `schema.json`. Daily values live in `data.json`.
A line click concatenates the schema prompt with that item's id and title
so the agent knows which row. Prompts never belong in `data.json`.

## Where it lives

Two files inside the bot's own profile directory:

```text
~/.hermes/profiles/<bot>/home/schema.json    # layout — changes rarely
~/.hermes/profiles/<bot>/home/data.json      # values — rewritten by runs
```

The `default` profile uses `~/.hermes/home/` instead, since that profile *is*
the Hermes home.

No registration call, no database. A bot joins Bot HQ by writing
`schema.json`; a bot without one still appears in the fleet with status,
routines, and a chat link.

Write atomically — write a sibling temp file and `rename()` it over the target.
A half-written `data.json` is a parse error, and the page will say so.

## schema.json

```json
{
  "version": 1,
  "title": "Research Desk",
  "subtitle": "Semis coverage, refreshed each morning",
  "composer": false,
  "toolbar": [
    { "id": "brief", "label": "Run now", "type": "run_routine", "job": "morning-brief", "primary": true },
    { "id": "notes", "label": "Open notes", "type": "open_path", "path": "~/research/notes.md" }
  ],
  "widgets": [
    { "id": "snapshot", "type": "kpi", "title": "Snapshot", "width": "full" },
    { "id": "compare", "type": "table", "title": "NVDA vs AMD" },
    { "id": "risks", "type": "alerts", "title": "Open risks" },
    { "id": "cites", "type": "sources", "title": "Sources" }
  ]
}
```

| Field | Rules |
| --- | --- |
| `version` | Integer. `1` today. An unknown version still renders; the page notes it. |
| `title` | Optional, <= 80 chars. Defaults to the bot's Bot Mode title. |
| `subtitle` | Optional, <= 160 chars. |
| `composer` | Optional bool, default `false`. `true` adds one input on the page. |
| `toolbar` | Optional, <= 8. Page-level buttons, always above the widget stack. |
| `actions` | Alias for `toolbar`. Existing Homes keep working; no migration. |
| `widgets` | <= 24. Order is render order. `id` must be unique, `[a-z0-9_-]`. |

`width` is `full` or `half` (default `half`); `full` spans the page. An optional
`empty` string is shown when `data.json` has nothing for that widget yet.

### Buttons

The same button object is used on the toolbar, on a `buttons` widget, and
on `list` / `alerts` lines. Named operations, never a shell command:

| `type` | Extra field | Effect |
| --- | --- | --- |
| `run_routine` | `job` | Triggers that cron job for this bot, then refreshes |
| `open_chat` | - | Opens the bot's conversation in Hermes |
| `open_path` | `path` | Reveals a file or folder in Finder / Explorer |
| `open_url` | `url` | Opens `http`/`https` in the default browser |
| `send_prompt` | `prompt` | Sends that text to the bot's Bot Chat, then refreshes |

`prompt` is required, stripped, max 4000 characters. `job` matches a cron
job by id, or by name (with or without Bot Mode's `[bot:<name>]` prefix).
One button may set `primary: true`.

If both `toolbar` and `actions` are present and disagree, `actions` wins so
an upgraded Home never loses its existing strip.

A `buttons` widget places the same controls in the card stack (no
`data.json` payload). `list` and `alerts` widgets may declare `buttons` in
schema; each item in `data.json` lists ids only:

```json
{ "id": "api-2-disk", "title": "disk full on api-2", "buttons": ["genuine", "escalate"] }
```

Item `id` must be `[a-z0-9_-]` and unique in that widget when `buttons` is
set. Missing id means no line buttons (a warning, not an unreadable Home).
Unknown ids are dropped. At most 3 buttons per line. On a line click, Bot
HQ appends `[item id]` and `[item title]` (alerts use `message` as the
title). Optional `{{item.id}}` / `{{item.title}}` in the schema prompt are
substituted first. `table`, `kpi`, `markdown`, `timeseries`, and `sources`
do not get line buttons.

## data.json

```json
{
  "updated_at": "2026-08-29T06:15:00Z",
  "stale_after_minutes": 1440,
  "note": "AMD Q2 filing not out yet",
  "widgets": {
    "snapshot": {
      "items": [
        { "label": "NVDA rev growth", "value": "+56%", "delta": "+4pp", "tone": "good" },
        { "label": "AMD rev growth", "value": "+9%", "tone": "neutral" }
      ]
    },
    "compare": {
      "columns": ["Metric", "NVDA", "AMD"],
      "rows": [["Gross margin", "75%", "49%"], ["Fwd P/E", "31", "27"]]
    },
    "risks": {
      "items": [{ "level": "warn", "message": "Reporting periods are not aligned" }]
    },
    "cites": {
      "items": [{ "title": "NVDA 10-Q", "url": "https://example.com/10q", "fetched_at": "2026-08-29T06:02:00Z" }]
    }
  }
}
```

`updated_at` is an ISO-8601 timestamp; it drives the "updated 20m ago" line.
`stale_after_minutes` (default 1440) decides when a Home is flagged **Stale**,
which is how a dead routine becomes visible instead of a dashboard quietly
showing last week's numbers as if they were current.

## Widget payloads

Types are a closed set. An unknown type renders as a skipped chip rather than
executing anything — a bot cannot ship HTML or JavaScript through this file.

| `type` | Payload | Caps |
| --- | --- | --- |
| `kpi` | `items: [{ label, value, delta?, tone? }]` | 12 items |
| `table` | `columns: [str]`, `rows: [[cell]]` | 12 columns, 200 rows |
| `list` | `items: [{ id?, title, detail?, tone?, url?, buttons? }]` | 200 items |
| `markdown` | `text: str` | 20,000 chars |
| `timeseries` | `series: [{ label, points: [[x, y]] }]` | 6 series, 500 points |
| `sources` | `items: [{ title, url?, fetched_at? }]` | 100 items |
| `alerts` | `items: [{ id?, level, message, detail?, buttons? }]` | 50 items |
| `buttons` | none (schema `buttons` only) | 8 buttons |

`tone` is `good`, `warn`, `bad`, or `neutral`. `level` is `info`, `warn`, or
`error`. `markdown` renders as paragraphs and bullet lines only — no HTML.
`points` take a number or an ISO-8601 string for `x` and a number for `y`.

Either file may be up to 512 KiB. Over that, the page reports the file as
unreadable instead of loading it: a dashboard is a summary, and a bot that
wants to hand over a dataset should link to it with `open_path`.

## What the page does with a broken Home

Nothing silently. A parse error, a bad type, or a missing widget payload
surfaces as a warning on the bot's page and as **Home unreadable** on its
fleet card, so the failure is visible where the data would have been.
