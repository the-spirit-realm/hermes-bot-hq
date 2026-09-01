"""Validation tests for the Home reader.

``data.json`` is model-authored, so these tests are mostly about hostile or
sloppy input: a widget type that does not exist, a `javascript:` URL dressed up
as an action, a table with ten thousand rows, a file caught mid-write. The rule
under test throughout is that bad input is *reported* — never rendered, never
crashing the fleet.

Stdlib ``unittest`` on purpose: the Hermes venv ships no test runner, and a
plugin's own suite should not need one installed to be runnable.

    PYTHONPATH=~/.hermes/hermes-agent \\
      ~/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

_SPEC = importlib.util.spec_from_file_location(
    "bot_control_center_api", Path(__file__).resolve().parent.parent / "dashboard" / "plugin_api.py"
)
api = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(api)


def _iso(minutes_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _schema(*widgets):
    schema, _ = api.validate_schema({"version": 1, "widgets": list(widgets)})

    return schema


class SchemaTests(unittest.TestCase):
    def test_widget_vocabulary_is_closed(self):
        schema, warnings = api.validate_schema(
            {"version": 1, "widgets": [{"id": "ok", "type": "kpi"}, {"id": "nope", "type": "iframe"}]}
        )

        # The unsupported widget survives as a placeholder rather than
        # vanishing: a silently dropped widget looks like it was never declared.
        self.assertEqual([(w["id"], w["supported"]) for w in schema["widgets"]], [("ok", True), ("nope", False)])
        self.assertTrue(any("iframe" in message for message in warnings))

    def test_duplicate_and_nameless_widgets_are_dropped_with_a_reason(self):
        schema, warnings = api.validate_schema(
            {"version": 1, "widgets": [{"id": "a", "type": "kpi"}, {"id": "a", "type": "table"}, {"type": "kpi"}]}
        )

        self.assertEqual([w["id"] for w in schema["widgets"]], ["a"])
        self.assertEqual(schema["widgets"][0]["type"], "kpi")
        self.assertTrue(any("duplicated" in message for message in warnings))
        self.assertTrue(any("no id" in message for message in warnings))

    def test_widget_count_is_capped(self):
        schema, warnings = api.validate_schema(
            {"version": 1, "widgets": [{"id": f"w{i}", "type": "kpi"} for i in range(40)]}
        )

        self.assertEqual(len(schema["widgets"]), api.MAX_WIDGETS)
        self.assertTrue(any("only the first" in message for message in warnings))

    def test_only_the_four_action_types_survive(self):
        schema, warnings = api.validate_schema(
            {
                "version": 1,
                "widgets": [],
                "actions": [
                    {"id": "run", "label": "Run", "type": "run_routine", "job": "digest"},
                    {"id": "chat", "label": "Chat", "type": "open_chat"},
                    {"id": "exec", "label": "Run locally", "type": "exec"},
                ],
            }
        )

        self.assertEqual([a["id"] for a in schema["actions"]], ["run", "chat"])
        self.assertTrue(any("exec" in message for message in warnings))

    def test_non_http_action_urls_are_refused(self):
        schema, warnings = api.validate_schema(
            {
                "version": 1,
                "widgets": [],
                "actions": [
                    {"id": "x", "type": "open_url", "url": "javascript:void(0)"},
                    {"id": "f", "type": "open_url", "url": "file:///tmp/notes.md"},
                    {"id": "ok", "type": "open_url", "url": "https://example.com"},
                ],
            }
        )

        self.assertEqual([a["id"] for a in schema["actions"]], ["ok"])
        self.assertEqual(len([m for m in warnings if "http(s)" in m]), 2)

    def test_an_action_without_its_target_is_not_a_button(self):
        schema, warnings = api.validate_schema(
            {
                "version": 1,
                "widgets": [],
                "actions": [{"id": "r", "type": "run_routine"}, {"id": "p", "type": "open_path"}],
            }
        )

        self.assertEqual(schema["actions"], [])
        self.assertEqual(len(warnings), 2)

    def test_open_path_expands_the_home_shorthand(self):
        schema, _ = api.validate_schema(
            {"version": 1, "widgets": [], "actions": [{"id": "p", "type": "open_path", "path": "~/notes.md"}]}
        )

        self.assertEqual(schema["actions"][0]["path"], str(Path.home() / "notes.md"))

    def test_a_newer_schema_version_still_renders(self):
        schema, warnings = api.validate_schema({"version": 99, "widgets": [{"id": "a", "type": "kpi"}]})

        self.assertEqual(len(schema["widgets"]), 1)
        self.assertTrue(any("newer" in message for message in warnings))

    def test_a_non_object_schema_is_a_single_clear_error(self):
        schema, warnings = api.validate_schema(["not", "a", "schema"])

        self.assertEqual(schema, {})
        self.assertEqual(warnings, ["schema.json must be a JSON object"])


class DataTests(unittest.TestCase):
    def test_data_for_an_undeclared_widget_is_reported_not_rendered(self):
        schema = _schema({"id": "declared", "type": "kpi"})
        data, warnings = api.validate_data(
            {"widgets": {"declared": {"items": []}, "smuggled": {"items": []}}}, schema
        )

        self.assertEqual(set(data["widgets"]), {"declared"})
        self.assertTrue(any("smuggled" in message for message in warnings))

    def test_collections_are_capped_per_type(self):
        schema = _schema(
            {"id": "k", "type": "kpi"},
            {"id": "t", "type": "table"},
            {"id": "l", "type": "list"},
        )
        data, warnings = api.validate_data(
            {
                "widgets": {
                    "k": {"items": [{"label": f"{i}", "value": "1"} for i in range(50)]},
                    "t": {"columns": ["a", "b"], "rows": [["1", "2"] for _ in range(500)]},
                    "l": {"items": [{"title": f"{i}"} for i in range(500)]},
                }
            },
            schema,
        )

        self.assertEqual(len(data["widgets"]["k"]["items"]), api.CAPS["kpi_items"])
        self.assertEqual(len(data["widgets"]["t"]["rows"]), api.CAPS["table_rows"])
        self.assertEqual(len(data["widgets"]["l"]["items"]), api.CAPS["list_items"])
        self.assertEqual(len(warnings), 3)

    def test_table_rows_are_trimmed_to_the_declared_column_count(self):
        schema = _schema({"id": "t", "type": "table"})
        data, _ = api.validate_data(
            {"widgets": {"t": {"columns": ["a", "b"], "rows": [["1", "2", "3", "4"]]}}}, schema
        )

        self.assertEqual(data["widgets"]["t"]["rows"], [["1", "2"]])

    def test_markdown_is_truncated_rather_than_streamed_whole(self):
        schema = _schema({"id": "m", "type": "markdown"})
        data, warnings = api.validate_data({"widgets": {"m": {"text": "x" * 50_000}}}, schema)

        self.assertEqual(len(data["widgets"]["m"]["text"]), api.CAPS["markdown_chars"])
        self.assertTrue(any("truncated" in message for message in warnings))

    def test_timeseries_accepts_timestamps_and_drops_unplottable_points(self):
        schema = _schema({"id": "s", "type": "timeseries"})
        data, _ = api.validate_data(
            {
                "widgets": {
                    "s": {
                        "series": [
                            {
                                "label": "items",
                                "points": [
                                    ["2026-08-29T00:00:00Z", 5],
                                    [1, 6],
                                    ["not a date", 7],
                                    [2, "not a number"],
                                    [3],
                                ],
                            }
                        ]
                    }
                }
            },
            schema,
        )

        points = data["widgets"]["s"]["series"][0]["points"]

        self.assertEqual([point[1] for point in points], [5.0, 6.0])
        self.assertEqual(points[0][0], datetime(2026, 8, 29, tzinfo=timezone.utc).timestamp())

    def test_unknown_tones_and_levels_fall_back_instead_of_leaking_through(self):
        schema = _schema({"id": "k", "type": "kpi"}, {"id": "a", "type": "alerts"})
        data, _ = api.validate_data(
            {
                "widgets": {
                    "k": {"items": [{"label": "x", "value": "1", "tone": "on-fire"}]},
                    "a": {"items": [{"level": "catastrophe", "message": "x"}]},
                }
            },
            schema,
        )

        self.assertEqual(data["widgets"]["k"]["items"][0]["tone"], "neutral")
        self.assertEqual(data["widgets"]["a"]["items"][0]["level"], "info")

    def test_an_unsupported_widget_gets_no_payload_even_if_data_exists(self):
        schema = _schema({"id": "x", "type": "iframe"})
        data, _ = api.validate_data({"widgets": {"x": {"items": [{"title": "hi"}]}}}, schema)

        self.assertEqual(data["widgets"], {})

    def test_staleness_is_computed_from_updated_at(self):
        schema = _schema({"id": "k", "type": "kpi"})

        fresh, _ = api.validate_data({"updated_at": _iso(10), "stale_after_minutes": 60}, schema)
        stale, _ = api.validate_data({"updated_at": _iso(600), "stale_after_minutes": 60}, schema)
        defaulted, _ = api.validate_data({"updated_at": _iso(10), "stale_after_minutes": -5}, schema)

        self.assertIs(fresh["stale"], False)
        self.assertIs(stale["stale"], True)
        self.assertEqual(defaulted["stale_after_minutes"], api.DEFAULT_STALE_AFTER_MINUTES)

    def test_a_missing_updated_at_is_never_reported_as_stale(self):
        schema = _schema({"id": "k", "type": "kpi"})
        data, _ = api.validate_data({"widgets": {}}, schema)

        self.assertIsNone(data["updated_at"])
        self.assertIs(data["stale"], False)


class FileTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def test_a_missing_file_is_not_an_error(self):
        payload, error = api._read_json(self.tmp / "absent.json")

        self.assertIsNone(payload)
        self.assertIsNone(error)

    def test_a_torn_write_is_reported_as_such(self):
        path = self.tmp / "data.json"
        path.write_text('{"widgets": {"a": ')

        payload, error = api._read_json(path)

        self.assertIsNone(payload)
        self.assertIn("not valid JSON", error)

    def test_an_oversized_file_is_refused_before_parsing(self):
        path = self.tmp / "data.json"
        path.write_text(json.dumps({"pad": "x" * (api.MAX_FILE_BYTES + 100)}))

        payload, error = api._read_json(path)

        self.assertIsNone(payload)
        self.assertIn("limit", error)

    def test_reading_a_home_for_an_unknown_bot_is_a_404(self):
        with self.assertRaises(HTTPException) as caught:
            api.read_home("definitely-not-a-profile")

        self.assertEqual(caught.exception.status_code, 404)


class RoutineResolutionTests(unittest.TestCase):
    def test_a_routine_resolves_by_id_or_name_with_or_without_the_bot_prefix(self):
        jobs = [{"job_id": "abc123", "name": "[bot:researcher] Morning Digest"}]

        for reference in ("abc123", "Morning Digest", "morning digest", "[bot:researcher] Morning Digest"):
            self.assertEqual(api._resolve_job_id(reference, jobs, "researcher"), "abc123")

        self.assertIsNone(api._resolve_job_id("Evening Digest", jobs, "researcher"))


if __name__ == "__main__":
    unittest.main()
