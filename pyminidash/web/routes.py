"""Routes HTTP. La page d'un groupe pose un placeholder auto-chargé par bloc ;
le fragment d'un bloc est servi par block_fragment (Task 8)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from pyminidash.config import GroupConfig
from pyminidash.runner import BlockError, run_block
from pyminidash.web.render import to_cards, to_table

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


@router.get("/groups/{group_id}/blocks/{index}", response_class=HTMLResponse)
async def block_fragment(request: Request, group_id: str, index: int) -> HTMLResponse:
    group = _get_group(request, group_id)
    # FastAPI parses negative ints as valid; this guard is load-bearing, not dead code
    if index < 0 or index >= len(group.blocks):
        raise HTTPException(status_code=404, detail="bloc inexistant")
    block = group.blocks[index]
    url = f"/groups/{group_id}/blocks/{index}"
    templates = request.app.state.templates

    result = await run_block(block)
    context = {
        "config": request.app.state.config,
        "group": group,
        "block": block,
        "url": url,
        "active_group_id": group_id,
        "computed_at": None,
    }

    if isinstance(result, BlockError):
        context["error"] = result
        return templates.TemplateResponse(
            request=request, name="_error.html", context=context
        )

    context["computed_at"] = result.computed_at
    if group.type == "table":
        context["table"] = to_table(result.records) if result.records else None
        return templates.TemplateResponse(
            request=request, name="_table.html", context=context
        )

    context["cards"] = to_cards(result.records)
    return templates.TemplateResponse(
        request=request, name="_cards.html", context=context
    )
