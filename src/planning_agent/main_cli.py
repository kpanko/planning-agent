"""Terminal chat interface for the planning agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from .agent import create_agent
from .context import build_context
from .extraction import run_extraction

console = Console()


def _setup_logging() -> None:
    """Configure logging to a file."""
    from planning_context.storage import get_data_dir

    log_path = get_data_dir() / "agent.log"
    handler = logging.FileHandler(
        log_path, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s"
        " %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root = logging.getLogger("planning-agent")
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def main() -> None:
    """Run the planning agent in the terminal."""
    _setup_logging()
    console.print("Building context...")
    ctx = build_context()
    agent = create_agent()
    console.print(
        "Planning agent ready."
        " Type 'done' to exit.\n"
    )

    history: list[Any] = []

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not user_input:
            continue
        if user_input.lower() in (
            "done", "exit", "quit",
        ):
            break

        try:
            result = await agent.run(
                user_input,
                deps=ctx,
                message_history=history,
            )
        except Exception as exc:
            logging.getLogger("planning-agent").exception(
                "agent.run failed"
            )
            console.print(
                f"\n[red]Error:[/red]"
                f" [yellow]{type(exc).__name__}:"
                f" {exc}[/yellow]"
            )
            console.print(
                "[dim]Full traceback in"
                " ~/.planning-agent/agent.log[/dim]\n"
            )
            continue
        console.print()
        console.print(Markdown(result.output))
        console.print()
        history = result.all_messages()

    if history:
        print("Extracting memories...")
        await run_extraction(history)
        print("Done.")


def main_sync() -> None:
    """Synchronous entry point for console_scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
