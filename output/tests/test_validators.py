from decimal import Decimal
import pytest

from output.backend.validators import (
    OperationValidator,
    OperationValidationError,
    InvalidAmountError,
    UnsupportedSymbolError,
    InsufficientFundsError,
    InsufficientHoldingsError,
)


def test_validate_amount_rounding_and_positive():
    v = OperationValidator()

    # rounding to cents (ROUND_HALF_UP)
    assert v.validate_amount('1.234') == Decimal('1.23')
    assert v.validate_amount('0.105') == Decimal('0.11')
    # floats and ints accepted
    assert v.validate_amount(2) == Decimal('2.00')
    assert v.validate_amount(0.235) == Decimal('0.24')


@pytest.mark.parametrize('bad', [0, '0.00', -1, '-5.00'])
def test_validate_amount_invalid_zero_and_negative(bad):
    v = OperationValidator()
    with pytest.raises(InvalidAmountError):
        v.validate_amount(bad)


def test_validate_amount_nonconvertible_raises():
    v = OperationValidator()
    with pytest.raises(InvalidAmountError):
        v.validate_amount(object())


def test_validate_non_negative_allows_zero_and_rejects_negative():
    v = OperationValidator()
    assert v.validate_non_negative_amount('0') == Decimal('0.00')
    assert v.validate_non_negative_amount(0) == Decimal('0.00')
    with pytest.raises(InvalidAmountError):
        v.validate_non_negative_amount('-0.01')


def test_symbol_support_and_validate_symbol_behaviour():
    # unrestricted validator accepts any non-empty string (case-insensitive normalization)
    v = OperationValidator()
    assert v.is_supported('aapl') is True
    assert v.validate_symbol('aapl') == 'AAPL'

    # invalid inputs
    with pytest.raises(UnsupportedSymbolError):
        v.validate_symbol('')
    with pytest.raises(UnsupportedSymbolError):
        v.validate_symbol(None)

    # restricted set is honored case-insensitively
    v2 = OperationValidator(supported_symbols=['AAPL', 'TsLa'])
    assert v2.supported_symbols() == {'AAPL', 'TSLA'}
    assert v2.is_supported('aapl') is True
    assert v2.is_supported('tsla') is True
    assert v2.is_supported('googl') is False
    with pytest.raises(UnsupportedSymbolError):
        v2.validate_symbol('googl')

    # whitespace does not match normalized set
    assert v2.is_supported(' AAPL ') is False


def test_set_supported_symbols_replaces_and_returns_copy():
    v = OperationValidator(['X'])
    assert v.supported_symbols() == {'X'}

    v.set_supported_symbols(['Y'])
    s = v.supported_symbols()
    assert s == {'Y'}
    # ensure returned set is a copy (mutation should not affect internal state)
    s.add('Z')
    assert v.supported_symbols() == {'Y'}


def test_validate_sufficient_funds_success_and_errors():
    v = OperationValidator()

    # valid: amount gets normalized and compared against balance
    amt = v.validate_sufficient_funds('10.00', '1.234')
    assert amt == Decimal('1.23')

    # insufficient funds
    with pytest.raises(InsufficientFundsError):
        v.validate_sufficient_funds('1.00', '2.00')

    # invalid balance (non-convertible) leads to InsufficientFundsError
    with pytest.raises(InsufficientFundsError):
        v.validate_sufficient_funds('not-a-number', '1.00')


def test_validate_sufficient_quantity_success_and_errors():
    v = OperationValidator()

    # sufficient: quantity normalized to 8 decimal places
    q = v.validate_sufficient_quantity('5', '1.234567891')
    assert q == Decimal('1.23456789')

    # requesting zero or negative quantity raises InvalidAmountError
    with pytest.raises(InvalidAmountError):
        v.validate_sufficient_quantity('5', 0)

    with pytest.raises(InvalidAmountError):
        v.validate_sufficient_quantity('5', '-1')

    # insufficient holdings
    with pytest.raises(InsufficientHoldingsError):
        v.validate_sufficient_quantity('1', '2')

    # invalid holding quantity (non-convertible) raises InsufficientHoldingsError
    with pytest.raises(InsufficientHoldingsError):
        v.validate_sufficient_quantity('not-a-number', '1')


def test_is_supported_non_string_and_none():
    v = OperationValidator()
    assert v.is_supported(123) is False
    assert v.is_supported(None) is False

    v2 = OperationValidator(supported_symbols=['AAPL'])
    assert v2.is_supported('AAPL') is True
    assert v2.is_supported(' aapl ') is False


def test_supported_symbols_returns_copy_or_none():
    v = OperationValidator()
    assert v.supported_symbols() is None

    v2 = OperationValidator(['A', 'B'])
    s = v2.supported_symbols()
    assert s == {'A', 'B'}
    s.remove('A')
    # original remains unchanged
    assert v2.supported_symbols() == {'A', 'B'}