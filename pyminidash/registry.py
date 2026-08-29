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


REGISTRY: dict[str, ProviderDef] = {}


def provider(name: str) -> Callable[[Callable[..., list]], Callable[..., list]]:
    def decorator(func: Callable[..., list]) -> Callable[..., list]:
        if name in REGISTRY:
            raise ValueError(f"provider '{name}' déjà enregistré")
        REGISTRY[name] = ProviderDef(name=name, func=func,
                                     signature=inspect.signature(func))
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


def validate_params(pdef: ProviderDef, params: dict) -> None:
    try:
        pdef.signature.bind(**params)
    except TypeError as exc:
        raise ValueError(
            f"{pdef.name}: {exc} ; signature attendue: {pdef.signature}"
        ) from None
