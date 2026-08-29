import pytest

from pyminidash.models import Record, text
from pyminidash.registry import (
    REGISTRY, get_provider, list_providers, provider, validate_params,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_decorator_registers_and_returns_function():
    @provider("demo")
    def demo(a: int, b: str = "x"):
        return [Record(text("k", "L", f"{a}{b}"))]

    assert demo(1) == [Record(text("k", "L", "1x"))]
    assert "demo" in REGISTRY
    assert list_providers() == ["demo"]


def test_duplicate_name_raises():
    @provider("demo")
    def demo():
        return []

    with pytest.raises(ValueError, match="demo"):
        @provider("demo")
        def demo2():
            return []


def test_get_provider_unknown_lists_available():
    @provider("alpha")
    def alpha():
        return []

    with pytest.raises(ValueError, match="alpha"):
        get_provider("beta")


def test_validate_params_ok():
    @provider("p")
    def p(paths: list, limit: int = 3):
        return []

    validate_params(get_provider("p"), {"paths": ["a"], "limit": 5})


def test_validate_params_missing_required():
    @provider("p")
    def p(paths: list):
        return []

    with pytest.raises(ValueError, match="signature attendue"):
        validate_params(get_provider("p"), {})


def test_validate_params_unknown_key():
    @provider("p")
    def p(limit: int = 3):
        return []

    with pytest.raises(ValueError, match="signature attendue"):
        validate_params(get_provider("p"), {"nope": 1})
