# Buttons

A Hermes bot is purpose-built: a fixed job, so a fixed set of next steps.
Declare a button when the user will do this again. Do not invent a new
widget type. Do not put `prompt` in `data.json`.

`toolbar` (or `actions` — same strip) is the page-level row above the cards.
A `buttons` widget sits in the stack like any other card. Line buttons sit
on a `list` or `alerts` item. If unsure, only do recipe 1.

## 1. Button card in the stack

```json
{
  "version": 1,
  "title": "Research Desk",
  "toolbar": [
    { "id": "digest", "label": "Run digest", "type": "run_routine", "job": "Researcher Digest", "primary": true }
  ],
  "widgets": [
    { "id": "findings", "type": "list", "title": "Findings", "width": "full" },
    {
      "id": "triage",
      "type": "buttons",
      "title": "Triage",
      "width": "full",
      "buttons": [
        { "id": "review", "label": "Review", "type": "send_prompt", "prompt": "Review the findings on this dashboard and update Home when done." },
        { "id": "escalate", "label": "Escalate", "type": "send_prompt", "prompt": "Escalate genuine open issues on this dashboard (email the owning team) and update Home." }
      ]
    }
  ]
}
```

No `data.json` entry for `triage`. Review here means the whole page, not one row.

## 2. Buttons on a list line

The control sits on the line. Schema declares the verbs; each item only names ids.

```json
{
  "id": "findings",
  "type": "list",
  "title": "Issues",
  "width": "full",
  "buttons": [
    { "id": "genuine", "label": "Genuine", "type": "send_prompt", "prompt": "Mark this issue genuine and update Home." },
    { "id": "escalate", "label": "Escalate", "type": "send_prompt", "prompt": "Escalate this issue (email the owning team) and update Home." }
  ]
}
```

```json
{
  "items": [
    { "id": "api-2-disk", "title": "disk full on api-2", "detail": "92% used", "buttons": ["genuine", "escalate"] },
    { "id": "payments-timeout", "title": "timeout on payments", "buttons": ["escalate"] }
  ]
}
```

Give every item with `buttons` an `id` (`[a-z0-9_-]`). Skip the id and that line has no buttons — the Home still publishes. Same pattern on `alerts` (title is `message`).

On a line click, Bot HQ appends `[item id]` and `[item title]` even if the prompt is just `escalate`. You may also use `{{item.id}}` and `{{item.title}}` in the schema prompt.

Full rules: `docs/home-contract.md` in the `hermes-bot-hq` plugin.
