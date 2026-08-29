"""Fabrique de l'application FastAPI."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyminidash.config import Config
from pyminidash.format import format_value
from pyminidash.web import routes

_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def create_app(config: Config, connections: dict | None = None) -> FastAPI:
    app = FastAPI(title=config.app.title)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["format_field"] = format_value

    app.state.config = config
    app.state.connections = connections or {}
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(routes.router)
    return app
