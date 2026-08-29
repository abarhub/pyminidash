"""Point d'entrée : pyminidash --config config.toml [--port 8000] [--open]."""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

import pyminidash.providers  # noqa: F401 — enregistre les providers intégrés
from pyminidash.config import ConfigError, load_config
from pyminidash.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyminidash")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true",
                        help="ouvrir le navigateur au démarrage")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        raise SystemExit(2)

    app = create_app(config)

    if args.open:
        url = f"http://{args.host}:{args.port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
