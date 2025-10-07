from decimal import Decimal
import pytest

from output.backend.valuation import ValuationEngine, ValuationError


class SimpleHolding:
    def __init__(self, symbol: str, quantity, average_cost):
        self.symbol = symbol
        self.quantity = quantity
        self.average_cost = average_cost


class PortfolioLike:
    def __init__(self, holdings):
        self._holdings = {h.symbol: h for h in holdings}

    def list_holdings(self):
        return list(self._holdings.values())


class FakePriceService:
    def __init__(self, price_map):
        # price_map: symbol -> Decimal or convertible
        self._map = {k.upper(): v for k, v in price_map.items()}

    def get_share_price(self, symbol: str):
        return self._map[symbol.upper()]


def test_holding_market_value_with_explicit_price_and_mapping_holding():
    # mapping-like holding
    holding = {"symbol": "A", "quantity": "2.345", "average_cost": "1.00"}
    ve = ValuationEngine()
    # explicit price string '3.333' -> quantized to 3.33
    mv = ve.holding_market_value(holding, price="3.333")
    # 2.345 * 3.33 = 7.80885 -> rounded to 7.81
    assert mv == Decimal("7.81")


def test_holding_market_value_with_price_service_and_object_holding():
    # object-like holding
    holding = SimpleHolding(symbol="B", quantity=Decimal("1.5"), average_cost="5.00")
    ps = FakePriceService({"B": Decimal("10.125")})  # will be quantized to 10.13
    ve = ValuationEngine(price_service=ps)
    mv = ve.holding_market_value(holding)  # uses price service
    # price -> 10.13; 1.5 * 10.13 = 15.195 -> 15.20
    assert mv == Decimal("15.20")


def test_holding_unrealized_pl_with_override_and_price_service():
    holding = SimpleHolding(symbol="C", quantity="3", average_cost="5.00")
    ve_no_ps = ValuationEngine()
    # explicit price 6.00 -> (6 - 5) * 3 = 3.00
    upl = ve_no_ps.holding_unrealized_pl(holding, price="6.00")
    assert upl == Decimal("3.00")

    # using price service returning 6.004 -> quantize to 6.00
    ps = FakePriceService({"C": "6.004"})
    ve = ValuationEngine(price_service=ps)
    upl2 = ve.holding_unrealized_pl(holding)
    assert upl2 == Decimal("3.00")


def test_portfolio_market_value_with_various_input_shapes_and_overrides():
    h1 = SimpleHolding(symbol="X", quantity="1.5", average_cost="2.00")
    h2 = {"symbol": "Y", "quantity": Decimal("2"), "average_cost": "1.00"}

    ve = ValuationEngine()
    # Provide overrides for both symbols
    overrides = {"X": "3.333", "Y": "4.00"}
    total = ve.portfolio_market_value([h1, h2], price_overrides=overrides)
    # h1: 1.5 * 3.33 = 4.995 -> 5.00 ; h2: 2 * 4.00 = 8.00 ; total = 13.00
    assert total == Decimal("13.00")

    # Now test portfolio-like object (list_holdings)
    p = PortfolioLike([h1, SimpleHolding(symbol="Y", quantity="2", average_cost="1.00")])
    total2 = ve.portfolio_market_value(p, price_overrides=overrides)
    assert total2 == Decimal("13.00")

    # And mapping with 'holdings' key
    mapped = {"holdings": [h1, h2]}
    total3 = ve.portfolio_market_value(mapped, price_overrides=overrides)
    assert total3 == Decimal("13.00")


def test_portfolio_unrealized_pl_sums_each_holding():
    h1 = SimpleHolding(symbol="A", quantity="2", average_cost="5.00")
    h2 = SimpleHolding(symbol="B", quantity="3", average_cost="1.00")
    ve = ValuationEngine()
    overrides = {"A": "6.00", "B": "1.50"}
    # A: (6-5)*2 = 2.00 ; B: (1.5-1)*3 = 1.50 ; total = 3.50
    upl = ve.portfolio_unrealized_pl([h1, h2], price_overrides=overrides)
    assert upl == Decimal("3.50")


def test_realized_pl_from_transactions_mixes_obj_and_mapping_and_ignores_none():
    class TxObj:
        def __init__(self, pl):
            self.profit_loss = pl

    txs = [
        TxObj(Decimal("1.234")),      # -> 1.23
        {"profit_loss": "2.345"},     # -> 2.35
        {"profit_loss": None},        # ignored
        TxObj(None),                  # ignored
    ]
    ve = ValuationEngine()
    total = ve.realized_pl_from_transactions(txs)
    # 1.23 + 2.35 = 3.58
    assert total == Decimal("3.58")


def test_realized_pl_from_transactions_invalid_value_raises():
    txs = [{"profit_loss": "not-a-number"}]
    ve = ValuationEngine()
    with pytest.raises(ValuationError):
        ve.realized_pl_from_transactions(txs)


def test_portfolio_breakdown_includes_prices_and_aggregates_and_handles_missing_price():
    # Holding with known price via overrides and one without price (no price_service)
    h1 = SimpleHolding(symbol="S1", quantity="1.23456789", average_cost="2.00")
    h2 = SimpleHolding(symbol="S2", quantity="2", average_cost="1.00")

    ve = ValuationEngine()  # no price service configured
    # Provide override only for S1
    breakdown = ve.portfolio_breakdown([h1, h2], price_overrides={"S1": "3.333"})
    # S1: price 3.33 -> market_value = 1.23456789 * 3.33 quantized
    expected_s1_mv = (Decimal("1.23456789") * Decimal("3.33")).quantize(Decimal("0.01"))
    # S2 has no price -> market_price and market_value should be None in breakdown
    rows = {r["symbol"]: r for r in breakdown["holdings"]}
    assert rows["S1"]["market_price"] == format(ve._to_decimal_cents("3.333"), "f")
    assert rows["S1"]["market_value"] == format(expected_s1_mv, "f")
    assert rows["S2"]["market_price"] is None
    assert rows["S2"]["market_value"] is None

    # Totals should account only for S1
    assert breakdown["total_market_value"] == format(expected_s1_mv, "f")
    # total_unrealized_pl present as string (may be 0.00)
    assert isinstance(breakdown["total_unrealized_pl"], str)


def test_holding_market_value_errors_for_invalid_inputs():
    ve = ValuationEngine()
    # Missing symbol
    bad_holding1 = {"quantity": "1", "average_cost": "1.00"}
    with pytest.raises(ValuationError):
        ve.holding_market_value(bad_holding1, price="1.00")

    # Missing quantity
    bad_holding2 = {"symbol": "Z", "average_cost": "1.00"}
    with pytest.raises(ValuationError):
        ve.holding_market_value(bad_holding2, price="1.00")

    # Non-iterable / unextractable holdings for portfolio methods
    with pytest.raises(ValuationError):
        ve.portfolio_market_value(12345, price_overrides={})


def test_get_price_for_symbol_raises_when_no_price_service_and_no_override():
    ve = ValuationEngine()  # no price service
    h = SimpleHolding(symbol="NOPS", quantity="1", average_cost="1.00")
    with pytest.raises(ValuationError):
        # calling holding_market_value without price and without a price service should raise
        ve.holding_market_value(h)