"""\"\"\"pricing.py

Provides PriceService which supplies deterministic test share prices for a
small set of supported symbols. The service is intentionally minimal and
self-contained, using only the Python standard library.

Usage:
    svc = PriceService()
    price = svc.get_share_price('AAPL')  # returns Decimal quantized to cents

Supported symbols (case-insensitive): AAPL, TSLA, GOOGL
\"\"\"\

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Dict

# Ensure enough precision for monetary arithmetic
getcontext().prec = 28

_CENT = Decimal('0.01')


class PriceServiceError(Exception):
    """Base exception for PriceService-related errors."""


class UnsupportedSymbolError(PriceServiceError, KeyError):
    """Raised when a requested symbol is not supported by the service."""


class PriceService:
    """Simple deterministic price provider for a small set of test symbols.

    The service returns Decimal prices quantized to two decimal places
    (cents) and treats symbol lookup case-insensitively. Only the following
    symbols are supported:
      - AAPL
      - TSLA
      - GOOGL

    This is intended for tests and simple examples, not for production use.
    """

    # Canonical price map (symbol -> Decimal price)
    _PRICES: Dict[str, Decimal] = {
        'AAPL': Decimal('150.00'),
        'TSLA': Decimal('720.50'),
        'GOOGL': Decimal('2800.75'),
    }

    def __init__(self) -> None:
        # normalize stored prices to be quantized to cents
        self._prices: Dict[str, Decimal] = {}
        for sym, p in self._PRICES.items():
            # Ensure each price is a Decimal rounded to cents
            self._prices[sym.upper()] = (Decimal(p).quantize(_CENT, rounding=ROUND_HALF_UP))

    def supported_symbols(self) -> Dict[str, Decimal]:
        """Return a shallow copy of supported symbols mapped to their prices.

        Keys are uppercased symbol strings.
        """
        return dict(self._prices)

    def is_supported(self, symbol: str) -> bool:
        """Return True if the symbol is supported (case-insensitive)."""
        if not isinstance(symbol, str):
            return False
        return symbol.upper() in self._prices

    def get_share_price(self, symbol: str) -> Decimal:
        """Return the share price for the given symbol as a Decimal.

        The symbol lookup is case-insensitive. If the symbol is not
        supported an UnsupportedSymbolError is raised.
        The returned Decimal is quantized to two decimal places.
        """
        if not isinstance(symbol, str) or not symbol:
            raise UnsupportedSymbolError(f"invalid symbol: {symbol!r}")

        up = symbol.upper()
        try:
            price = self._prices[up]
        except KeyError as exc:
            raise UnsupportedSymbolError(f"symbol not supported: {symbol!r}") from exc

        # Return a copy (Decimal is immutable but this clarifies intent)
        return Decimal(price)


__all__ = ['PriceService', 'UnsupportedSymbolError', 'PriceServiceError']"""