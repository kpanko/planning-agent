"""Terminal chat interface for the planning agent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any, Optional

import logfire
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from .agent import create_agent
from .context import build_context
from .extraction import run_extraction

console = Console()
_stderr = Console(stderr=True)


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
    logfire.configure(
        service_name="planning-agent-cli",
        send_to_logfire="if-token-present",
    )
    logfire.instrument_pydantic_ai()
    console.print("Building context...")
    ctx = build_context()

    # Mutable holder so the confirm callback can
    # pause/resume the Live display during prompts.
    active_live: dict[str, Optional[Live]] = {
        "live": None,
    }

    async def cli_confirm(
        name: str, detail: str = "",
    ) -> bool:
        """Pause Live, prompt, then resume."""
        live = active_live["live"]
        if live:
            live.stop()
        _stderr.print(
            f"  [dim]tool:[/dim]"
            f" [cyan]{name}[/cyan]"
            + (f" [dim]{detail}[/dim]" if detail else "")
        )
        try:
            answer = await asyncio.to_thread(
                lambda: input("  Run? [y/N] ")
                .strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            return False
        finally:
            if live:
                live.start()
        return answer in ("y", "yes")

    agent = create_agent(confirm=cli_confirm)
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
            console.print()
            full_text = ""

            live = Live(
                console=console,
                refresh_per_second=10,
            )
            active_live["live"] = live
            live.start()

            try:
                async def _stream_handler(
                    _run_ctx: Any,
                    events: AsyncIterable[Any],
                ) -> None:
                    nonlocal full_text
                    async for event in events:
                        if (
                            isinstance(
                                event, PartStartEvent
                            )
                            and isinstance(
                                event.part, TextPart
                            )
                            and event.part.content
                        ):
                            full_text += (
                                event.part.content
                            )
                            live.update(
                                Markdown(full_text)
                            )
                        elif (
                            isinstance(
                                event, PartDeltaEvent
                            )
                            and isinstance(
                                event.delta,
                                TextPartDelta,
                            )
                            and event.delta.content_delta
                        ):
                            full_text += (
                                event.delta.content_delta
                            )
                            live.update(
                                Markdown(full_text)
                            )

                result = await agent.run(
                    user_input,
                    deps=ctx,
                    message_history=history,
                    event_stream_handler=(
                        _stream_handler
                    ),
                )
            finally:
                live.stop()
                active_live["live"] = None

            history = result.all_messages()
            console.print()
        except Exception as exc:
            logging.getLogger("planning-agent").exception(
                "agent.run_stream failed"
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

    if history:
        print("Extracting memories...")
        await run_extraction(history)
        print("Done.")


def main_sync() -> None:
    """Synchronous entry point for console_scripts."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
