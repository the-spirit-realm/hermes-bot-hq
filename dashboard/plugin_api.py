"""Bot HQ — backend routes.

Mounted at ``/api/plugins/hermes-bot-hq/`` by the dashboard plugin system
and reached from the desktop half through ``ctx.rest``.

Why this layer exists at all: a bot publishes its dashboard as plain JSON in
its own profile directory, which is the right storage (no new database, visible
from a shell, editable by hand). But a desktop plugin may only import the
plugin SDK and the gateway exposes no file-read RPC, so something server-side
has to hand those files to the UI. That is all this module is — a reader and a
validator. It never writes a Home; bots own their own files.

Validation is not decoration. ``data.json`` is model-authored, so every payload
is treated as untrusted: unknown widget types are reported rather than
rendered, collections are capped, and a file over the size limit is refused
outright instead of being streamed into the renderer.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()

# ── Contract limits (documented in docs/home-contract.md) ──────────────────

MAX_FILE_BYTES = 512 * 1024
MAX_WIDGETS = 24
MAX_ACTIONS = 8
DEFAULT_STALE_AFTER_MINUTES = 24 * 60

WIDGET_TYPES = frozenset({"kpi", "table", "list", "markdown", "timeseries", "sources", "alerts", "buttons"})
WIDGETS_WITH_BUTTONS = frozenset({"buttons", "list", "alerts"})
ACTION_TYPES = frozenset({"run_routine", "open_chat", "open_path", "open_url", "send_prompt"})
TONES = frozenset({"good", "warn", "bad", "neutral"})
ALERT_LEVELS = frozenset({"info", "warn", "error"})
ITEM_ID_RE = re.compile(r"^[a-z0-9_-]+$")

CAPS = {
    "kpi_items": 12,
    "table_columns": 12,
    "table_rows": 200,
    "list_items": 200,
    "markdown_chars": 20_000,
    "series": 6,
    "points": 500,
    "sources": 100,
    "alerts": 50,
    "prompt_chars": 4_000,
    "line_buttons": 3,
}


# ── Paths ──────────────────────────────────────────────────────────────────


def _bot_home_dir(bot: str) -> Path:
    """Resolve ``<profile home>/home`` for *bot*.

    Delegates to ``hermes_cli.profiles`` so the name rules (normalization, the
    ``default`` special case, a custom ``HERMES_HOME``) stay identical to every
    other surface instead of being re-derived here.
    """
    from hermes_cli.profiles import get_profile_dir, normalize_profile_name

    canon = normalize_profile_name(bot)
    profile_dir = get_profile_dir(canon)

    if not profile_dir or not profile_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"bot '{bot}' not found")

    return profile_dir / "home"


def _known_bots() -> List[str]:
    from hermes_cli.profiles import list_profiles

    return [info.name for info in list_profiles()]


# ── Reading ────────────────────────────────────────────────────────────────


def _read_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    """Read one Home file. Returns ``(payload, error)`` — never raises.

    A missing file is not an error (a bot simply has not published), but a file
    that exists and cannot be used is: the caller surfaces the reason so a
    broken Home is visible instead of looking like an empty one.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"cannot stat {path.name}: {exc}"

    if stat.st_size > MAX_FILE_BYTES:
        return None, f"{path.name} is {stat.st_size} bytes (limit {MAX_FILE_BYTES})"

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read {path.name}: {exc}"

    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        # Most likely a torn write; the skill tells bots to rename() instead.
        return None, f"{path.name} is not valid JSON (line {exc.lineno}): {exc.msg}"


def _mtime_iso(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


# ── Validation ─────────────────────────────────────────────────────────────


def _clip(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text[:limit]


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None

    text = str(value).strip().replace("Z", "+00:00")

    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None

    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _parse_buttons(raw: Any, warnings: List[str], where: str) -> List[Dict[str, Any]]:
    """Normalize one list of declared buttons. Unknown types are dropped."""
    if raw is None:
        return []

    if not isinstance(raw, list):
        warnings.append(f"{where} must be a list")
        return []

    if len(raw) > MAX_ACTIONS:
        warnings.append(f"{where} has {len(raw)} entries; only the first {MAX_ACTIONS} are shown")
        raw = raw[:MAX_ACTIONS]

    buttons: List[Dict[str, Any]] = []

    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            warnings.append(f"{where} #{index + 1} is not an object")
            continue

        action_type = str(entry.get("type") or "").strip()

        if action_type not in ACTION_TYPES:
            shown = action_type or "(missing)"
            warnings.append(f"action #{index + 1} has unsupported type '{shown}'")
            continue

        action = {
            "id": str(entry.get("id") or f"action-{index + 1}").strip(),
            "label": _clip(entry.get("label"), 40) or action_type.replace("_", " "),
            "type": action_type,
            "primary": bool(entry.get("primary")),
        }

        # Each type carries exactly one target, and it is validated here so the
        # renderer never has to guess what a button means.
        if action_type == "run_routine":
            job = str(entry.get("job") or "").strip()

            if not job:
                warnings.append(f"action '{action['id']}' is run_routine without a job")
                continue

            action["job"] = job
        elif action_type == "open_path":
            path = str(entry.get("path") or "").strip()

            if not path:
                warnings.append(f"action '{action['id']}' is open_path without a path")
                continue

            action["path"] = os.path.expanduser(path)
        elif action_type == "open_url":
            url = str(entry.get("url") or "").strip()

            if not url.startswith(("http://", "https://")):
                warnings.append(f"action '{action['id']}' must be an http(s) url")
                continue

            action["url"] = url
        elif action_type == "send_prompt":
            prompt = str(entry.get("prompt") or "").strip()

            if not prompt:
                warnings.append(f"action '{action['id']}' is send_prompt without a prompt")
                continue

            if len(prompt) > CAPS["prompt_chars"]:
                warnings.append(
                    f"action '{action['id']}' prompt is {len(prompt)} chars; truncated to {CAPS['prompt_chars']}"
                )

            action["prompt"] = prompt[: CAPS["prompt_chars"]]

        buttons.append(action)

    return buttons


def _toolbar_source(raw: Dict[str, Any], warnings: List[str]) -> Tuple[List[Any], str]:
    """Pick the page strip. ``actions`` wins when both lists have entries."""
    raw_actions = raw.get("actions")
    raw_toolbar = raw.get("toolbar")

    if raw_actions is not None and not isinstance(raw_actions, list):
        warnings.append("schema.actions must be a list")
        raw_actions = None

    if raw_toolbar is not None and not isinstance(raw_toolbar, list):
        warnings.append("schema.toolbar must be a list")
        raw_toolbar = None

    if raw_actions:
        return raw_actions, "schema.actions"

    if raw_toolbar is not None:
        return raw_toolbar, "schema.toolbar"

    return raw_actions or [], "schema.actions"


def validate_schema(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize ``schema.json`` into exactly what the renderer expects.

    Unknown widget types survive as ``supported: False`` entries rather than
    being dropped: the page shows a skipped chip in place, which tells the
    reader something is there and unrenderable instead of silently omitting it.
    """
    warnings: List[str] = []

    if not isinstance(raw, dict):
        return {}, ["schema.json must be a JSON object"]

    version = raw.get("version")

    if not isinstance(version, int):
        warnings.append("schema.version missing or not an integer; assuming 1")
        version = 1
    elif version != 1:
        warnings.append(f"schema.version {version} is newer than this plugin understands")

    widgets: List[Dict[str, Any]] = []
    seen_ids: set = set()
    raw_widgets = raw.get("widgets")

    if raw_widgets is None:
        raw_widgets = []
    elif not isinstance(raw_widgets, list):
        warnings.append("schema.widgets must be a list")
        raw_widgets = []

    if len(raw_widgets) > MAX_WIDGETS:
        warnings.append(f"schema.widgets has {len(raw_widgets)} entries; only the first {MAX_WIDGETS} are shown")
        raw_widgets = raw_widgets[:MAX_WIDGETS]

    for index, entry in enumerate(raw_widgets):
        if not isinstance(entry, dict):
            warnings.append(f"widget #{index + 1} is not an object")
            continue

        widget_id = str(entry.get("id") or "").strip()

        if not widget_id:
            warnings.append(f"widget #{index + 1} has no id")
            continue

        if widget_id in seen_ids:
            warnings.append(f"widget id '{widget_id}' is duplicated; keeping the first")
            continue

        seen_ids.add(widget_id)
        widget_type = str(entry.get("type") or "").strip()
        supported = widget_type in WIDGET_TYPES

        if not supported:
            shown = widget_type or "(missing)"
            warnings.append(f"widget '{widget_id}' has unsupported type '{shown}'")

        widget = {
            "id": widget_id,
            "type": widget_type,
            "supported": supported,
            "title": _clip(entry.get("title"), 80),
            "width": "full" if str(entry.get("width") or "").strip() == "full" else "half",
            "empty": _clip(entry.get("empty"), 160),
        }

        if widget_type in WIDGETS_WITH_BUTTONS:
            widget["buttons"] = _parse_buttons(entry.get("buttons"), warnings, f"widget '{widget_id}' buttons")
        elif entry.get("buttons") is not None:
            warnings.append(f"widget '{widget_id}' cannot declare buttons")

        widgets.append(widget)

    strip, strip_name = _toolbar_source(raw, warnings)
    actions = _parse_buttons(strip, warnings, strip_name)

    return (
        {
            "version": version,
            "title": _clip(raw.get("title"), 80),
            "subtitle": _clip(raw.get("subtitle"), 160),
            "composer": bool(raw.get("composer")),
            "actions": actions,
            "toolbar": actions,
            "widgets": widgets,
        },
        warnings,
    )


def _validate_kpi(payload: Dict[str, Any], warn) -> Dict[str, Any]:
    items = payload.get("items")
    items = items if isinstance(items, list) else []

    if len(items) > CAPS["kpi_items"]:
        warn(f"kpi has {len(items)} items; showing {CAPS['kpi_items']}")

    out = []

    for entry in items[: CAPS["kpi_items"]]:
        if not isinstance(entry, dict):
            continue

        tone = str(entry.get("tone") or "neutral")
        out.append(
            {
                "label": _clip(entry.get("label"), 60),
                "value": _clip(entry.get("value"), 40),
                "delta": _clip(entry.get("delta"), 24),
                "tone": tone if tone in TONES else "neutral",
            }
        )

    return {"items": out}


def _validate_table(payload: Dict[str, Any], warn) -> Dict[str, Any]:
    columns = payload.get("columns")
    columns = [_clip(c, 40) for c in columns[: CAPS["table_columns"]]] if isinstance(columns, list) else []
    rows_raw = payload.get("rows")
    rows_raw = rows_raw if isinstance(rows_raw, list) else []

    if len(rows_raw) > CAPS["table_rows"]:
        warn(f"table has {len(rows_raw)} rows; showing {CAPS['table_rows']}")

    width = len(columns) or CAPS["table_columns"]
    rows = []

    for row in rows_raw[: CAPS["table_rows"]]:
        if not isinstance(row, list):
            continue

        rows.append([_clip(cell, 200) for cell in row[:width]])

    return {"columns": columns, "rows": rows}


def _item_button_ids(entry: Dict[str, Any], allowed: List[Dict[str, Any]], warn, seen_ids: set) -> Tuple[str, List[str]]:
    """Keep line-button refs that the widget declared. No prompt text from data."""
    raw_id = str(entry.get("id") or "").strip()
    raw_buttons = entry.get("buttons")

    if raw_buttons is None:
        return (raw_id if raw_id and ITEM_ID_RE.match(raw_id) else ""), []

    if not isinstance(raw_buttons, list):
        warn("item buttons must be a list of ids")
        return "", []

    if not raw_id or not ITEM_ID_RE.match(raw_id):
        warn("item buttons need an id matching [a-z0-9_-]")
        return "", []

    if raw_id in seen_ids:
        warn(f"item id '{raw_id}' is duplicated; line buttons dropped on the duplicate")
        return "", []

    seen_ids.add(raw_id)
    allowed_ids = {button["id"] for button in allowed}
    picked: List[str] = []

    for ref in raw_buttons[: CAPS["line_buttons"]]:
        button_id = str(ref or "").strip()

        if button_id in allowed_ids and button_id not in picked:
            picked.append(button_id)
        elif button_id:
            warn(f"item '{raw_id}' names unknown button '{button_id}'")

    if len(raw_buttons) > CAPS["line_buttons"]:
        warn(f"item '{raw_id}' has {len(raw_buttons)} buttons; showing {CAPS['line_buttons']}")

    return raw_id, picked


def _validate_list(payload: Dict[str, Any], warn, allowed_buttons: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    items = payload.get("items")
    items = items if isinstance(items, list) else []

    if len(items) > CAPS["list_items"]:
        warn(f"list has {len(items)} items; showing {CAPS['list_items']}")

    out = []
    seen_ids: set = set()
    allowed_buttons = allowed_buttons or []

    for entry in items[: CAPS["list_items"]]:
        if not isinstance(entry, dict):
            continue

        tone = str(entry.get("tone") or "neutral")
        url = str(entry.get("url") or "").strip()
        item_id, buttons = _item_button_ids(entry, allowed_buttons, warn, seen_ids)
        item = {
            "title": _clip(entry.get("title"), 160),
            "detail": _clip(entry.get("detail"), 400),
            "tone": tone if tone in TONES else "neutral",
            "url": url if url.startswith(("http://", "https://")) else "",
        }

        if item_id:
            item["id"] = item_id

        if buttons:
            item["buttons"] = buttons

        out.append(item)

    return {"items": out}


def _validate_markdown(payload: Dict[str, Any], warn) -> Dict[str, Any]:
    text = payload.get("text")

    if text is None:
        text = payload.get("markdown")

    text = "" if text is None else str(text)

    if len(text) > CAPS["markdown_chars"]:
        warn(f"markdown is {len(text)} chars; truncated to {CAPS['markdown_chars']}")

    return {"text": text[: CAPS["markdown_chars"]]}


def _validate_timeseries(payload: Dict[str, Any], warn) -> Dict[str, Any]:
    series_raw = payload.get("series")
    series_raw = series_raw if isinstance(series_raw, list) else []

    if len(series_raw) > CAPS["series"]:
        warn(f"timeseries has {len(series_raw)} series; showing {CAPS['series']}")

    series = []

    for entry in series_raw[: CAPS["series"]]:
        if not isinstance(entry, dict):
            continue

        points_raw = entry.get("points")
        points_raw = points_raw if isinstance(points_raw, list) else []

        if len(points_raw) > CAPS["points"]:
            warn(f"series '{entry.get('label', '')}' has {len(points_raw)} points; showing {CAPS['points']}")

        points = []

        for point in points_raw[: CAPS["points"]]:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue

            y = point[1]

            if not isinstance(y, (int, float)) or isinstance(y, bool):
                continue

            x = point[0]
            # x may be a number or an ISO timestamp; the renderer only needs
            # ordering, so a timestamp is converted to epoch seconds here.
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                x_value = float(x)
            else:
                stamp = _parse_ts(x)

                if stamp is None:
                    continue

                x_value = stamp.timestamp()

            points.append([x_value, float(y)])

        series.append({"label": _clip(entry.get("label"), 40), "points": points})

    return {"series": series}


def _validate_sources(payload: Dict[str, Any], warn) -> Dict[str, Any]:
    items = payload.get("items")
    items = items if isinstance(items, list) else []

    if len(items) > CAPS["sources"]:
        warn(f"sources has {len(items)} items; showing {CAPS['sources']}")

    out = []

    for entry in items[: CAPS["sources"]]:
        if not isinstance(entry, dict):
            continue

        url = str(entry.get("url") or "").strip()
        out.append(
            {
                "title": _clip(entry.get("title"), 160) or url,
                "url": url if url.startswith(("http://", "https://")) else "",
                "fetched_at": _clip(entry.get("fetched_at"), 40),
            }
        )

    return {"items": out}


def _validate_alerts(payload: Dict[str, Any], warn, allowed_buttons: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    items = payload.get("items")
    items = items if isinstance(items, list) else []

    if len(items) > CAPS["alerts"]:
        warn(f"alerts has {len(items)} items; showing {CAPS['alerts']}")

    out = []
    seen_ids: set = set()
    allowed_buttons = allowed_buttons or []

    for entry in items[: CAPS["alerts"]]:
        if not isinstance(entry, dict):
            continue

        level = str(entry.get("level") or "info")
        item_id, buttons = _item_button_ids(entry, allowed_buttons, warn, seen_ids)
        item = {
            "level": level if level in ALERT_LEVELS else "info",
            "message": _clip(entry.get("message"), 300),
            "detail": _clip(entry.get("detail"), 600),
        }

        if item_id:
            item["id"] = item_id

        if buttons:
            item["buttons"] = buttons

        out.append(item)

    return {"items": out}


def _validate_buttons(_payload: Dict[str, Any], _warn) -> Dict[str, Any]:
    return {}


_VALIDATORS = {
    "kpi": _validate_kpi,
    "table": _validate_table,
    "list": _validate_list,
    "markdown": _validate_markdown,
    "timeseries": _validate_timeseries,
    "sources": _validate_sources,
    "alerts": _validate_alerts,
    "buttons": _validate_buttons,
}


def validate_data(raw: Any, schema: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize ``data.json`` against an already-validated schema.

    Only widgets the schema declares are carried through, and each payload is
    shaped by its type's validator. Data for an undeclared widget is reported
    rather than rendered — otherwise a bot could grow its own dashboard by
    writing a data key, which is exactly the drift this contract prevents.
    """
    warnings: List[str] = []

    if not isinstance(raw, dict):
        return {"widgets": {}, "updated_at": None, "note": "", "stale": False}, ["data.json must be a JSON object"]

    widgets_raw = raw.get("widgets")
    widgets_raw = widgets_raw if isinstance(widgets_raw, dict) else {}
    declared = {widget["id"]: widget for widget in schema.get("widgets", [])}

    for key in widgets_raw:
        if key not in declared:
            warnings.append(f"data has widget '{key}' which schema.json does not declare")

    widgets: Dict[str, Any] = {}

    for widget_id, widget in declared.items():
        if not widget["supported"]:
            continue

        if widget["type"] == "buttons":
            continue

        payload = widgets_raw.get(widget_id)

        if payload is None:
            continue

        if not isinstance(payload, dict):
            warnings.append(f"data for widget '{widget_id}' is not an object")
            continue

        def warn(message: str, _id: str = widget_id) -> None:
            warnings.append(f"widget '{_id}': {message}")

        if widget["type"] in ("list", "alerts"):
            widgets[widget_id] = _VALIDATORS[widget["type"]](payload, warn, widget.get("buttons") or [])
        else:
            widgets[widget_id] = _VALIDATORS[widget["type"]](payload, warn)

    updated = _parse_ts(raw.get("updated_at"))
    stale_after = raw.get("stale_after_minutes")

    if not isinstance(stale_after, (int, float)) or isinstance(stale_after, bool) or stale_after <= 0:
        stale_after = DEFAULT_STALE_AFTER_MINUTES

    stale = False

    if updated is not None:
        age_minutes = (datetime.now(timezone.utc) - updated).total_seconds() / 60
        stale = age_minutes > float(stale_after)

    return (
        {
            "widgets": widgets,
            "updated_at": updated.isoformat() if updated else None,
            "note": _clip(raw.get("note"), 300),
            "stale": stale,
            "stale_after_minutes": int(stale_after),
        },
        warnings,
    )


# ── Home assembly ──────────────────────────────────────────────────────────


def read_home(bot: str) -> Dict[str, Any]:
    """Everything the page needs for one bot's dashboard."""
    home_dir = _bot_home_dir(bot)
    schema_path = home_dir / "schema.json"
    data_path = home_dir / "data.json"

    raw_schema, schema_error = _read_json(schema_path)
    raw_data, data_error = _read_json(data_path)

    errors = [message for message in (schema_error, data_error) if message]

    if raw_schema is None:
        return {
            "bot": bot,
            "has_home": False,
            "error": "; ".join(errors) or None,
            "schema": None,
            "data": None,
            "warnings": [],
            "dir": str(home_dir),
        }

    schema, warnings = validate_schema(raw_schema)
    data, data_warnings = validate_data(raw_data if raw_data is not None else {}, schema)

    return {
        "bot": bot,
        "has_home": True,
        "error": "; ".join(errors) or None,
        "schema": schema,
        "data": data,
        "warnings": warnings + data_warnings,
        # Falling back to the file's mtime means a bot that forgets updated_at
        # still gets an honest "last changed" line instead of a blank one.
        "updated_at": data["updated_at"] or _mtime_iso(data_path) or _mtime_iso(schema_path),
        "dir": str(home_dir),
    }


def _home_summary(bot: str) -> Dict[str, Any]:
    """The fleet-card view of a Home — no widget payloads."""
    try:
        home = read_home(bot)
    except HTTPException:
        raise
    except Exception as exc:  # a bad file must never take out the whole fleet
        log.warning("hermes-bot-hq: summary failed for %s: %s", bot, exc)
        return {"bot": bot, "has_home": False, "error": str(exc)}

    return {
        "bot": bot,
        "has_home": home["has_home"],
        "error": home["error"],
        "updated_at": home.get("updated_at"),
        "stale": bool(home.get("data", {}).get("stale")) if home["has_home"] else False,
        "title": home["schema"]["title"] if home["has_home"] else "",
        "widget_count": len(home["schema"]["widgets"]) if home["has_home"] else 0,
        "composer": bool(home["schema"]["composer"]) if home["has_home"] else False,
        "action_count": len(home["schema"]["actions"]) if home["has_home"] else 0,
        "warning_count": len(home["warnings"]),
    }


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "plugin": "hermes-bot-hq", "widget_types": sorted(WIDGET_TYPES)}


@router.get("/fleet")
async def fleet() -> Dict[str, Any]:
    """One Home summary per bot on this machine."""
    bots = []

    for bot in _known_bots():
        try:
            bots.append(_home_summary(bot))
        except HTTPException:
            continue

    return {"bots": bots}


@router.get("/home/{bot}")
async def home(bot: str) -> Dict[str, Any]:
    return read_home(bot)


class RunRoutineBody(BaseModel):
    job: str


@router.post("/home/{bot}/run-routine")
async def run_routine(bot: str, body: RunRoutineBody) -> Dict[str, Any]:
    """Trigger one of this bot's cron jobs.

    The gateway's ``cron.manage`` RPC deliberately exposes only
    list/add/remove/pause/resume, so a manual run cannot go through it. This
    calls the same ``cronjob`` tool the ``hermes cron run`` CLI uses, with
    ``HERMES_HOME`` scoped to the bot's profile the way the gateway scopes its
    own cron calls — one code path, no second scheduler.
    """
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    home_dir = _bot_home_dir(bot)
    profile_dir = home_dir.parent
    job_ref = body.job.strip()

    if not job_ref:
        raise HTTPException(status_code=400, detail="job is required")

    token = set_hermes_home_override(str(profile_dir))

    try:
        from tools.cronjob_tools import cronjob

        listing = json.loads(cronjob(action="list", include_disabled=True))
        job_id = _resolve_job_id(job_ref, listing.get("jobs") or [], bot)

        if not job_id:
            raise HTTPException(status_code=404, detail=f"no routine matching '{job_ref}' for {bot}")

        result = json.loads(cronjob(action="run", job_id=job_id))
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("hermes-bot-hq: run-routine failed for %s/%s: %s", bot, job_ref, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        reset_hermes_home_override(token)

    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error") or "routine did not start")

    job = result.get("job") or {}

    return {
        "ok": True,
        "job_id": job_id,
        "name": job.get("name") or job_ref,
        # A manual run can execute inline or be handed to the gateway's
        # background worker; the UI says which so "done" is never a guess.
        "background": bool(job.get("execution_mode") == "background" or job.get("delegation_id")),
        "executed": bool(job.get("executed")),
        "success": job.get("execution_success"),
        "skipped": job.get("execution_skipped"),
    }


def _resolve_job_id(reference: str, jobs: List[Dict[str, Any]], bot: str) -> Optional[str]:
    """Match a schema's ``job`` against the profile's jobs.

    Accepts an exact id, an exact name, or a name with Bot Mode's
    ``[bot:<name>]`` prefix stripped — a bot writing its own schema should not
    have to reproduce a prefix the Routines UI hides from it.
    """
    marker = f"[bot:{bot}]"
    needle = reference.replace(marker, "").strip().lower()

    # The cron tool reports its identifier as ``job_id``; ``id`` is accepted too
    # so a schema written against either field keeps working.
    def ident(job: Dict[str, Any]) -> str:
        return str(job.get("job_id") or job.get("id") or "")

    for job in jobs:
        if ident(job) == reference:
            return ident(job)

    for job in jobs:
        name = str(job.get("name") or "").replace(marker, "").strip().lower()

        if name and name == needle:
            return ident(job)

    return None
