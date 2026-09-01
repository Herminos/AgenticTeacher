import pytest

from app.services.compute_service import ComputeService


@pytest.mark.asyncio
async def test_safe_integral() -> None:
    result, warnings, verified = await ComputeService().compute("integrate(x**2, x)", 3000)
    assert result == "x**3/3"
    assert warnings == []
    assert verified is True


@pytest.mark.asyncio
async def test_rejects_attribute_access() -> None:
    with pytest.raises(ValueError):
        await ComputeService().compute("__import__('os').system('id')", 3000)
