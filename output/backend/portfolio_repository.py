# -*- coding: utf-8 -*-
"""portfolio_repository.py

Repository adapter exposing CRUD and query operations for Portfolio objects.

This adapter delegates to an underlying storage implementation (for example
InMemoryStorage from storage.py). It prefers specific portfolio-oriented
storage APIs when present (save_portfolio, get_portfolio, etc.) and falls
back to generic method names (save/get/delete/list_all/exists) when
necessary. When no storage is provided and InMemoryStorage is available the
adapter will create a local instance; otherwise an error is raised.

Only standard library modules are used.
"""

from __future__ import annotations

from typing import Any, List, Optional

try:
    # Try relative import when used within the package
    from .storage import InMemoryStorage
    from .portfolio import Portfolio
except Exception:
    InMemoryStorage = None  # type: ignore
    Portfolio = object  # type: ignore


class PortfolioRepository:
    """Adapter repository for Portfolio objects.

    Methods:
      - save(portfolio) -> Optional[Any]: persist portfolio and return whatever
        the underlying storage returned (if anything).
      - get(portfolio_id) -> Optional[Portfolio]
      - delete(portfolio_id) -> None
      - list_all() -> List[Portfolio]
      - exists(portfolio_id) -> bool
      - list_by_owner(owner) -> List[Portfolio]

    The repository delegates to underlying storage methods, preferring the
    explicit portfolio-named APIs when available.
    """

    def __init__(self, storage: Optional[Any] = None) -> None:
        if storage is None:
            if InMemoryStorage is None:
                raise RuntimeError("No storage implementation available and no storage provided")
            storage = InMemoryStorage()
        self._storage = storage

    # --- CRUD / Query API ---------------------------------------
    def save(self, portfolio: Any) -> Optional[Any]:
        """Save a portfolio object.

        Delegates to storage.save_portfolio(portfolio) when available,
        otherwise tries storage.save(portfolio). Returns whatever the
        underlying call returns (often None).
        """
        if hasattr(self._storage, 'save_portfolio'):
            return self._storage.save_portfolio(portfolio)
        if hasattr(self._storage, 'save'):
            return self._storage.save(portfolio)
        raise AttributeError('Underlying storage does not implement save_portfolio or save')

    def get(self, portfolio_id: str) -> Optional[Portfolio]:
        """Return the stored Portfolio or None if not present."""
        if hasattr(self._storage, 'get_portfolio'):
            return self._storage.get_portfolio(portfolio_id)
        if hasattr(self._storage, 'get'):
            return self._storage.get(portfolio_id)
        raise AttributeError('Underlying storage does not implement get_portfolio or get')

    def delete(self, portfolio_id: str) -> None:
        """Delete a portfolio. Underlying storage is expected to raise KeyError if missing."""
        if hasattr(self._storage, 'delete_portfolio'):
            return self._storage.delete_portfolio(portfolio_id)
        if hasattr(self._storage, 'delete'):
            return self._storage.delete(portfolio_id)
        raise AttributeError('Underlying storage does not implement delete_portfolio or delete')

    def list_all(self) -> List[Portfolio]:
        """Return a list of all portfolios.

        Delegates to storage.list_portfolios() when available, otherwise
        storage.list_all(). Returns a shallow copy (list()).
        """
        if hasattr(self._storage, 'list_portfolios'):
            return list(self._storage.list_portfolios())
        if hasattr(self._storage, 'list_all'):
            return list(self._storage.list_all())
        raise AttributeError('Underlying storage does not implement list_portfolios or list_all')

    def exists(self, portfolio_id: str) -> bool:
        """Return True if portfolio_id exists in storage."""
        if hasattr(self._storage, 'exists_portfolio'):
            return bool(self._storage.exists_portfolio(portfolio_id))
        if hasattr(self._storage, 'exists'):
            return bool(self._storage.exists(portfolio_id))
        raise AttributeError('Underlying storage does not implement exists_portfolio or exists')

    def list_by_owner(self, owner: str) -> List[Portfolio]:
        """Return portfolios whose owner matches the given owner string.

        Prefers storage.list_portfolios_by_owner(owner) when available.
        Otherwise performs a best-effort linear scan over list_all() and
        matches either mapping key 'owner' or attribute 'owner'.
        """
        if hasattr(self._storage, 'list_portfolios_by_owner'):
            return list(self._storage.list_portfolios_by_owner(owner))

        # Fallback: use list_all and filter
        portfolios: List[Portfolio] = self.list_all()
        out: List[Portfolio] = []
        for p in portfolios:
            found = False
            try:
                if isinstance(p, dict):
                    if p.get('owner') == owner:
                        found = True
                else:
                    if getattr(p, 'owner', None) == owner:
                        found = True
            except Exception:
                # Skip objects that raise on introspection
                found = False
            if found:
                out.append(p)
        return out


__all__ = ['PortfolioRepository']

# When executed directly print a short message (not used on import)
if __name__ == '__main__':
    print('PortfolioRepository module')