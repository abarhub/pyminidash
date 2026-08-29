"""Fixtures partagées : isolation du registre global + providers factices."""
import pytest

from pyminidash.models import Record, status, text, title
from pyminidash.models import StatusLevel
from pyminidash.registry import REGISTRY, provider


@pytest.fixture(autouse=True)
def _registry_snapshot():
    """Restaure REGISTRY à l'état d'avant-test (évite les fuites entre tests)."""
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


@pytest.fixture
def dummy_providers():
    """Enregistre des providers de test. Nettoyage assuré par _registry_snapshot."""
    @provider("dummy_rows")
    def dummy_rows(n: int = 2):
        return [
            Record(
                title("name", "Nom", f"item{i}"),
                status("state", "État", "UP", level=StatusLevel.OK, summary=True),
                text("detail", "Détail", f"ligne cachée {i}"),
            )
            for i in range(n)
        ]

    @provider("dummy_boom")
    def dummy_boom():
        raise RuntimeError("boom interne")

    @provider("dummy_empty")
    def dummy_empty():
        return []

    return ["dummy_rows", "dummy_boom", "dummy_empty"]
