from decimal import Decimal
import pytest

from output.backend.pricing import (
    PriceService,
    UnsupportedSymbolError,
)


def test_supported_symbols_contains_expected_and_quantized():
    svc = PriceService()
    supported = svc.supported_symbols()

    # Keys should be uppercased and include the expected symbols
    assert set(supported.keys()) >= {"AAPL", "TSLA", "GOOGL"}

    # Values should be Decimal quantized to cents
    assert supported["AAPL"] == Decimal("150.00")
    assert supported["TSLA"] == Decimal("720.50")
    assert supported["GOOGL"] == Decimal("2800.75")


def test_get_share_price_case_insensitive_and_returns_decimal():
    svc = PriceService()

    # case-insensitive lookup
    assert svc.get_share_price('aapl') == Decimal('150.00')
    assert svc.get_share_price('TsLa') == Decimal('720.50')
    assert svc.get_share_price('GOOGL') == Decimal('2800.75')

    # return type is Decimal and quantized
    p = svc.get_share_price('AAPL')
    assert isinstance(p, Decimal)
    assert p == Decimal('150.00')


@pytest.mark.parametrize("bad_symbol", [None, '', 'XYZ', ' AAPL '])
def test_get_share_price_invalid_symbol_raises(bad_symbol):
    svc = PriceService()
    with pytest.raises(UnsupportedSymbolError):
        svc.get_share_price(bad_symbol)


def test_is_supported_handles_non_string_and_whitespace():
    svc = PriceService()

    assert not svc.is_supported(123)
    assert not svc.is_supported(None)

    # Whitespace changes the string and should not be treated as supported
    assert not svc.is_supported(' AAPL ')

    # Normal supported symbol
    assert svc.is_supported('aapl')


def test_supported_symbols_returns_shallow_copy_and_is_immutable_to_caller_mutation():
    svc = PriceService()
    supported1 = svc.supported_symbols()
    # mutate the returned dict
    supported1['NEW'] = Decimal('1.23')

    # fetching supported symbols again should not include our mutation
    supported2 = svc.supported_symbols()
    assert 'NEW' not in supported2

    # original mapping keys are uppercase
    for k in supported2.keys():
        assert k == k.upper()


def test_supported_symbols_keys_are_uppercase_and_prices_preserved():
    svc = PriceService()
    supported = svc.supported_symbols()
    for k, v in supported.items():
        assert isinstance(k, str)
        assert k == k.upper()
        assert isinstance(v, Decimal)
        # values match expected canonical ones if present
        if k == 'AAPL':
            assert v == Decimal('150.00')
        if k == 'TSLA':
            assert v == Decimal('720.50')
        if k == 'GOOGL':
            assert v == Decimal('2800.75')