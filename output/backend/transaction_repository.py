"""transaction_repository.py

Repository adapter exposing CRUD and query operations for Transaction objects.

This adapter delegates to an underlying storage implementation (for example
InMemoryStorage from storage.py). It prefers specific transaction-oriented
storage APIs when present (save_transaction, get_transaction, etc.) and
falls back to generic method names (save/get/delete/list_all/exists) when
necessary. When no storage is provided and InMemoryStorage is available the
adapter will create a local instance; otherwise an error is raised.

Only standard library modules are used.
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    # Try relative import when used within the package
    from .storage import InMemoryStorage
except Exception:
    InMemoryStorage = None  # type: ignore


class TransactionRepository:
    """Adapter repository for transaction objects.

    Methods:
      - save(transaction) -> str: persist transaction and return transaction_id
      - get(transaction_id) -> Optional[Any]
      - delete(transaction_id) -> None
      - list_all() -> List[Any]
      - exists(transaction_id) -> bool
      - list_for_account(account_id) -> List[Any]

    The repository delegates to underlying storage methods, preferring the
    explicit transaction-named APIs when available.
    """

    def __init__(self, storage: Optional[Any] = None) -> None:
        if storage is None:
            if InMemoryStorage is None:
                raise RuntimeError("No storage implementation available and no storage provided")
            storage = InMemoryStorage()
        self._storage = storage

    # --- Helpers -------------------------------------------------
    @staticmethod
    def _extract_id(obj: Any) -> Optional[str]:
        """Try to extract transaction_id from obj via mapping or attribute access."""
        try:
            if isinstance(obj, dict) and 'transaction_id' in obj:
                val = obj.get('transaction_id')
                return str(val) if val is not None else None
        except Exception:
            pass
        try:
            val = getattr(obj, 'transaction_id')
        except Exception:
            val = None
        if val is not None:
            return str(val)
        return None

    # --- CRUD / Query API ---------------------------------------
    def save(self, transaction: Any) -> str:
        """Save a transaction object and return its transaction_id.

        Delegates to storage.save_transaction(transaction) when available,
        otherwise tries storage.save(transaction). If the underlying call
        does not return an id, this method will attempt to read transaction_id
        from the object and return that value.
        """
        # Prefer explicit API
        if hasattr(self._storage, 'save_transaction'):
            res = self._storage.save_transaction(transaction)
            # Underlying implementation should return the id
            if res is not None:
                return str(res)
            # Fallback to reading attached id
            tid = self._extract_id(transaction)
            if tid is not None:
                return tid
            raise RuntimeError('Underlying storage did not return transaction id')

        # Fallback to generic save
        if hasattr(self._storage, 'save'):
            res = self._storage.save(transaction)
            if res is not None:
                return str(res)
            tid = self._extract_id(transaction)
            if tid is not None:
                return tid
            raise RuntimeError('Underlying storage did not return transaction id')

        raise AttributeError('Underlying storage does not implement save_transaction or save')

    def get(self, transaction_id: str) -> Optional[Any]:
        """Return the stored transaction or None if not present."""
        if hasattr(self._storage, 'get_transaction'):
            return self._storage.get_transaction(transaction_id)
        if hasattr(self._storage, 'get'):
            return self._storage.get(transaction_id)
        raise AttributeError('Underlying storage does not implement get_transaction or get')

    def delete(self, transaction_id: str) -> None:
        """Delete a transaction. Underlying storage is expected to raise KeyError if missing."""
        if hasattr(self._storage, 'delete_transaction'):
            return self._storage.delete_transaction(transaction_id)
        if hasattr(self._storage, 'delete'):
            return self._storage.delete(transaction_id)
        raise AttributeError('Underlying storage does not implement delete_transaction or delete')

    def list_all(self) -> List[Any]:
        """Return a list of all transactions."""
        if hasattr(self._storage, 'list_transactions'):
            return list(self._storage.list_transactions())
        if hasattr(self._storage, 'list_all'):
            return list(self._storage.list_all())
        raise AttributeError('Underlying storage does not implement list_transactions or list_all')

    def exists(self, transaction_id: str) -> bool:
        """Return True if transaction_id exists in storage."""
        if hasattr(self._storage, 'exists_transaction'):
            return bool(self._storage.exists_transaction(transaction_id))
        if hasattr(self._storage, 'exists'):
            return bool(self._storage.exists(transaction_id))
        raise AttributeError('Underlying storage does not implement exists_transaction or exists')

    def list_for_account(self, account_id: str) -> List[Any]:
        """Return transactions that reference the given account id.

        Delegates to storage.list_transactions_for_account(account_id) when
        available. Otherwise performs a best-effort filter over list_all().
        """
        if hasattr(self._storage, 'list_transactions_for_account'):
            return list(self._storage.list_transactions_for_account(account_id))

        # Fallback: filter all transactions for common fields
        out: List[Any] = []
        for tx in self.list_all():
            found = False
            try:
                if isinstance(tx, dict):
                    if tx.get('account_id') == account_id:
                        found = True
                    if tx.get('from_account') == account_id or tx.get('to_account') == account_id:
                        found = True
                else:
                    if getattr(tx, 'account_id', None) == account_id:
                        found = True
                    if getattr(tx, 'from_account', None) == account_id or getattr(tx, 'to_account', None) == account_id:
                        found = True
            except Exception:
                # Be conservative and skip objects that raise on introspection
                found = False
            if found:
                out.append(tx)
        return out


__all__ = ['TransactionRepository']