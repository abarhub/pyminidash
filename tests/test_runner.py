from pyminidash.config import BlockConfig
from pyminidash.models import Record, text
from pyminidash.registry import provider
from pyminidash.runner import BlockError, BlockOk, run_block


async def test_ok_returns_records():
    @provider("r_ok")
    def r_ok(n: int = 2):
        return [Record(text("k", "L", str(i))) for i in range(n)]

    res = await run_block(BlockConfig(provider="r_ok", params={"n": 3}))
    assert isinstance(res, BlockOk)
    assert len(res.records) == 3
    assert res.computed_at is not None


async def test_empty_list_is_ok():
    @provider("r_empty")
    def r_empty():
        return []

    res = await run_block(BlockConfig(provider="r_empty"))
    assert isinstance(res, BlockOk)
    assert res.records == []


async def test_exception_becomes_block_error():
    @provider("r_boom")
    def r_boom():
        raise RuntimeError("cassé")

    res = await run_block(BlockConfig(provider="r_boom"))
    assert isinstance(res, BlockError)
    assert res.kind == "exception"
    assert "RuntimeError" in res.message and "cassé" in res.message


async def test_timeout_becomes_block_error():
    @provider("r_slow")
    def r_slow():
        import time
        time.sleep(0.5)
        return []

    res = await run_block(BlockConfig(provider="r_slow", timeout=0.1))
    assert isinstance(res, BlockError)
    assert res.kind == "timeout"


async def test_non_list_result_is_invalid():
    @provider("r_bad")
    def r_bad():
        return "pas une liste"

    res = await run_block(BlockConfig(provider="r_bad"))
    assert isinstance(res, BlockError)
    assert res.kind == "invalid_result"


async def test_heterogeneous_records_invalid():
    @provider("r_het")
    def r_het():
        return [Record(text("a", "A", "1")), Record(text("b", "B", "2"))]

    res = await run_block(BlockConfig(provider="r_het"))
    assert isinstance(res, BlockError)
    assert res.kind == "invalid_result"
