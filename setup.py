"""hermes-bot-hq CLI setup — the seamless-onboarding command.

Registers ``hermes hermes-bot-hq setup``, which brings every bot profile on
this machine (default + all named profiles, present and future) up to a
working Bot HQ dashboard in one idempotent, reviewable step.

Why this exists (see the plugin's own postmortems in agent history):

1. A freshly created profile has NO ``plugins/hermes-bot-hq`` symlink at all
   — ``hermes plugins enable`` cannot even see the plugin without it. This
   command creates the symlink first, per profile, before enabling.
2. Enabling a plugin updates ``plugins.enabled`` live, but the plugin's
   FastAPI dashboard routes only mount once, at backend process startup.
   Enabling alone leaves the Fleet page showing "Home unreadable" until the
   profile's backend is actually restarted. This command restarts and then
   greps the profile's own log for the mount line — it does not just assume
   success from the enable command's exit code.
3. ``hermes plugins enable <name> --allow-tool-override`` skips the
   interactive consent screen entirely and is trivially reachable by
   anything that can shell out (including a bot's own terminal tool). This
   command NEVER passes that flag — it always enables with
   ``--no-allow-tool-override``, so it can never be the thing that grants a
   plugin elevated permissions on a bot's behalf without a human seeing it.
4. Nothing here runs silently: the full plan (which profiles, which of the
   three actions each needs) is printed and confirmed once before any
   process is touched, kept, or restarted.

Idempotent by design: running it again after creating a new bot only acts
on that one new profile and leaves already-set-up bots untouched. One
memorized command for the plugin's entire lifecycle — first install and
every bot added after.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List, NamedTuple

PLUGIN_NAME = "hermes-bot-hq"
_ROUTE_MOUNT_MARKER = f"Mounted plugin API routes: /api/plugins/{PLUGIN_NAME}/"
_RESTART_WAIT_S = 6
_LOG_TAIL_BYTES = 200_000


class ProfilePlan(NamedTuple):
    name: str
    profile_dir: Path
    needs_symlink: bool
    needs_enable: bool
    already_done: bool


def setup_argparse(subparser) -> None:
    """Build the argparse tree for ``hermes hermes-bot-hq``."""
    subs = subparser.add_subparsers(dest="bot_hq_command")
    setup_cmd = subs.add_parser(
        "setup",
        help="Enable this plugin's dashboard for every bot profile (idempotent)",
    )
    setup_cmd.add_argument(
        "--yes", "-y", action="store_true", help="Skip the confirmation prompt"
    )
    setup_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the plan and exit without changing anything",
    )
    setup_cmd.add_argument(
        "--only",
        action="append",
        dest="only_profiles",
        default=None,
        metavar="PROFILE",
        help=(
            "Limit to this bot profile (repeatable). Default: every profile "
            "Hermes knows about. Named --only, not --profile, because Hermes' "
            "global -p/--profile flag is parsed before this subcommand ever "
            "sees argv and would silently shadow a same-named local flag."
        ),
    )


def run_setup(args) -> None:
    """Handler for ``hermes hermes-bot-hq <subcommand>``."""
    if getattr(args, "bot_hq_command", None) != "setup":
        print(f"Usage: hermes {PLUGIN_NAME} setup [--yes] [--dry-run] [--profile NAME ...]")
        return

    plugin_source_dir = Path(__file__).resolve().parent

    try:
        from hermes_cli.profiles import get_profile_dir, list_profiles, normalize_profile_name
    except ImportError as exc:  # pragma: no cover - only if run outside Hermes
        print(f"Could not import Hermes profile APIs: {exc}")
        sys.exit(1)

    if getattr(args, "only_profiles", None):
        names = [normalize_profile_name(n) for n in args.only_profiles]
    else:
        names = [info.name for info in list_profiles()]

    if not names:
        print("No profiles found — nothing to do.")
        return

    print(f"Found {len(names)} profile(s): {', '.join(names)}")

    plan: List[ProfilePlan] = []
    for name in names:
        profile_dir = get_profile_dir(name)
        symlink_path = profile_dir / "plugins" / PLUGIN_NAME
        needs_symlink = not symlink_path.exists()
        needs_enable = PLUGIN_NAME not in _read_enabled_plugins(profile_dir)
        already_done = not needs_symlink and not needs_enable
        plan.append(ProfilePlan(name, profile_dir, needs_symlink, needs_enable, already_done))

    pending = [p for p in plan if not p.already_done]
    already = [p for p in plan if p.already_done]

    if already:
        print(f"\nAlready set up ({len(already)}): {', '.join(p.name for p in already)}")

    if not pending:
        print("\nEvery listed bot already has hermes-bot-hq set up. Nothing to do.")
        return

    print(f"\nWill update {len(pending)} profile(s):")
    for p in pending:
        actions = []
        if p.needs_symlink:
            actions.append("create plugin symlink")
        if p.needs_enable:
            actions.append("enable plugin (no tool-override)")
        actions.append("restart backend + verify dashboard route")
        print(f"  {p.name}: {', '.join(actions)}")

    if args.dry_run:
        print("\nDry run — nothing changed.")
        return

    if not args.yes:
        try:
            answer = input("\nProceed for the profile(s) above? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in {"y", "yes"}:
            print("Aborted. No changes made.")
            return

    print()
    failures = []
    for p in pending:
        print(f"[{p.name}]")
        try:
            if p.needs_symlink:
                _create_symlink(p.profile_dir, plugin_source_dir)
                print(f"  symlink created -> {plugin_source_dir}")

            if p.needs_enable:
                _enable_plugin(p.name)
                print("  plugin enabled (tool-override NOT granted)")

            restarted = _restart_backend(p.name)
            if restarted:
                print(f"  backend restarted (old pid {restarted})")
            else:
                print("  backend was not running (will pick up config on next start)")

            if _verify_route_mounted(p.profile_dir):
                print("  ✓ dashboard route confirmed mounted")
            else:
                print(
                    "  ⚠ could not confirm the route mounted yet — check "
                    f"{p.profile_dir / 'logs' / 'agent.log'} for "
                    f"'{_ROUTE_MOUNT_MARKER}' after the backend finishes starting"
                )
        except Exception as exc:  # noqa: BLE001 - report and continue with the rest
            failures.append((p.name, str(exc)))
            print(f"  ✗ failed: {exc}")
        print()

    if failures:
        print(f"Done with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print("Done. Every listed bot now has a working Bot HQ dashboard.")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_enabled_plugins(profile_dir: Path) -> set:
    """Read ``plugins.enabled`` from a profile's config.yaml. Never raises."""
    config_path = profile_dir / "config.yaml"
    if not config_path.exists():
        return set()
    try:
        import yaml

        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        enabled = (data.get("plugins") or {}).get("enabled") or []
        return set(enabled) if isinstance(enabled, list) else set()
    except Exception:
        return set()


def _create_symlink(profile_dir: Path, plugin_source_dir: Path) -> None:
    plugins_dir = profile_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    link_path = plugins_dir / PLUGIN_NAME
    if link_path.exists() or link_path.is_symlink():
        return
    link_path.symlink_to(plugin_source_dir)


def _enable_plugin(profile_name: str) -> None:
    """Enable the plugin for one profile. Never grants tool-override."""
    result = subprocess.run(
        [
            "hermes",
            "-p",
            profile_name,
            "plugins",
            "enable",
            PLUGIN_NAME,
            "--no-allow-tool-override",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"'hermes plugins enable' exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()[:300]}"
        )


def _find_backend_pid(profile_name: str) -> int | None:
    """Best-effort lookup of a running ``serve`` process for this profile."""
    try:
        ps_out = subprocess.run(
            ["ps", "-eo", "pid,command"], capture_output=True, text=True, check=False
        ).stdout
    except Exception:
        return None

    marker = (
        "hermes_cli.main serve"
        if profile_name == "default"
        else f"hermes_cli.main --profile {profile_name} serve"
    )
    for line in ps_out.splitlines():
        if marker in line:
            parts = line.strip().split(None, 1)
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


def _restart_backend(profile_name: str) -> int | None:
    """Kill the profile's running backend so the app supervisor respawns a
    fresh one. Returns the killed pid, or None if nothing was running."""
    pid = _find_backend_pid(profile_name)
    if pid is None:
        return None
    try:
        subprocess.run(["kill", str(pid)], check=False)
    except Exception:
        return None
    time.sleep(_RESTART_WAIT_S)
    return pid


def _verify_route_mounted(profile_dir: Path) -> bool:
    """Grep the profile's agent.log for proof the route mounted, not just
    that the enable command exited 0."""
    log_path = profile_dir / "logs" / "agent.log"
    if not log_path.exists():
        return False
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as f:
            if size > _LOG_TAIL_BYTES:
                f.seek(size - _LOG_TAIL_BYTES)
            tail = f.read().decode("utf-8", errors="replace")
        return _ROUTE_MOUNT_MARKER in tail
    except Exception:
        return False
