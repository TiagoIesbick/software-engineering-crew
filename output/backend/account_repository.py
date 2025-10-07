from __future__ import annotations

# account_repository.py
# Adapter repository that provides CRUD access to Account objects using a
# storage layer (e.g. InMemoryStorage). This module is intentionally small
# and uses only the standard library and local package storage/accounts.

from typing import Any, Iterable, List, Optional

try:
    # Relative import assuming this module lives alongside storage.py and accounts.py
    from .storage import InMemoryStorage
    from .accounts import Account
except Exception:
    # If imported in isolation (for static analysis), provide fallbacks for type
    InMemoryStorage = None  # type: ignore
    Account = object  # type: ignore


class AccountRepository:
    """Repository adapter exposing a simple CRUD interface for Account
    objects. The adapter delegates to an underlying storage implementation.

    The repository implements the minimal protocol expected by the service
    layer:
      - save(account: Account) -> None
      - get(account_id: str) -> Optional[Account]
      - delete(account_id: str) -> None
      - list_all() -> List[Account]
      - exists(account_id: str) -> bool

    The underlying storage object may implement methods using different
    names (for example, InMemoryStorage provides save_account/get_account/...).
    This adapter will try to call the most specific method name first and
    fall back to generic names when appropriate.
    """

    def __init__(self, storage: Optional[Any] = None) -> None:
        """Create an AccountRepository.

        If no storage is provided an InMemoryStorage instance is created (when
        available).
        """
        if storage is None:
            if InMemoryStorage is None:
                raise RuntimeError("No storage implementation available and no storage provided")
            storage = InMemoryStorage()
        self._storage = storage

    # --- Save / update -------------------------------------------------
    def save(self, account: Account) -> None:
        """Save or update an Account in the underlying storage.

        Delegates to storage.save_account(account) if present, otherwise to
        storage.save(account). Any exceptions from the storage layer are
        propagated.
        """
        # Prefer explicit account store API
        if hasattr(self._storage, 'save_account'):
            return self._storage.save_account(account)
        # Generic save
        if hasattr(self._storage, 'save'):
            return self._storage.save(account)
        raise AttributeError('Underlying storage does not implement save/save_account')

    # --- Get ----------------------------------------------------------
    def get(self, account_id: str) -> Optional[Account]:
        """Return an Account or None if not found.

        Delegates to storage.get_account(account_id) or storage.get(account_id).
        """
        if hasattr(self._storage, 'get_account'):
            return self._storage.get_account(account_id)
        if hasattr(self._storage, 'get'):
            return self._storage.get(account_id)
        raise AttributeError('Underlying storage does not implement get/get_account')

    # --- Delete -------------------------------------------------------
    def delete(self, account_id: str) -> None:
        """Delete an account from storage.

        Delegates to storage.delete_account(account_id) or storage.delete(account_id).
        If the account is not present the underlying storage is expected to
        raise KeyError which will be propagated.
        """
        if hasattr(self._storage, 'delete_account'):
            return self._storage.delete_account(account_id)
        if hasattr(self._storage, 'delete'):
            return self._storage.delete(account_id)
        raise AttributeError('Underlying storage does not implement delete/delete_account')

    # --- List / Exists -----------------------------------------------
    def list_all(self) -> List[Account]:
        """Return a list of all accounts stored.

        Delegates to storage.list_accounts() or storage.list_all().
        """
        if hasattr(self._storage, 'list_accounts'):
            return list(self._storage.list_accounts())
        if hasattr(self._storage, 'list_all'):
            return list(self._storage.list_all())
        raise AttributeError('Underlying storage does not implement list_all/list_accounts')

    def exists(self, account_id: str) -> bool:
        """Return True if account_id exists in storage.

        Delegates to storage.exists_account(account_id) or storage.exists(account_id).
        """
        if hasattr(self._storage, 'exists_account'):
            return bool(self._storage.exists_account(account_id))
        if hasattr(self._storage, 'exists'):
            return bool(self._storage.exists(account_id))
        raise AttributeError('Underlying storage does not implement exists/exists_account')


__all__ = ['AccountRepository']

# For visibility when executed directly, print a short summary (not used on import)
if __name__ == '__main__':
    print('AccountRepository module')