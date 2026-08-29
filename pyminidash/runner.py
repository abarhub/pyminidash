"""Exécution d'un bloc : appelle le provider dans un thread, avec timeout,
et normalise le résultat ou l'erreur."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from pyminidash.config import BlockConfig
from pyminidash.models import Record
from pyminidash.registry import get_provider

log = logging.getLogger("pyminidash.runner")

DEFAULT_TIMEOUT: float = 10.0


@dataclass(frozen=True)
class BlockError:
    kind: str  # "exception" | "timeout" | "invalid_result"
    message: str


@dataclass(frozen=True)
class BlockOk:
    records: list[Record]
    computed_at: datetime


BlockResult = BlockOk | BlockError


def _check_records(result: object) -> str | None:
    if not isinstance(result, list) or any(not isinstance(r, Record) for r in result):
        return "le provider n'a pas renvoyé une list[Record]"
    if result:
        expected = result[0].keys()
        for r in result[1:]:
            if r.keys() != expected:
                return (f"records hétérogènes : attendu {expected}, "
                        f"obtenu {r.keys()}")
    return None


async def run_block(block: BlockConfig) -> BlockResult:
    pdef = get_provider(block.provider)
    timeout = block.timeout or DEFAULT_TIMEOUT
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(pdef.func, **block.params), timeout
        )
    except (asyncio.TimeoutError, TimeoutError):
        # asyncio.wait_for annule le *future*, pas le thread : le worker est
        # abandonné, pas interrompu — le provider continue jusqu'au bout dans le
        # threadpool par défaut. Les providers intégrés sont auto-bornés (httpx
        # porte son propre timeout, les appels psutil sont finis) ; tout nouveau
        # provider faisant de l'I/O bloquante DOIT imposer son propre timeout.
        log.warning("bloc '%s' : délai dépassé (%gs)", block.provider, timeout)
        return BlockError("timeout", f"délai dépassé ({timeout:g} s)")
    except Exception as exc:  # noqa: BLE001 — on veut tout attraper
        log.exception("bloc '%s' : exception du provider", block.provider)
        return BlockError("exception", f"{type(exc).__name__}: {exc}")

    problem = _check_records(result)
    if problem:
        log.error("bloc '%s' : %s", block.provider, problem)
        return BlockError("invalid_result", problem)
    return BlockOk(records=result, computed_at=datetime.now())
