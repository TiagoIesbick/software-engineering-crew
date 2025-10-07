from decimal import Decimal
import pytest

from output.backend.holding import (
    Holding,
    InvalidQuantityError,
    InvalidPriceError,
    InsufficientQuantityError,
)


def test_post_init_normalizes_quantity_and_average_cost():
    # quantity should be quantized to 8 decimal places and average_cost to cents
    h = Holding(symbol='AAPL', quantity='1.234567891', average_cost='10.125')
    assert h.symbol == 'AAPL'
    assert h.quantity == Decimal('1.23456789')
    assert h.average_cost == Decimal('10.13')


def test_empty_symbol_raises_value_error():
    with pytest.raises(ValueError):
        Holding(symbol='')


def test_buy_from_zero_sets_average_cost_and_quantity():
    h = Holding(symbol='TSLA')
    new_qty = h.buy(quantity='2.5', price='3.333')
    # price quantized to cents -> 3.33
    assert new_qty == Decimal('2.5').quantize(Decimal('0.00000001'))
    assert h.quantity == Decimal('2.5').quantize(Decimal('0.00000001'))
    assert h.average_cost == Decimal('3.33')


def test_buy_updates_average_cost_correctly():
    # Start with existing position
    h = Holding(symbol='GOOG', quantity='2', average_cost='3.00')
    # Buy 1 at 4.00 -> new_avg = (2*3 + 1*4)/3 = 10/3 -> quantized to cents
    h.buy(quantity='1', price='4.00')
    assert h.quantity == Decimal('3').quantize(Decimal('0.00000001'))
    assert h.average_cost == Decimal('3.33')


@pytest.mark.parametrize("bad_qty", [0, '0', '-1', -1])
def test_buy_invalid_quantities_raise(bad_qty):
    h = Holding(symbol='X')
    with pytest.raises(InvalidQuantityError):
        h.buy(quantity=bad_qty, price='1.00')


@pytest.mark.parametrize("bad_price", [0, '0', '-2', -2])
def test_buy_invalid_prices_raise(bad_price):
    h = Holding(symbol='X')
    with pytest.raises(InvalidPriceError):
        h.buy(quantity='1', price=bad_price)


def test_sell_reduces_quantity_and_returns_realized_pnl():
    # Setup a holding with explicit average cost
    h = Holding(symbol='IBM', quantity='5', average_cost='10.00')
    # Sell 2 at 12.345 -> price quantized to 12.35; pnl = (12.35 - 10.00)*2 = 4.70
    pnl = h.sell(quantity='2', price='12.345')
    assert pnl == Decimal('4.70')
    assert h.quantity == Decimal('3').quantize(Decimal('0.00000001'))
    # average_cost remains unchanged when some quantity remains
    assert h.average_cost == Decimal('10.00')


def test_sell_more_than_available_raises_insufficient_quantity():
    h = Holding(symbol='NFLX', quantity='1.5', average_cost='20.00')
    with pytest.raises(InsufficientQuantityError):
        h.sell(quantity='2.0', price='21.00')


def test_sell_full_position_resets_average_cost():
    h = Holding(symbol='MSFT', quantity='3', average_cost='5.00')
    pnl = h.sell(quantity='3', price='5.50')
    # pnl = (5.50 - 5.00)*3 = 1.50
    assert pnl == Decimal('1.50')
    assert h.quantity == Decimal('0').quantize(Decimal('0.00000001'))
    assert h.average_cost == Decimal('0.00')


def test_sell_invalid_quantity_or_price_raise():
    h = Holding(symbol='BABA', quantity='1', average_cost='10')
    with pytest.raises(InvalidQuantityError):
        h.sell(quantity='0', price='1.00')
    with pytest.raises(InvalidPriceError):
        h.sell(quantity='0.5', price='0')


def test_market_value_is_quantity_times_price_and_quantized():
    h = Holding(symbol='AMZN', quantity='1.23456789', average_cost='0.00')
    mv = h.market_value(price='2.345')
    # price -> 2.35, mv = 1.23456789 * 2.35 quantized to cents
    expected = (Decimal('1.23456789') * Decimal('2.35')).quantize(Decimal('0.01'))
    assert mv == expected


def test_to_dict_and_repr_include_core_fields():
    h = Holding(symbol='ORCL', quantity='2.000000004', average_cost='1.005', currency='EUR')
    d = h.to_dict()
    # quantity quantized to 8 dp, average cost to cents
    assert d['symbol'] == 'ORCL'
    assert d['quantity'] == format(h.quantity, 'f')
    assert d['average_cost'] == format(h.average_cost, 'f')
    assert d['currency'] == 'EUR'

    r = repr(h)
    assert 'ORCL' in r
    assert format(h.quantity, 'f') in r
    assert format(h.average_cost, 'f') in r