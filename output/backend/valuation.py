"""
# valuation.py

Provides ValuationEngine for computing portfolio market value and profit & loss
(realized and unrealized) using holdings and a PriceService.

This module is self-contained and uses only the Python standard library. It is
written to be resilient to a few different kinds of inputs for holdings and
transactions (object-like or mapping-like). Monetary results are returned as
Decimal quantized to cents.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext, InvalidOperation
from typing import Optional, Iterable, Any, Dict, List

# Ensure sufficient precision for monetary calculations
getcontext().prec = 28

_CENT = Decimal('0.01')


class ValuationError(Exception):
    """Base exception for valuation related errors."""


class ValuationEngine:
    """Compute market values and profit/loss for portfolios/holdings.

    The engine can be constructed with an optional price_service which must
    provide a get_share_price(symbol: str) -> Decimal method. If no
    price_service is provided callers must supply explicit prices via the
    methods that require them.

    Methods are tolerant of inputs in several forms:
      - portfolio-like object with a list_holdings() method returning Holding objects
      - an iterable of Holding objects
      - a mapping/dict with a 'holdings' key containing an iterable of holdings

    Transaction inputs for realized P/L calculations may be a list of
    Transaction objects (with .profit_loss) or mapping-like with a
    'profit_loss' key. Profit/loss values are normalized to Decimal cents
    when present and non-null.
    """

    def __init__(self, price_service: Optional[Any] = None) -> None:
        """Create a ValuationEngine.

        price_service: optional object exposing get_share_price(symbol) -> Decimal
        """
        self.price_service = price_service

    # --- Helpers -------------------------------------------------
    @staticmethod
    def _to_decimal_cents(value) -> Decimal:
        """Convert value to Decimal quantized to cents. Raises ValuationError on failure."""
        try:
            dec = Decimal(value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValuationError(f"invalid monetary value: {value!r}") from exc
        return dec.quantize(_CENT, rounding=ROUND_HALF_UP)

    def _get_price_for_symbol(self, symbol: str) -> Decimal:
        """Obtain price for symbol via the configured price_service.

        Raises ValuationError if no price_service is available or if the
        price_service raises.
        """
        if self.price_service is None:
            raise ValuationError("no price_service configured; explicit price required")
        try:
            price = self.price_service.get_share_price(symbol)
        except Exception as exc:
            raise ValuationError(f"failed to obtain price for {symbol}: {exc}") from exc
        # Ensure result is Decimal quantized to cents
        return self._to_decimal_cents(price)

    @staticmethod
    def _extract_holdings(obj: Any) -> Iterable[Any]:
        """Extract an iterable of holdings from various container shapes.

        A holding is expected to have attributes: symbol, quantity, average_cost
        or mapping keys with same names. This function returns the iterable of
        holding-like objects.
        """
        # Portfolio-like with list_holdings
        try:
            if hasattr(obj, 'list_holdings') and callable(getattr(obj, 'list_holdings')):
                return obj.list_holdings()
        except Exception:
            pass

        # Mapping-like with 'holdings' key
        try:
            if isinstance(obj, dict) and 'holdings' in obj:
                return obj['holdings']
        except Exception:
            pass

        # If it's already an iterable (list/tuple/generator) we assume holdings
        if isinstance(obj, Iterable):
            return obj  # type: ignore

        # As a last resort, attempt to read attribute _holdings (internal mapping)
        try:
            val = getattr(obj, '_holdings')
            if isinstance(val, dict):
                return list(val.values())
            return val
        except Exception:
            pass

        raise ValuationError('unable to extract holdings from provided object')

    # --- Valuation computations -------------------------------
    def holding_market_value(self, holding: Any, price: Optional[Any] = None) -> Decimal:
        """Compute market value of a single holding: quantity * price.

        price: optional explicit price. If omitted price will be fetched from
        the configured price_service.
        """
        # Resolve fields on the holding (support attribute or mapping)
        try:
            sym = holding.symbol if hasattr(holding, 'symbol') else holding.get('symbol')
        except Exception:
            raise ValuationError('holding missing symbol')
        if not isinstance(sym, str) or not sym:
            raise ValuationError('holding has invalid symbol')

        # quantity
        try:
            qty = getattr(holding, 'quantity', None) if hasattr(holding, 'quantity') else holding.get('quantity')
        except Exception:
            qty = None
        if qty is None:
            raise ValuationError(f'holding {sym!r} missing quantity')

        # Resolve price
        if price is None:
            price_dec = self._get_price_for_symbol(sym)
        else:
            price_dec = self._to_decimal_cents(price)

        # Normalize quantity to Decimal (it may already be Decimal with more precision)
        try:
            qty_dec = Decimal(qty)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValuationError(f'invalid quantity for {sym!r}: {qty!r}') from exc

        mv = (qty_dec * price_dec).quantize(_CENT, rounding=ROUND_HALF_UP)
        return mv

    def holding_unrealized_pl(self, holding: Any, price: Optional[Any] = None) -> Decimal:
        """Compute unrealized P/L for a single holding: (market_price - average_cost) * quantity."""
        # read symbol
        try:
            sym = holding.symbol if hasattr(holding, 'symbol') else holding.get('symbol')
        except Exception:
            raise ValuationError('holding missing symbol')
        if not isinstance(sym, str) or not sym:
            raise ValuationError('holding has invalid symbol')

        # quantity and average_cost retrieval
        try:
            qty = getattr(holding, 'quantity', None) if hasattr(holding, 'quantity') else holding.get('quantity')
        except Exception:
            qty = None
        if qty is None:
            raise ValuationError(f'holding {sym!r} missing quantity')

        try:
            avg = getattr(holding, 'average_cost', None) if hasattr(holding, 'average_cost') else holding.get('average_cost')
        except Exception:
            avg = None
        if avg is None:
            raise ValuationError(f'holding {sym!r} missing average_cost')

        # Resolve price
        if price is None:
            price_dec = self._get_price_for_symbol(sym)
        else:
            price_dec = self._to_decimal_cents(price)

        # Convert qty and avg to Decimal
        try:
            qty_dec = Decimal(qty)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValuationError(f'invalid quantity for {sym!r}: {qty!r}') from exc
        try:
            avg_dec = Decimal(avg)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValuationError(f'invalid average_cost for {sym!r}: {avg!r}') from exc

        unreal = ((price_dec - avg_dec) * qty_dec).quantize(_CENT, rounding=ROUND_HALF_UP)
        return unreal

    def portfolio_market_value(self, portfolio_or_holdings: Any, price_overrides: Optional[Dict[str, Any]] = None) -> Decimal:
        """Compute total market value for a portfolio or iterable of holdings.

        price_overrides: optional mapping of symbol -> explicit price to use
        instead of price_service for specific symbols.
        """
        price_overrides = dict(price_overrides or {})
        total = Decimal('0.00')
        holdings = self._extract_holdings(portfolio_or_holdings)
        for h in holdings:
            # determine override for symbol
            sym = h.symbol if hasattr(h, 'symbol') else h.get('symbol')
            override = price_overrides.get(sym)
            mv = self.holding_market_value(h, price=override)
            total += mv
        return total.quantize(_CENT, rounding=ROUND_HALF_UP)

    def portfolio_unrealized_pl(self, portfolio_or_holdings: Any, price_overrides: Optional[Dict[str, Any]] = None) -> Decimal:
        """Compute aggregate unrealized P/L for a portfolio or holdings iterable."""
        price_overrides = dict(price_overrides or {})
        total = Decimal('0.00')
        holdings = self._extract_holdings(portfolio_or_holdings)
        for h in holdings:
            sym = h.symbol if hasattr(h, 'symbol') else h.get('symbol')
            override = price_overrides.get(sym)
            upl = self.holding_unrealized_pl(h, price=override)
            total += upl
        return total.quantize(_CENT, rounding=ROUND_HALF_UP)

    def realized_pl_from_transactions(self, transactions: Iterable[Any]) -> Decimal:
        """Sum realized profit/loss from a sequence of transactions.

        Transactions may be objects with .profit_loss attribute or mapping-like
        with key 'profit_loss'. Values that are None are ignored.
        """
        total = Decimal('0.00')
        for tx in transactions:
            # attempt to get profit_loss
            try:
                pl = getattr(tx, 'profit_loss', None) if hasattr(tx, 'profit_loss') else tx.get('profit_loss')
            except Exception:
                pl = None
            if pl is None:
                continue
            # normalize to Decimal cents
            pl_dec = self._to_decimal_cents(pl)
            total += pl_dec
        return total.quantize(_CENT, rounding=ROUND_HALF_UP)

    def portfolio_breakdown(self, portfolio_or_holdings: Any, price_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return a per-holding valuation breakdown and aggregates.

        The returned dict includes per-holding entries with symbol, quantity,
        average_cost, market_price, market_value, unrealized_pl and top-level
        aggregates: total_market_value and total_unrealized_pl.
        """
        price_overrides = dict(price_overrides or {})
        holdings = list(self._extract_holdings(portfolio_or_holdings))
        rows: List[Dict[str, Any]] = []
        total_mv = Decimal('0.00')
        total_upl = Decimal('0.00')

        for h in holdings:
            sym = h.symbol if hasattr(h, 'symbol') else h.get('symbol')
            qty = getattr(h, 'quantity', None) if hasattr(h, 'quantity') else h.get('quantity')
            avg = getattr(h, 'average_cost', None) if hasattr(h, 'average_cost') else h.get('average_cost')
            override = price_overrides.get(sym)
            try:
                price = self._get_price_for_symbol(sym) if override is None else self._to_decimal_cents(override)
            except ValuationError:
                # If price is missing mark as None and skip calculations
                price = None

            if price is not None:
                mv = self.holding_market_value(h, price=price)
                upl = self.holding_unrealized_pl(h, price=price)
            else:
                mv = None
                upl = None

            # Normalize values to strings for safe serialization, keep Decimal for mv/upl
            rows.append({
                'symbol': sym,
                'quantity': format(Decimal(qty), 'f'),
                'average_cost': format(Decimal(avg), 'f') if avg is not None else None,
                'market_price': format(price, 'f') if price is not None else None,
                'market_value': format(mv, 'f') if mv is not None else None,
                'unrealized_pl': format(upl, 'f') if upl is not None else None,
            })

            if mv is not None:
                total_mv += mv
            if upl is not None:
                total_upl += upl

        return {
            'holdings': rows,
            'total_market_value': format(total_mv.quantize(_CENT, rounding=ROUND_HALF_UP), 'f'),
            'total_unrealized_pl': format(total_upl.quantize(_CENT, rounding=ROUND_HALF_UP), 'f'),
        }


__all__ = ['ValuationEngine', 'ValuationError']

# If executed directly, print a brief usage example (not for importers)
if __name__ == '__main__':
    print('ValuationEngine module: provides valuation utilities for portfolios')