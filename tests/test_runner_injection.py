import pytest

from pyminidash.config import BlockConfig
from pyminidash.connection import Connection
from pyminidash.errors import ProviderError
from pyminidash.models import Record, title
from pyminidash.registry import provider
from pyminidash.runner import BlockError, BlockOk, run_block


async def test_connection_is_injected():
    seen = {}

    @provider("inj")
    def inj(connection, q: str):
        seen["conn"] = connection
        return [Record(title("k", "K", q))]

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(
        BlockConfig(provider="inj", connection="jira", params={"q": "hi"}),
        {"jira": conn},
    )
    assert isinstance(res, BlockOk)
    assert seen["conn"] is conn


async def test_no_connection_param_means_no_injection():
    @provider("plain")
    def plain(n: int = 1):
        return [Record(title("k", "K", str(n)))]

    res = await run_block(BlockConfig(provider="plain", params={"n": 3}))
    assert isinstance(res, BlockOk)
    assert res.records[0].fields[0].value == "3"


async def test_provider_error_message_has_no_type_prefix():
    @provider("boom")
    def boom(connection):
        raise ProviderError("authentification refusée pour la connexion 'jira'")

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(
        BlockConfig(provider="boom", connection="jira"), {"jira": conn}
    )
    assert isinstance(res, BlockError)
    assert res.message == "authentification refusée pour la connexion 'jira'"
    assert "ProviderError" not in res.message


async def test_unexpected_exception_still_prefixed():
    @provider("crash")
    def crash(connection):
        raise RuntimeError("bug")

    conn = Connection(name="jira", base_url="https://x", token="t")
    res = await run_block(BlockConfig(provider="crash", connection="jira"), {"jira": conn})
    assert isinstance(res, BlockError)
    assert res.message == "RuntimeError: bug"
