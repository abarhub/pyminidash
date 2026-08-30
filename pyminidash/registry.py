"""Registre global des providers. Un provider est une fonction décorée
@provider("nom") ; ses modules sont importés au démarrage pour l'enregistrer."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProviderDef:
    name: str
    func: Callable[..., list]
    signature: inspect.Signature
    validate: Callable[[dict], None] | None = None


REGISTRY: dict[str, ProviderDef] = {}


def provider(
    name: str, *, validate: Callable[[dict], None] | None = None
) -> Callable[[Callable[..., list]], Callable[..., list]]:
    def decorator(func: Callable[..., list]) -> Callable[..., list]:
        if name in REGISTRY:
            raise ValueError(f"provider '{name}' déjà enregistré")
        REGISTRY[name] = ProviderDef(
            name=name, func=func, signature=inspect.signature(func),
            validate=validate,
        )
        return func

    return decorator


def list_providers() -> list[str]:
    return sorted(REGISTRY)


def get_provider(name: str) -> ProviderDef:
    try:
        return REGISTRY[name]
    except KeyError:
        available = ", ".join(list_providers()) or "(aucun)"
        raise ValueError(
            f"provider inconnu: '{name}' ; providers disponibles : {available}"
        ) from None


def validate_params(pdef: ProviderDef, params: dict, *,
                    injected: frozenset[str] = frozenset()) -> None:
    clash = injected & params.keys()
    if clash:
        k = sorted(clash)[0]
        raise ValueError(
            f"{pdef.name}: le paramètre '{k}' est injecté, à ne pas mettre dans params"
        )
    probe = {n: None for n in injected if n in pdef.signature.parameters}
    probe.update(params)
    try:
        pdef.signature.bind(**probe)
    except TypeError as exc:
        raise ValueError(
            f"{pdef.name}: {exc} ; signature attendue: {pdef.signature}"
        ) from None
