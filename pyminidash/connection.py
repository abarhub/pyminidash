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
    for name, cc in config.connections.items():
        if cc.token not in secrets:
            avail = ", ".join(sorted(secrets)) or "(aucune)"
            raise ConfigError(
                f"connexion '{name}' : la clé de token déclarée est absente de "
                f"secrets.toml (clés disponibles : {avail})"
            )
        if not secrets[cc.token].strip():
            raise ConfigError(
                f"connexion '{name}' : le token '{cc.token}' est vide dans secrets.toml"
            )
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
    return out
