"""
# trading.py

TradingEngine: executes buy/sell orders with validation, updates account cash
and portfolio holdings, and records transactions and realized profit/loss.

This module is intended to be used alongside the other backend modules in
this package (accounts, account_service, portfolio, portfolio_repository,
transaction, transaction_repository, pricing, validators). It is self-
contained in that it only imports from the local package and the standard
library.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any

# Relative imports from package
from .account_service import AccountService
from .portfolio_repository import PortfolioRepository
from .transaction_repository import TransactionRepository
from .pricing import PriceService, UnsupportedSymbolError as PricingUnsupported
from .validators import (
    OperationValidator,
    InsufficientFundsError,
    UnsupportedSymbolError as ValidatorUnsupported,
    InsufficientHoldingsError,
    InvalidAmountError as ValidatorInvalidAmount,
)
from .transaction import Transaction


class TradingError(Exception):
    """Base exception for trading-related errors."""


class TradingEngine:
    """Execute buy and sell orders, update accounts and portfolios, and
    persist transactions.

    The engine is intentionally thin: it wires together an AccountService,
    a PortfolioRepository, a TransactionRepository, a PriceService, and
    an OperationValidator. If callers do not provide these objects sensible
    defaults (in-memory ones) are created.

    Typical usage:
        engine = TradingEngine()
        tx = engine.buy(account_id='acct-1', portfolio_id='p-1', symbol='AAPL', quantity='1', use_market_price=True)

    Methods return the created Transaction object on success.
    """

    def __init__(
        self,
        account_service: Optional[AccountService] = None,
        portfolio_repo: Optional[PortfolioRepository] = None,
        transaction_repo: Optional[TransactionRepository] = None,
        price_service: Optional[PriceService] = None,
        validator: Optional[OperationValidator] = None,
    ) -> None:
        self.account_service = account_service if account_service is not None else AccountService()
        self.portfolio_repo = portfolio_repo if portfolio_repo is not None else PortfolioRepository()
        self.transaction_repo = transaction_repo if transaction_repo is not None else TransactionRepository()
        self.price_service = price_service if price_service is not None else PriceService()
        self.validator = validator if validator is not None else OperationValidator()

    def _resolve_price(self, symbol: str, price: Optional[Any], use_market_price: bool) -> Decimal:
        """Return a Decimal price (already quantized by PriceService or Transaction).

        If use_market_price is True the price is fetched from PriceService.
        Otherwise a provided price must be present.
        """
        if use_market_price:
            try:
                return self.price_service.get_share_price(symbol)
            except Exception as exc:
                # Normalize pricing errors
                raise TradingError(f"failed to obtain market price for {symbol}: {exc}") from exc

        if price is None:
            raise TradingError("price must be provided when use_market_price is False")

        # Let Transaction.trade/_to_decimal handle normalization; just return as-is
        return Decimal(price)

    def buy(
        self,
        account_id: str,
        portfolio_id: str,
        symbol: str,
        quantity: object,
        price: Optional[object] = None,
        use_market_price: bool = False,
        transaction_id: Optional[str] = None,
    ) -> Transaction:
        """Execute a buy: validate funds, withdraw cash, update holdings, record transaction.

        Returns the created Transaction.
        """
        # Validate symbol
        try:
            norm_symbol = self.validator.validate_symbol(symbol)
        except Exception as exc:
            raise TradingError(f"invalid or unsupported symbol: {symbol}") from exc

        # Resolve price (Decimal-like or convertible)
        resolved_price = None
        try:
            resolved_price = self._resolve_price(norm_symbol, price, use_market_price)
        except Exception:
            raise

        # Create a transaction object to determine the required amount and validate quantity/price
        try:
            tx = Transaction.trade(account_id=account_id, side='buy', quantity=quantity, price=resolved_price, transaction_id=transaction_id)
        except Exception as exc:
            raise TradingError(f"invalid trade parameters: {exc}") from exc

        # Validate sufficient funds in account
        try:
            acct = self.account_service.get_account(account_id)
        except Exception as exc:
            raise TradingError(f"account not found: {account_id}") from exc

        try:
            # validate_sufficient_funds will normalize the amount and raise if insufficient
            self.validator.validate_sufficient_funds(acct.get_balance(), tx.amount)
        except InsufficientFundsError as exc:
            raise
        except Exception as exc:
            # Normalize any other validation to TradingError
            raise TradingError(f"funds validation failed: {exc}") from exc

        # Withdraw funds (this will persist via AccountService)
        try:
            self.account_service.withdraw(account_id, tx.amount)
        except Exception as exc:
            # Propagate known account-related exceptions
            raise

        # Update portfolio holdings
        try:
            portfolio = self.portfolio_repo.get(portfolio_id)
            if portfolio is None:
                raise TradingError(f"portfolio not found: {portfolio_id}")
            # portfolio.buy will validate and mutate the holding; it may raise
            portfolio.buy(norm_symbol, quantity, resolved_price)
            # persist portfolio
            self.portfolio_repo.save(portfolio)
        except Exception as exc:
            # If portfolio update fails attempt to refund the withdrawn amount
            try:
                self.account_service.deposit(account_id, tx.amount)
            except Exception:
                raise TradingError("failed to update portfolio and failed to refund account; inconsistent state") from exc
            raise

        # Record transaction (include created transaction object)
        try:
            # We already have tx constructed earlier; ensure transaction amount/price/quantity as stored
            self.transaction_repo.save(tx)
        except Exception as exc:
            # Persistent failure: attempt to roll back portfolio and account
            try:
                # rollback portfolio by selling the same quantity at the same price
                # Note: this may not perfectly restore average_cost but restores quantity
                portfolio.sell(norm_symbol, quantity, resolved_price)
                self.portfolio_repo.save(portfolio)
            except Exception:
                pass
            try:
                self.account_service.deposit(account_id, tx.amount)
            except Exception:
                pass
            raise TradingError(f"failed to persist transaction: {exc}") from exc

        return tx

    def sell(
        self,
        account_id: str,
        portfolio_id: str,
        symbol: str,
        quantity: object,
        price: Optional[object] = None,
        use_market_price: bool = False,
        transaction_id: Optional[str] = None,
    ) -> Transaction:
        """Execute a sell: validate holdings, update holdings (realize P/L), deposit proceeds, record transaction.

        Returns the created Transaction (which includes profit_loss when available).
        """
        # Validate symbol
        try:
            norm_symbol = self.validator.validate_symbol(symbol)
        except Exception as exc:
            raise TradingError(f"invalid or unsupported symbol: {symbol}") from exc

        # Resolve price
        try:
            resolved_price = self._resolve_price(norm_symbol, price, use_market_price)
        except Exception:
            raise

        # Fetch portfolio and ensure holding exists and sufficient
        portfolio = self.portfolio_repo.get(portfolio_id)
        if portfolio is None:
            raise TradingError(f"portfolio not found: {portfolio_id}")

        holding = portfolio.get_holding(norm_symbol)
        if holding is None:
            # Align with validator exception types
            raise InsufficientHoldingsError(f"no holding for symbol: {norm_symbol}")

        # Validate sufficient quantity
        try:
            self.validator.validate_sufficient_quantity(holding.quantity, quantity)
        except Exception as exc:
            raise

        # Perform the sell on the portfolio (this reduces quantity and returns realized pnl)
        try:
            pnl = portfolio.sell(norm_symbol, quantity, resolved_price)
            # persist portfolio
            self.portfolio_repo.save(portfolio)
        except Exception as exc:
            raise

        # Create transaction with realized P/L
        try:
            tx = Transaction.trade(account_id=account_id, side='sell', quantity=quantity, price=resolved_price, profit_loss=pnl, transaction_id=transaction_id)
        except Exception as exc:
            # Attempt to roll back portfolio change by buying back the quantity at the same price
            try:
                portfolio.buy(norm_symbol, quantity, resolved_price)
                self.portfolio_repo.save(portfolio)
            except Exception:
                pass
            raise TradingError(f"failed to construct sell transaction: {exc}") from exc

        # Deposit proceeds to account
        try:
            self.account_service.deposit(account_id, tx.amount)
        except Exception as exc:
            # Attempt to roll back portfolio change
            try:
                portfolio.buy(norm_symbol, quantity, resolved_price)
                self.portfolio_repo.save(portfolio)
            except Exception:
                raise TradingError("failed to deposit proceeds and rollback failed; inconsistent state") from exc
            raise

        # Persist transaction
        try:
            self.transaction_repo.save(tx)
        except Exception as exc:
            # best-effort: attempt rollback (withdraw proceeds and buy back holdings)
            try:
                self.account_service.withdraw(account_id, tx.amount)
            except Exception:
                pass
            try:
                portfolio.buy(norm_symbol, quantity, resolved_price)
                self.portfolio_repo.save(portfolio)
            except Exception:
                pass
            raise TradingError(f"failed to persist transaction: {exc}") from exc

        return tx

    def list_transactions_for_account(self, account_id: str):
        """Return transactions referencing the given account id."""
        return self.transaction_repo.list_for_account(account_id)

    def get_portfolio_holdings(self, portfolio_id: str):
        """Return holdings list for the given portfolio id."""
        p = self.portfolio_repo.get(portfolio_id)
        if p is None:
            raise TradingError(f"portfolio not found: {portfolio_id}")
        return p.list_holdings()


__all__ = ['TradingEngine', 'TradingError']