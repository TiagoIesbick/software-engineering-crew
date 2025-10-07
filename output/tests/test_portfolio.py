from decimal import Decimal
import pytest

from output.backend.portfolio import (
    Portfolio,
    PortfolioNotFoundError,
)
from output.backend.holding import (
    Holding,
    InvalidQuantityError,
    InvalidPriceError,
    InsufficientQuantityError,
)


def test_portfolio_init_validations():
    with pytest.raises(ValueError):
        Portfolio(portfolio_id='', owner='owner')
    with pytest.raises(ValueError):
        Portfolio(portfolio_id='pid', owner='')


def test_add_get_list_and_remove_holding_and_type_check():
    p = Portfolio(portfolio_id='p1', owner='alice')

    h = Holding(symbol='AAPL', quantity='1', average_cost='10.00')
    p.add_holding(h)

    # get_holding should return the exact object
    got = p.get_holding('AAPL')
    assert got is h

    # list_holdings should include it
    listed = p.list_holdings()
    assert any(x is h for x in listed)

    # remove_holding removes it
    p.remove_holding('AAPL')
    assert p.get_holding('AAPL') is None

    # removing again raises KeyError
    with pytest.raises(KeyError):
        p.remove_holding('AAPL')

    # add_holding should reject non-Holding types
    with pytest.raises(TypeError):
        p.add_holding({'symbol': 'X'})


def test_buy_creates_holding_and_symbol_normalization_and_quantization():
    p = Portfolio(portfolio_id='p2', owner='bob')
    # buy with whitespace in symbol should be normalized
    h = p.buy('  tsla  ', quantity='2.5', price='3.333')
    # Holding should now exist under normalized symbol
    assert p.get_holding('tsla') is h

    # quantity and average_cost should be quantized appropriately
    assert h.quantity == Decimal('2.5').quantize(Decimal('0.00000001'))
    assert h.average_cost == Decimal('3.33')


def test_buy_updates_average_cost_correctly():
    p = Portfolio(portfolio_id='p3', owner='carol')
    # initial buy
    p.buy('GOOG', quantity='2', price='3.00')
    # buy more to update average cost
    h = p.buy('GOOG', quantity='1', price='4.00')
    assert h.quantity == Decimal('3').quantize(Decimal('0.00000001'))
    # (2*3 + 1*4)/3 = 10/3 -> rounded to cents 3.33
    assert h.average_cost == Decimal('3.33')


def test_buy_invalid_inputs_raise():
    p = Portfolio(portfolio_id='p4', owner='dan')
    with pytest.raises(InvalidQuantityError):
        p.buy('X', quantity=0, price='1.00')
    with pytest.raises(InvalidPriceError):
        p.buy('X', quantity='1', price=0)


def test_sell_reduces_quantity_returns_pnl_and_removes_when_zero():
    p = Portfolio(portfolio_id='p5', owner='erin')
    p.buy('IBM', quantity='5', price='10.00')

    # Sell part of position
    pnl = p.sell('IBM', quantity='2', price='12.345')
    # price quantized to 12.35; pnl = (12.35 - 10.00) * 2 = 4.70
    assert pnl == Decimal('4.70')

    h = p.get_holding('IBM')
    assert h is not None
    assert h.quantity == Decimal('3').quantize(Decimal('0.00000001'))

    # Sell remaining quantity -> position removed
    pnl2 = p.sell('IBM', quantity='3', price='10.00')
    assert pnl2 == Decimal('0.00')
    # holding removed from portfolio
    assert p.get_holding('IBM') is None


def test_sell_nonexistent_raises_portfolio_not_found():
    p = Portfolio(portfolio_id='p6', owner='frank')
    with pytest.raises(PortfolioNotFoundError):
        p.sell('NOPE', quantity='1', price='1.00')


def test_sell_insufficient_quantity_propagates():
    p = Portfolio(portfolio_id='p7', owner='gina')
    p.buy('NFLX', quantity='1.5', price='20.00')
    with pytest.raises(InsufficientQuantityError):
        p.sell('NFLX', quantity='2.0', price='21.00')


def test_market_value_with_mapping_and_callable_and_errors():
    p = Portfolio(portfolio_id='p8', owner='hank')
    p.buy('AAA', quantity='1.23456789', price='0.00')
    p.buy('BBB', quantity='2', price='0.00')

    # Provide mapping price_provider
    prices = {
        'AAA': '2.345',  # will be quantized by Holding.market_value
        'BBB': '1.00',
    }
    mv = p.market_value(prices)
    # compute expected by using Holding.market_value semantics
    expected = (p.get_holding('AAA').market_value('2.345') + p.get_holding('BBB').market_value('1.00')).quantize(Decimal('0.01'))
    assert mv == expected

    # Provide callable price_provider
    def provider(sym):
        return prices[sym]

    mv2 = p.market_value(provider)
    assert mv2 == expected

    # Missing price_provider should raise
    with pytest.raises(ValueError):
        p.market_value(None)

    # Mapping missing a symbol should raise KeyError
    bad_prices = {'AAA': '2.345'}
    with pytest.raises(KeyError):
        p.market_value(bad_prices)


def test_to_dict_and_repr_include_core_fields_and_holdings():
    p = Portfolio(portfolio_id='p9', owner='ivy', account_id='acc-1', currency='EUR')
    p.buy('ORCL', quantity='2', price='1.005')
    d = p.to_dict()
    assert d['portfolio_id'] == 'p9'
    assert d['owner'] == 'ivy'
    assert d['account_id'] == 'acc-1'
    assert d['currency'] == 'EUR'
    assert isinstance(d['holdings'], list)
    assert any(h['symbol'] == 'ORCL' for h in d['holdings'])

    r = repr(p)
    assert 'p9' in r
    assert 'ivy' in r
    # holdings count should appear
    assert 'holdings=' in r