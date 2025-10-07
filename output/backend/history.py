from __future__ import annotations

from typing import Optional, List, Any, Iterable, Dict
from datetime import datetime, timezone

# Try to import repository adapters when used inside the package. If not
# available the user of HistoryService should inject compatible objects.
try:
    from .transaction_repository import TransactionRepository
    from .portfolio_repository import PortfolioRepository
except Exception:  # pragma: no cover - fallback for static analysis
    TransactionRepository = None  # type: ignore
    PortfolioRepository = None  # type: ignore


class HistoryError(Exception):
    """Base exception for history-related errors."""


class HistoryService:
    """Service providing transaction history and holdings snapshots.

    The service is a thin adapter over a TransactionRepository and a
    PortfolioRepository. If repositories are not provided they are left as
    None and callers must pass repositories that implement the minimal
    methods used below.

    Expected repository methods:
      - transaction_repo.list_for_account(account_id) -> Iterable[transaction]
      - portfolio_repo.get(portfolio_id) -> portfolio or None
      - portfolio object: must support list_holdings() -> Iterable[holding]

    Normalization behavior:
      - Transactions produced by the repository may be mapping-like or
        objects (e.g. Transaction instances). For objects, if a to_dict()
        method exists it will be used; otherwise common attributes are
        extracted into a dict.
      - Holdings are normalized via a to_dict() method if present, or by
        extracting common attributes (symbol, quantity, average_cost,
        currency) when possible.
    """

    def __init__(self, transaction_repo: Optional[object] = None, portfolio_repo: Optional[object] = None) -> None:
        self._tx_repo = transaction_repo
        self._portfolio_repo = portfolio_repo

    # -- Repository accessors -------------------------------------------------
    def _require_tx_repo(self) -> object:
        if self._tx_repo is not None:
            return self._tx_repo
        if TransactionRepository is not None:
            # lazily create a repository instance if possible
            return TransactionRepository()
        raise HistoryError("no transaction repository available")

    def _require_portfolio_repo(self) -> object:
        if self._portfolio_repo is not None:
            return self._portfolio_repo
        if PortfolioRepository is not None:
            return PortfolioRepository()
        raise HistoryError("no portfolio repository available")

    # -- Helpers ---------------------------------------------------------------
    @staticmethod
    def _to_datetime_maybe(value: Any) -> Optional[datetime]:
        """Try to convert a created_at-like value to a timezone-aware datetime.

        Accepts datetime or ISO-formatted string. Returns None if conversion
        is not possible.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                # assume UTC for naive datetimes
                return dt.replace(tzinfo=timezone.utc)
            return dt
        if isinstance(value, str):
            try:
                # fromisoformat supports offsets; ensure timezone-aware when present
                dt = datetime.fromisoformat(value)
            except Exception:
                # best-effort: try parsing common ISO forms
                try:
                    # strip fractional seconds if present and endswith Z
                    if value.endswith('Z'):
                        return datetime.fromisoformat(value[:-1]).replace(tzinfo=timezone.utc)
                except Exception:
                    return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return None

    @staticmethod
    def _tx_to_dict(tx: Any) -> Dict[str, Any]:
        """Normalize a transaction-like object to a plain dict.

        Prefers calling to_dict() when available, otherwise attempts to
        extract a few common attributes/keys.
        """
        # If mapping-like, return a shallow copy
        try:
            if isinstance(tx, dict):
                return dict(tx)
        except Exception:
            pass

        # If object has to_dict, use it
        try:
            if hasattr(tx, 'to_dict') and callable(getattr(tx, 'to_dict')):
                return tx.to_dict()  # type: ignore[call-arg]
        except Exception:
            # fall through to attribute extraction
            pass

        out: Dict[str, Any] = {}
        # common fields to attempt to extract
        for name in ('transaction_id', 'kind', 'account_id', 'from_account', 'to_account', 'quantity', 'price', 'amount', 'profit_loss', 'created_at', 'executed_at', 'metadata'):
            try:
                val = getattr(tx, name)
            except Exception:
                try:
                    # try mapping-style
                    val = tx[name]  # type: ignore[index]
                except Exception:
                    val = None
            if val is not None:
                out[name] = val
        # fall back: give the object's repr if no fields found
        if not out:
            out['repr'] = repr(tx)
        return out

    @staticmethod
    def _holding_to_dict(h: Any) -> Dict[str, Any]:
        """Normalize a holding-like object to a plain dict with core fields."""
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
            # Normalize Decimals/other numeric types by converting to string for safety
            if val is not None:
                out[name] = val
        if not out:
            out['repr'] = repr(h)
        return out

    # -- Public API -----------------------------------------------------------
    def list_transactions_for_account(self, account_id: str, sort_desc: bool = True) -> List[Dict[str, Any]]:
        """Return a list of transactions referencing account_id as plain dicts.

        Transactions are returned sorted by created_at (descending by default).
        If the underlying repository returns objects or mappings they will be
        normalized into dicts. This method does not mutate the stored objects.
        """
        repo = self._require_tx_repo()
        # repository is expected to provide list_for_account(account_id)
        if not hasattr(repo, 'list_for_account'):
            raise HistoryError('transaction repository missing list_for_account')

        txs = list(repo.list_for_account(account_id))  # type: ignore[call-arg]
        normalized = [self._tx_to_dict(t) for t in txs]

        # Attempt to sort by created_at when present
        def _key(item: Dict[str, Any]):
            val = item.get('created_at')
            dt = self._to_datetime_maybe(val)
            # If created_at is missing, use minimal sentinel
            return dt or datetime.fromtimestamp(0, tz=timezone.utc)

        normalized.sort(key=_key, reverse=bool(sort_desc))
        return normalized

    def transactions_between(self, account_id: str, start: Optional[Any] = None, end: Optional[Any] = None, sort_desc: bool = True) -> List[Dict[str, Any]]:
        """Return transactions for account_id filtered by an optional time range.

        start and end may be datetime or ISO-8601 strings. Range is inclusive
        on both ends when provided.
        """
        all_tx = self.list_transactions_for_account(account_id, sort_desc=False)
        start_dt = self._to_datetime_maybe(start) if start is not None else None
        end_dt = self._to_datetime_maybe(end) if end is not None else None

        out: List[Dict[str, Any]] = []
        for tx in all_tx:
            dt = self._to_datetime_maybe(tx.get('created_at'))
            # if we cannot determine a datetime, be conservative and include it
            if dt is None:
                out.append(tx)
                continue
            if start_dt is not None and dt < start_dt:
                continue
            if end_dt is not None and dt > end_dt:
                continue
            out.append(tx)

        out.sort(key=lambda item: self._to_datetime_maybe(item.get('created_at')) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=bool(sort_desc))
        return out

    def holdings_snapshot(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """Return a snapshot of holdings for the given portfolio_id.

        The portfolio is retrieved from the portfolio repository and each
        holding is normalized to a plain dict. Raises KeyError if the
        portfolio cannot be found.
        """
        repo = self._require_portfolio_repo()
        if not hasattr(repo, 'get'):
            raise HistoryError('portfolio repository missing get')

        portfolio = repo.get(portfolio_id)  # type: ignore[call-arg]
        if portfolio is None:
            raise KeyError(portfolio_id)

        # Try to get holdings via list_holdings() or via attribute / mapping
        holdings_iter: Iterable[Any]
        try:
            if hasattr(portfolio, 'list_holdings') and callable(getattr(portfolio, 'list_holdings')):
                holdings_iter = portfolio.list_holdings()
            else:
                # try mapping-like
                if isinstance(portfolio, dict) and 'holdings' in portfolio:
                    holdings_iter = portfolio['holdings']
                else:
                    # fallback: try _holdings attribute
                    holdings_attr = getattr(portfolio, '_holdings', None)
                    if holdings_attr is None:
                        # nothing we can do
                        holdings_iter = []
                    elif isinstance(holdings_attr, dict):
                        holdings_iter = list(holdings_attr.values())
                    else:
                        holdings_iter = holdings_attr
        except Exception:
            holdings_iter = []

        out = [self._holding_to_dict(h) for h in holdings_iter]
        return out

    def account_snapshot(self, account_id: str, portfolio_id: Optional[str] = None, include_transactions: bool = True, include_holdings: bool = True) -> Dict[str, Any]:
        """Return a combined snapshot for an account.

        If portfolio_id is provided holdings for that portfolio will be
        included. The resulting dict contains keys 'transactions' and
        'holdings' depending on the include_* flags.
        """
        result: Dict[str, Any] = {}
        if include_transactions:
            try:
                result['transactions'] = self.list_transactions_for_account(account_id)
            except Exception as exc:
                # expose repository errors as HistoryError
                raise HistoryError(f'failed to list transactions: {exc}') from exc
        if include_holdings:
            if portfolio_id is None:
                result['holdings'] = []
            else:
                try:
                    result['holdings'] = self.holdings_snapshot(portfolio_id)
                except KeyError:
                    # translate missing portfolio into an empty holdings list
                    result['holdings'] = []
                except Exception as exc:
                    raise HistoryError(f'failed to obtain holdings snapshot: {exc}') from exc
        return result


__all__ = ['HistoryService', 'HistoryError']


# For demonstration when executed directly print a short message
if __name__ == '__main__':
    print('HistoryService module: provides transaction listings and holdings snapshots')