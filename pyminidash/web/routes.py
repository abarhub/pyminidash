"""Routes HTTP. La page d'un groupe pose un placeholder auto-chargé par bloc ;
le fragment d'un bloc est servi par block_fragment (Task 8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pyminidash.config import GroupConfig

router = APIRouter()


def _get_group(request: Request, group_id: str) -> GroupConfig:
    for group in request.app.state.config.groups:
        if group.id == group_id:
            return group
    raise HTTPException(status_code=404, detail=f"groupe inconnu : {group_id}")


@router.get("/")
def index(request: Request) -> RedirectResponse:
    default = request.app.state.config.app.default_group
    return RedirectResponse(url=f"/groups/{default}")


@router.get("/groups/{group_id}", response_class=HTMLResponse)
def group_page(request: Request, group_id: str) -> HTMLResponse:
    group = _get_group(request, group_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="group.html",
        context={
            "config": request.app.state.config,
            "group": group,
            "active_group_id": group_id,
        },
    )
