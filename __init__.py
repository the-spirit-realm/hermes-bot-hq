"""Bot HQ — agent half.

The plugin's real surfaces live elsewhere: the UI is a desktop plugin
(``desktop/plugin.js``) and the Home reader is a FastAPI router
(``dashboard/plugin_api.py``). This module exists only to hand the bundled
``bot-home`` skill to the agent (loadable as ``hermes-bot-hq:bot-home``),
so a bot can learn the Home contract and
publish its own dashboard without being told the file layout every time.
"""

from __future__ import annotations

from pathlib import Path

from .setup import run_setup, setup_argparse


def register(ctx) -> None:
    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                ctx.register_skill(child.name, skill_md)

    # `hermes hermes-bot-hq setup` — the one seamless-onboarding command.
    # Brings every bot profile (present and future) to a working dashboard:
    # creates the missing plugins/ symlink a fresh profile never gets on its
    # own, enables the plugin (never with --allow-tool-override), restarts
    # that profile's backend, and verifies the dashboard route actually
    # mounted instead of trusting the enable command's exit code alone.
    ctx.register_cli_command(
        name="hermes-bot-hq",
        help="Set up Bot HQ's dashboard across all your bot profiles",
        setup_fn=setup_argparse,
        handler_fn=run_setup,
    )
