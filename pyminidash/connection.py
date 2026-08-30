"""Connexions authentifiées vers des services externes (Jira, Bitbucket, Bamboo)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from pyminidash.config import Config, ConfigError

log = logging.getLogger("pyminidash.connection")


@dataclass(frozen=True, repr=False)
class Connection:
    name: str
    base_url: str
    token: str
    verify: bool | str = True
    user: str | None = None

    def __repr__(self) -> str:
        return (
            f"Connection(name={self.name!r}, base_url={self.base_url!r}, "
            f"token=***, verify={self.verify!r}, user={self.user!r})"
        )

    def client(self, timeout: float = 15.0) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            verify=self.verify,
            timeout=timeout,
            follow_redirects=False,
        )


def build_connections(config: Config, secrets: dict[str, str]) -> dict[str, Connection]:
    out: dict[str, Connection] = {}
    disabled: list[str] = []
    for name, cc in config.connections.items():
        # Token absent ou vide → connexion désactivée (pas d'erreur fatale) : le
        # serveur démarre, les blocs qui l'utilisent s'afficheront en erreur.
        if cc.token not in secrets or not secrets[cc.token].strip():
            disabled.append(name)
            continue
        if isinstance(cc.verify, str) and not Path(cc.verify).is_file():
            raise ConfigError(
                f"connexion '{name}' : fichier CA '{cc.verify}' introuvable"
            )
        if cc.verify is False:
            log.warning(
                "connexion '%s' : verify=false — le token est transmis sans "
                "vérification du certificat TLS (risque d'interception)", name
            )
        out[name] = Connection(
            name=name,
            base_url=cc.base_url,
            token=secrets[cc.token],
            verify=cc.verify,
            user=cc.user,
        )
    if disabled:
        log.warning(
            "connexions désactivées (token absent/vide dans secrets.toml) : %s "
            "— les blocs qui les utilisent s'afficheront en erreur",
            ", ".join(disabled),
        )
    return out
