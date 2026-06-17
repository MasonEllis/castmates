"""Dev entrypoint: run the FastAPI app with auto-reload.

Usage:
    python main.py                 # default host/port
    python main.py --port 9000     # see flags below

This is intentionally a thin wrapper around ``uvicorn.run`` so the same
``uvicorn app.main:app`` invocation still works for advanced cases (multiple
workers, custom log config, etc.).
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the actors-overlap backend.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload on code changes (use in production-ish runs).",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
    )
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
