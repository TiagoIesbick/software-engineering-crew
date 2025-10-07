# portfolio.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, getcontext
from threading import RLock
from typing import Dict, Optional, Callable, Iterable, List

# Relative import to reuse the Holding implementation
from .holding import (
    Holding,
    HoldingError,
    InvalidQuantityError,
    InvalidPriceError,
    InsufficientQuantityError,
)

# Ensure sufficient precision
getcontext().prec = 28

_CENT = Decimal('0.01')


class PortfolioError(Exception):
    """Base class for portfolio-related errors."""

class PortfolioNotFoundError(PortfolioError, KeyError):
    """Raised when a requested holding is not found."""


@dataclass
class Portfolio:
    """Tracks holdings for an account and updates positions/cost basis on trades.

    Attributes:
        portfolio_id: unique portfolio identifier (string)
        owner: owner identifier (string)
        account_id: optional linked account id
        currency: informational currency code (defaults to 'USD')
        holdings: mapping of symbol -> Holding objects
    """

    portfolio_id: str
    owner: str
    account_id: Optional[str] = None
    currency: str = 'USD'

    # internal holdings map and lock for thread-safety
    _holdings: Dict[str, Holding] = field(default_factory=dict, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio_id, str) or not self.portfolio_id:
            raise ValueError('portfolio_id must be a non-empty string')
        if not isinstance(self.owner, str) or not self.owner:
            raise ValueError('owner must be a non-empty string')

    # --- Holdings management ---------------------------------------
    def _normalize_symbol(self, symbol: str) -> str:
        if not isinstance(symbol, str) or not symbol:
            raise ValueError('symbol must be a non-empty string')
        return symbol.strip()

    def add_holding(self, holding: Holding) -> None:
        """Add or replace a Holding in the portfolio.

        The holding's symbol is used as the key. Replaces any existing holding
        with the same symbol.
        """
        if not isinstance(holding, Holding):
            raise TypeError('holding must be a Holding instance')
        sym = self._normalize_symbol(holding.symbol)
        with self._lock:
            self._holdings[sym] = holding

    def get_holding(self, symbol: str) -> Optional[Holding]:
        """Return the Holding for symbol or None if not present."""
        sym = self._normalize_symbol(symbol)
        with self._lock:
            return self._holdings.get(sym)

    def list_holdings(self) -> List[Holding]:
        """Return a list of holdings (a shallow copy)."""
        with self._lock:
            return list(self._holdings.values())

    def remove_holding(self, symbol: str) -> None:
        """Remove a holding by symbol. Raises KeyError if missing."""
        sym = self._normalize_symbol(symbol)
        with self._lock:
            if sym in self._holdings:
                del self._holdings[sym]
            else:
                raise KeyError(sym)

    # --- Trading operations ---------------------------------------
    def buy(self, symbol: str, quantity: object, price: object) -> Holding:
        """Buy quantity of symbol at price.

        Creates a new Holding if none exists. Returns the Holding after the
        purchase. Raises Holding-related exceptions on invalid inputs.
        """
        sym = self._normalize_symbol(symbol)
        with self._lock:
            holding = self._holdings.get(sym)
            if holding is None:
                # Create a new holding with zero quantity and zero average_cost
                holding = Holding(symbol=sym, quantity=Decimal('0'), average_cost=Decimal('0.00'), currency=self.currency)
                self._holdings[sym] = holding
            # Delegate validation and state change to Holding.buy
            holding.buy(quantity=quantity, price=price)
            return holding

    def sell(self, symbol: str, quantity: object, price: object) -> Decimal:
        """Sell quantity of symbol at price.

        Returns realized P/L as Decimal (quantized to cents). If the sale
        reduces the holding to zero quantity the holding is removed from the
        portfolio. Raises Holding-related exceptions on invalid inputs.
        """
        sym = self._normalize_symbol(symbol)
        with self._lock:
            holding = self._holdings.get(sym)
            if holding is None:
                raise PortfolioNotFoundError(f'no holding for symbol: {sym}')
            pnl = holding.sell(quantity=quantity, price=price)
            # Remove if fully closed
            if holding.quantity == Decimal('0').quantize(Decimal('0.00000001')):
                del self._holdings[sym]
            return pnl

    # --- Valuation & utilities ------------------------------------
    def market_value(self, price_provider: Optional[object] = None) -> Decimal:
        """Compute total market value of the portfolio.

        price_provider can be:
          - None: raises ValueError (price information required)
          - mapping (dict-like): must provide price_provider[symbol]
          - callable: called as price_provider(symbol) -> price

        Each holding's Holding.market_value is used so price inputs are
        normalized consistently. The returned total is quantized to cents.
        """
        if price_provider is None:
            raise ValueError('price_provider is required to compute market value')

        total = Decimal('0.00')
        with self._lock:
            for sym, holding in self._holdings.items():
                # obtain price
                if callable(price_provider):
                    price = price_provider(sym)
                else:
                    try:
                        price = price_provider[sym]
                    except Exception as exc:
                        raise KeyError(f'price for {sym} not available') from exc
                mv = holding.market_value(price)
                total += mv
        return total.quantize(_CENT, rounding=ROUND_HALF_UP)

    def to_dict(self) -> Dict[str, object]:
        """Serialize portfolio core fields and holdings to a dict."""
        with self._lock:
            holdings_list = [h.to_dict() for h in self._holdings.values()]
        return {
            'portfolio_id': self.portfolio_id,
            'owner': self.owner,
            'account_id': self.account_id,
            'currency': self.currency,
            'holdings': holdings_list,
        }

    def __repr__(self) -> str:
        with self._lock:
            count = len(self._holdings)
        return (f"Portfolio(portfolio_id={self.portfolio_id!r}, owner={self.owner!r}, holdings={count}, currency={self.currency!r})")


__all__ = [
    'Portfolio',
    'PortfolioError',
    'PortfolioNotFoundError',
]