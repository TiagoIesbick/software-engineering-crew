"""
# storage.py

Provides InMemoryStorage which offers simple thread-safe, dict-backed in-memory
stores for accounts, portfolios, and transactions.

This module is self-contained and uses only the Python standard library.

Design notes:
- Stores are simple dicts keyed by identifier strings.
- Methods follow a small CRUD-like API for each store:
    - save_*(obj) -> for accounts/portfolios returns None, for transactions returns id
    - get_*(id) -> Optional[object]
    - delete_*(id) -> None (raises KeyError if missing)
    - list_*() -> List[object]
    - exists_*(id) -> bool
- For transactions, if the saved object does not provide an id, the storage
  will generate one (uuid4 hex) and attach it under 'transaction_id' if the
  object is a mutable mapping or attribute if an object supports assignment.
- Thread-safety: separate RLocks for each store.

This is intentionally minimal and meant for tests and simple in-memory use.
"""

from __future__ import annotations
from threading import RLock
from typing import Any, Dict, List, Optional
import uuid


class InMemoryStorage:
  """Thread-safe in-memory storage for accounts, portfolios, and transactions.
  
  The storage stores objects as-is. Objects are expected to expose an
  identifier either as an attribute (e.g. obj.account_id) or a mapping key
  (e.g. obj['account_id']). For transactions, if no id is present the store
  will generate one (uuid4 hex) and attach it when possible.
  """
  
  def __init__(self) -> None:
    # Underlying stores
    self._accounts: Dict[str, Any] = {}
    self._portfolios: Dict[str, Any] = {}
    self._transactions: Dict[str, Any] = {}
    # Locks for thread-safety (fine-grained per-store)
    self._accounts_lock = RLock()
    self._portfolios_lock = RLock()
    self._transactions_lock = RLock()
    
  # --- Helpers -----------------------------------------------------
  @staticmethod
  def _extract_id(obj: Any, key_name: str) -> Optional[str]:
    """Try to extract an identifier named key_name from obj.
    Accepts objects with attribute access or mapping access.
    Returns None
    if no id can be determined.
    """
    
    # Mapping-like
    try:
      if isinstance(obj, dict) and key_name in obj:
        val = obj[key_name]
        return str(val) if val is not None else None
    except Exception:
      pass
    
    # Attribute-like
    try:
      val = getattr(obj, key_name)
    except Exception:
      val = None
    if val is not None:
      return str(val)
    return None
  
  @staticmethod
  def _attach_id(obj: Any, key_name: str, id_value: str) -> None:
    """Attach id_value to obj under key_name when possible.
    If obj is a mapping, set obj[key_name]=id_value. If obj has attribute
    assignment (setattr) set that attribute. Otherwise do nothing.
    """
    try:
      if isinstance(obj, dict):
        obj[key_name] = id_value
        return
    except Exception:
      pass
    
    try:
      setattr(obj, key_name, id_value)
      return
    except Exception:
      pass
    
  # --- Account store API ------------------------------------------
  def save_account(self, account: Any) -> None:
    """Save or update an account.
    The account object must expose an account_id (attribute or mapping key).
    """
    acct_id = self._extract_id(account, 'account_id')
    if not acct_id:
      raise ValueError('account must have an account_id')
    
    with self._accounts_lock:
      self._accounts[acct_id] = account
      
  def get_account(self, account_id: str) -> Optional[Any]:
    """Return the account object or None if not present."""
    with self._accounts_lock:
      return self._accounts.get(account_id)
    
  def delete_account(self, account_id: str) -> None:
    """Delete an account. Raises KeyError if not found."""
    with self._accounts_lock:
      if account_id in self._accounts:
        del self._accounts[account_id]
      else:
        raise KeyError(account_id)
      
  def list_accounts(self) -> List[Any]:
    """Return a list of all account objects."""
    with self._accounts_lock:
      return list(self._accounts.values())
    
  def exists_account(self, account_id: str) -> bool:
    with self._accounts_lock:
      return account_id in self._accounts
    
  # --- Portfolio store API ----------------------------------------
  def save_portfolio(self, portfolio: Any) -> None:
    """Save or update a portfolio.
    The portfolio must expose a portfolio_id (attribute or mapping key).
    """
    pid = self._extract_id(portfolio, 'portfolio_id')
    if not pid:
      raise ValueError('portfolio must have a portfolio_id')
    
    with self._portfolios_lock:
      self._portfolios[pid] = portfolio
      
  def get_portfolio(self, portfolio_id: str) -> Optional[Any]:
    with self._portfolios_lock:
      return self._portfolios.get(portfolio_id)
    
  def delete_portfolio(self, portfolio_id: str) -> None:
    with self._portfolios_lock:
      if portfolio_id in self._portfolios:
        del self._portfolios[portfolio_id]
      else:
        raise KeyError(portfolio_id)
      
  def list_portfolios(self) -> List[Any]:
    with self._portfolios_lock:
      return list(self._portfolios.values())
    
  def exists_portfolio(self, portfolio_id: str) -> bool:
    with self._portfolios_lock:
      return portfolio_id in self._portfolios
    
  def list_portfolios_by_owner(self, owner: str) -> List[Any]:
    """Return portfolios whose 'owner' attribute/key matches the given owner.
    This is a convenience query and performs a simple linear scan.
    """
    result: List[Any] = []
    with self._portfolios_lock:
      for p in self._portfolios.values():
        # Try mapping first then attribute
        val = None
        try:
          if isinstance(p, dict):
            val = p.get('owner')
        except Exception:
          val = None
        if val is None:
          try:
            val = getattr(p, 'owner')
          except Exception:
            val = None
        if val == owner:
          result.append(p)
    return result
  
  # --- Transaction store API --------------------------------------
  def save_transaction(self, transaction: Any) -> str:
    """Save a transaction and return its transaction_id.
    If the transaction object lacks a transaction_id the store will
    generate a uuid4-based one and attempt to set it on the object when
    possible (mapping or attribute). The returned id is the key used in
    the transaction store.
    """
    tid = self._extract_id(transaction, 'transaction_id')
    if not tid:
      # Generate a new id and attach if possible
      tid = uuid.uuid4().hex
      
    self._attach_id(transaction, 'transaction_id', tid)
    with self._transactions_lock:
      self._transactions[tid] = transaction
    
    return tid
  
  def get_transaction(self, transaction_id: str) -> Optional[Any]:
    with self._transactions_lock:
      return self._transactions.get(transaction_id)
    
  def delete_transaction(self, transaction_id: str) -> None:
    with self._transactions_lock:
      if transaction_id in self._transactions:
        del self._transactions[transaction_id]
      else:
        raise KeyError(transaction_id)
      
  def list_transactions(self) -> List[Any]:
    with self._transactions_lock:
      return list(self._transactions.values())
    
  def exists_transaction(self, transaction_id: str) -> bool:
    with self._transactions_lock:
      return transaction_id in self._transactions
    
  def list_transactions_for_account(self, account_id: str) -> List[Any]:
    """Return transactions that reference the given account_id.
    A transaction is considered to reference an account if it has a key or
    attribute named 'account_id' or 'from_account'/'to_account' matching
    the provided id. This is a best-effort convenience helper.
    """
    out: List[Any] = []
    
    with self._transactions_lock:
      for tx in self._transactions.values():
        # Check common fields
        found = False
        # Try mapping access
        try:
          if isinstance(tx, dict):
            if tx.get('account_id') == account_id:
              found = True
            if tx.get('from_account') == account_id or tx.get('to_account') == account_id:
              found = True
        except Exception:
          pass
        
        if not found:
          # Attribute access
          try:
            if getattr(tx, 'account_id', None) == account_id:
              found = True
          except Exception:
            pass
          
        if not found:
          try:
            if getattr(tx, 'from_account', None) == account_id or getattr(tx, 'to_account', None) == account_id:
              found = True
          except Exception:
            pass
          
        if found:
          out.append(tx)
          
    return out
  
  # --- Utility -----------------------------------------------------
  def clear_all(self) -> None:
    """Clear all stores. Useful for tests or resetting state."""
    with self._accounts_lock:
      self._accounts.clear()
      
    with self._portfolios_lock:
      self._portfolios.clear()
      
    with self._transactions_lock:
      self._transactions.clear()
        
__all__ = ['InMemoryStorage']
