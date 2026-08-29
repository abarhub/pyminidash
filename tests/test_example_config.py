from pathlib import Path

import pyminidash.providers  # noqa: F401 — enregistre les providers réels
from pyminidash.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def test_example_config_is_valid():
    cfg = load_config(EXAMPLE)
    assert cfg.app.default_group
    assert len(cfg.groups) >= 2
    # tous les providers référencés existent → pas d'exception levée
