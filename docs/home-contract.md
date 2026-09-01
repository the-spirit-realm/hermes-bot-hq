# The Home contract

A **Home** is a bot's dashboard. The bot owns the data; Bot HQ owns
the structure. That split is the whole design: a bot can refresh its numbers
every morning without permission, but it cannot invent new UI on every load,
so the page stays something you can learn once and trust.

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
  "actions": [
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
| `actions` | Optional, <= 8. Declared operations only (below). |
| `widgets` | <= 24. Order is render order. `id` must be unique, `[a-z0-9_-]`. |

`width` is `full` or `half` (default `half`); `full` spans the page. An optional
`empty` string is shown when `data.json` has nothing for that widget yet.

### Actions

Named operations, never free-form commands:

| `type` | Extra field | Effect |
| --- | --- | --- |
| `run_routine` | `job` | Triggers that cron job for this bot, then refreshes |
| `open_chat` | - | Opens the bot's conversation in Hermes |
| `open_path` | `path` | Reveals a file or folder in Finder / Explorer |
| `open_url` | `url` | Opens `http`/`https` in the default browser |

`job` matches a cron job by id, or by name (with or without Bot Mode's
`[bot:<name>]` prefix). One action may set `primary: true`.

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
| `list` | `items: [{ title, detail?, tone?, url? }]` | 200 items |
| `markdown` | `text: str` | 20,000 chars |
| `timeseries` | `series: [{ label, points: [[x, y]] }]` | 6 series, 500 points |
| `sources` | `items: [{ title, url?, fetched_at? }]` | 100 items |
| `alerts` | `items: [{ level, message, detail? }]` | 50 items |

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
