"""\"\"\"reporting.py

ReportingService: compose account, portfolio, transaction and valuation data
into a consolidated account report.

This module is intentionally lightweight and makes use of other package
components when available. To remain flexible for tests and different
running contexts the service accepts injected dependencies (account
service, portfolio/transaction repositories, valuation engine, history
service, price service). When not provided it will attempt to instantiate
sensible defaults from nearby modules in the same package.

Only the Python standard library is used by this file.
\"\"\"

from __future__ import annotations

from typing import Optional, Any, Dict, List, Iterable
from decimal import Decimal
import datetime


class ReportingError(Exception):
    """Base exception for reporting-related errors."""


class ReportingService:
    """Generate summary reports combining holdings, valuation, and P/L for an account.

    The service is a thin composition layer. It tries to be forgiving when
    optional dependencies are unavailable but will raise ReportingError for
    unrecoverable situations (for example missing account service when an
    account lookup is requested).
    
    Constructor arguments may include:
      - account_service: provides get_account(account_id) -> Account
      - portfolio_repo: provides get(portfolio_id) -> Portfolio-like
      - transaction_repo: provides list_for_account(account_id) -> iterable of transactions
      - valuation_engine: provides valuation utilities (portfolio_breakdown, realized_pl_from_transactions)
      - history_service: provides list_transactions_for_account(account_id) and holdings_snapshot(portfolio_id)
      - price_service: optional price provider (used when instantiating valuation engine)
    """

    def __init__(
        self,
        account_service: Optional[object] = None,
        portfolio_repo: Optional[object] = None,
        transaction_repo: Optional[object] = None,
        valuation_engine: Optional[object] = None,
        history_service: Optional[object] = None,
        price_service: Optional[object] = None,
    ) -> None:
        # Prefer explicitly provided collaborators
        self.account_service = account_service
        self.portfolio_repo = portfolio_repo
        self.transaction_repo = transaction_repo
        self._valuation = valuation_engine
        self.history_service = history_service
        self.price_service = price_service

        # Lazily import defaults from the sibling package modules if needed.
        # Importing is done here to avoid import-time errors in isolation.
        if self.account_service is None:
            try:
                from .account_service import AccountService

                self.account_service = AccountService()
            except Exception:
                self.account_service = None

        if self.portfolio_repo is None:
            try:
                from .portfolio_repository import PortfolioRepository

                self.portfolio_repo = PortfolioRepository()
            except Exception:
                self.portfolio_repo = None

        if self.transaction_repo is None:
            try:
                from .transaction_repository import TransactionRepository

                self.transaction_repo = TransactionRepository()
            except Exception:
                self.transaction_repo = None

        if self.history_service is None:
            try:
                from .history import HistoryService

                # If transaction_repo/portfolio_repo were injected, pass them into HistoryService
                self.history_service = HistoryService(transaction_repo=self.transaction_repo, portfolio_repo=self.portfolio_repo)
            except Exception:
                self.history_service = None

        if self._valuation is None:
            try:
                from .valuation import ValuationEngine

                # if a price service was injected or available try to wire it in
                ps = self.price_service
                if ps is None:
                    try:
                        from .pricing import PriceService

                        ps = PriceService()
                    except Exception:
                        ps = None
                self._valuation = ValuationEngine(price_service=ps)
            except Exception:
                self._valuation = None

    # --- Internal helpers -------------------------------------------------
    @staticmethod
    def _format_decimal(d: Optional[Decimal]) -> Optional[str]:
        if d is None:
            return None
        return format(d, 'f')

    @staticmethod
    def _normalize_tx_to_dict(tx: Any) -> Dict[str, Any]:
        """Lightweight normalization of a transaction-like object to a dict.

        This intentionally mirrors a subset of behavior from HistoryService
        to avoid depending on it being present.
        """
        # If it's already a mapping-like dict, return a shallow copy
        try:
            if isinstance(tx, dict):
                return dict(tx)
        except Exception:
            pass

        # If the object provides to_dict, prefer that
        try:
            if hasattr(tx, 'to_dict') and callable(getattr(tx, 'to_dict')):
                return tx.to_dict()  # type: ignore[call-arg]
        except Exception:
            pass

        out: Dict[str, Any] = {}
        for name in ('transaction_id', 'kind', 'account_id', 'from_account', 'to_account', 'quantity', 'price', 'amount', 'profit_loss', 'created_at', 'executed_at', 'metadata'):
            try:
                val = getattr(tx, name)
            except Exception:
                try:
                    val = tx[name]  # type: ignore[index]
                except Exception:
                    val = None
            if val is not None:
                out[name] = val
        if not out:
            out['repr'] = repr(tx)
        return out

    @staticmethod
    def _normalize_holding_to_dict(h: Any) -> Dict[str, Any]:
        """Normalize a holding-like object to a dict with the core fields."""
        try:
            if isinstance(h, dict):
                return dict(h)
        except Exception:
            pass

        try:
            if hasattr(h, 'to_dict') and callable(getattr(h, 'to_dict')):
                return h.to_dict()  # type: ignore[call-arg]
        except Exception:
            pass

        out: Dict[str, Any] = {}
        for name in ('symbol', 'quantity', 'average_cost', 'currency'):
            try:
                val = getattr(h, name)
            except Exception:
                try:
                    val = h[name]  # type: ignore[index]
                except Exception:
                    val = None
            if val is not None:
                out[name] = val
        if not out:
            out['repr'] = repr(h)
        return out

    # --- Public API -----------------------------------------------------
    def account_summary(
        self,
        account_id: str,
        portfolio_id: Optional[str] = None,
        include_transactions: bool = True,
        include_holdings: bool = True,
        price_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a consolidated account report.

        The returned dict contains:
          - account: core account fields (from account.to_dict()) if available
          - balance: account cash balance as string
          - holdings: list of normalized holding dicts (if portfolio_id given and include_holdings)
          - valuation: breakdown produced by ValuationEngine.portfolio_breakdown when possible
          - realized_pl: sum of realized P/L from transactions (string)
          - transactions: list of normalized transactions (if include_transactions)

        Depending on available collaborators some pieces may be omitted or set
        to None. Errors from underlying components are surfaced as
        ReportingError.
        """
        report: Dict[str, Any] = {}

        # Account info
        if self.account_service is None:
            raise ReportingError('no account service available')

        try:
            acct = self.account_service.get_account(account_id)
        except Exception as exc:
            raise ReportingError(f'failed to fetch account {account_id}: {exc}') from exc

        # account.to_dict() is preferred, fall back to attributes
        try:
            account_dict = acct.to_dict() if hasattr(acct, 'to_dict') else {
                'account_id': getattr(acct, 'account_id', None),
                'owner': getattr(acct, 'owner', None),
                'balance': str(getattr(acct, 'balance', None)),
                'currency': getattr(acct, 'currency', None),
            }
        except Exception:
            account_dict = {'account_id': account_id}

        report['account'] = account_dict
        # Provide balance as string if available
        try:
            bal = acct.get_balance() if hasattr(acct, 'get_balance') else getattr(acct, 'balance', None)
            report['balance'] = format(bal, 'f') if bal is not None else None
        except Exception:
            report['balance'] = None

        # Transactions: obtain via history_service if available (provides normalized dicts), else from transaction_repo
        txs_raw: List[Any] = []
        txs_normalized: List[Dict[str, Any]] = []
        if include_transactions:
            if self.history_service is not None:
                try:
                    txs_normalized = list(self.history_service.list_transactions_for_account(account_id))
                except Exception:
                    # fall back to transaction_repo below
                    txs_normalized = []
            if not txs_normalized and self.transaction_repo is not None:
                # Attempt to use transaction_repo.list_for_account
                try:
                    txs_raw = list(self.transaction_repo.list_for_account(account_id))
                    txs_normalized = [self._normalize_tx_to_dict(t) for t in txs_raw]
                except Exception:
                    # give up gracefully
                    txs_normalized = []

            report['transactions'] = txs_normalized
        else:
            report['transactions'] = []

        # Holdings: fetch snapshot via history_service if present, else via portfolio_repo
        holdings_list: List[Dict[str, Any]] = []
        holdings_raw: Iterable[Any] = []
        if include_holdings and portfolio_id is not None:
            if self.history_service is not None:
                try:
                    holdings_list = list(self.history_service.holdings_snapshot(portfolio_id))
                except KeyError:
                    # missing portfolio -> empty list
                    holdings_list = []
                except Exception:
                    holdings_list = []
            elif self.portfolio_repo is not None:
                try:
                    portfolio = self.portfolio_repo.get(portfolio_id)
                    if portfolio is None:
                        holdings_list = []
                    else:
                        # try list_holdings
                        if hasattr(portfolio, 'list_holdings') and callable(getattr(portfolio, 'list_holdings')):
                            holdings_raw = list(portfolio.list_holdings())
                        else:
                            # mapping with 'holdings'
                            try:
                                holdings_raw = list(portfolio.get('holdings', []))  # type: ignore[call-arg]
                            except Exception:
                                # try internal attribute
                                holdings_attr = getattr(portfolio, '_holdings', None)
                                if holdings_attr is None:
                                    holdings_raw = []
                                elif isinstance(holdings_attr, dict):
                                    holdings_raw = list(holdings_attr.values())
                                else:
                                    holdings_raw = holdings_attr
                        holdings_list = [self._normalize_holding_to_dict(h) for h in holdings_raw]
                except Exception:
                    holdings_list = []
            else:
                holdings_list = []
        report['holdings'] = holdings_list

        # Valuation: use valuation engine if present
        if self._valuation is not None and holdings_list:
            try:
                # The valuation.portfolio_breakdown accepts either a portfolio-like object
                # or an iterable of holdings. We have normalized holdings to dicts; the
                # valuation engine supports iterables of holdings (mapping or object).
                valuation = self._valuation.portfolio_breakdown(holdings_list, price_overrides or {})
                report['valuation'] = valuation
            except Exception as exc:
                # Surface valuation error but do not fail entire report
                report['valuation'] = {'error': str(exc)}
        else:
            # No valuation available or no holdings
            report['valuation'] = None

        # Realized P/L: sum profit_loss from transactions (use valuation engine helper if available)
        realized_total: Optional[Decimal] = None
        try:
            if self._valuation is not None and report.get('transactions') is not None:
                # transactions normalized to dicts; pass the raw normalized list
                realized_total = self._valuation.realized_pl_from_transactions(report['transactions'])
            elif report.get('transactions') is not None:
                # fallback: sum profit_loss keys available in normalized transactions
                total = Decimal('0.00')
                found_any = False
                for tx in report['transactions']:
                    pl = tx.get('profit_loss') if isinstance(tx, dict) else None
                    if pl is None:
                        continue
                    found_any = True
                    try:
                        total += Decimal(pl)
                    except Exception:
                        # try to coerce via string
                        try:
                            total += Decimal(str(pl))
                        except Exception:
                            raise ReportingError('invalid profit_loss value in transactions')
                if found_any:
                    realized_total = total
                else:
                    realized_total = Decimal('0.00')
        except Exception as exc:
            # if valuation.realized_pl_from_transactions raised, record the error
            report['realized_pl'] = {'error': str(exc)}
        else:
            report['realized_pl'] = self._format_decimal(realized_total)

        return report


__all__ = ['ReportingService', 'ReportingError']"""