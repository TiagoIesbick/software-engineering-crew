"""
transaction.py

Provides the Transaction class representing an immutable record of a
financial transaction: deposit, withdrawal, buy, or sell.

The Transaction class is implemented as a frozen dataclass and includes
fields for identifiers, account references, quantity, price, amounts,
profit/loss, timestamps, and optional metadata. Monetary values use
Decimal and are quantized to two decimal places (cents). Quantity is
kept as a Decimal with up to 8 decimal places to accommodate fractional
shares/units.

This module uses only the Python standard library.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid

# Reasonable precision for monetary calculations
getcontext().prec = 28

# Quantization constants
_CENT = Decimal('0.01')
_QTY = Decimal('0.00000001')

# up to 8 decimal places for quantities


class TransactionError(Exception):
    """Base class for transaction-related errors."""
    

class InvalidTransactionError(TransactionError):
    """Raised for invalid transaction construction or values."""
    
    
def _to_decimal(value) -> Decimal:
    """Convert input to Decimal and quantize to cents.
    Accepts Decimal, int, float, or str. Raises InvalidTransactionError
    for unconvertible values.
    """
    try:
        dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidTransactionError(f"Invalid monetary value: {value!r}") from exc
    return dec.quantize(_CENT, rounding=ROUND_HALF_UP)

def _to_quantity(value) -> Decimal:
    """Convert input to Decimal and quantize to quantity resolution.
    Quantity may be fractional (e.g. shares). We quantize to 8 decimal
    places which should be sufficient for most use cases.
    """
    try:
        dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidTransactionError(f"Invalid quantity value: {value!r}") from exc
    return dec.quantize(_QTY, rounding=ROUND_HALF_UP)
    
    
@dataclass(frozen=True)
class Transaction:
    """Immutable record of a financial transaction.
    Fields:
        transaction_id: unique id (string). If omitted a uuid4 hex string is generated automatically.
        kind: one of 'deposit', 'withdrawal', 'buy', 'sell'.
        account_id: primary account related to the transaction (for deposits, withdrawals, and trades).
        from_account / to_account: optional fields useful for transfers or multi-party transactions.
        quantity: quantity traded (Decimal), for buy/sell transactions.
        price: price per unit (Decimal), for buy/sell transactions.
        amount: monetary amount (Decimal). For trades this is quantity * price (quantized), for cash ops it is the cash value.
        profit_loss: optional realized/unrealized P/L (Decimal).
        created_at: timestamp when the transaction object was created (UTC).
        executed_at: optional timestamp when the transaction was executed/settled.
        metadata: optional free-form mapping for auxiliary information.
    """
    transaction_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: str = field(default='deposit')
    
    # Common account fields
    account_id: Optional[str] = None
    from_account: Optional[str] = None
    to_account: Optional[str] = None
    
    # Trade-specific fields
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    
    # Monetary fields
    amount: Decimal = field(default_factory=lambda: Decimal('0.00'))
    profit_loss: Optional[Decimal] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    
    # Arbitrary metadata
    metadata: Optional[Dict[str, Any]] = None
    
    # Allowed kinds
    _ALLOWED_KINDS = ("deposit", "withdrawal", "buy", "sell")
    
    def __post_init__(self) -> None:
        # Validate kind
        if self.kind not in self._ALLOWED_KINDS:
            raise InvalidTransactionError(f"Invalid transaction kind: {self.kind!r}")
        
        # Validate timestamps
        if self.created_at.tzinfo is None:
            # enforce timezone-aware UTC
            object.__setattr__(self, 'created_at', self.created_at.replace(tzinfo=timezone.utc))
        if self.executed_at is not None and self.executed_at.tzinfo is None:
            object.__setattr__(self, 'executed_at', self.executed_at.replace(tzinfo=timezone.utc))
            
        # Validate and normalize monetary/quantity fields depending on kind
        if self.kind in ("deposit", "withdrawal"):
            # Must have an account_id and a positive amount
            if not self.account_id:
                raise InvalidTransactionError("deposit/withdrawal requires account_id")
            
            # Convert amount to Decimal cents
            try:
                amt = _to_decimal(self.amount)
            except InvalidTransactionError:
                raise InvalidTransactionError("Invalid amount for cash transaction")
            
            if amt <= Decimal('0'):
                raise InvalidTransactionError("amount must be positive for deposit/withdrawal")
            
            # Set normalized amount
            object.__setattr__(self, 'amount', amt)
            
            # Clear trade-specific fields if present
            if self.quantity is not None or self.price is not None:
                raise InvalidTransactionError("deposit/withdrawal must not have quantity/price")
            else:  # buy or sell
                # Must have account_id, quantity and price
                if not self.account_id:
                    raise InvalidTransactionError("trade transaction requires account_id")
                if self.quantity is None:
                    raise InvalidTransactionError("trade transaction requires quantity")
                if self.price is None:
                    raise InvalidTransactionError("trade transaction requires price")
                
            # Normalize quantity and price
            try:
                qty = _to_quantity(self.quantity)
            except InvalidTransactionError:
                raise InvalidTransactionError("Invalid quantity for trade")
            
            try:
                pr = _to_decimal(self.price)
            except InvalidTransactionError:
                raise InvalidTransactionError("Invalid price for trade")
            if qty <= Decimal('0'):
                raise InvalidTransactionError("quantity must be positive for trade")
            if pr <= Decimal('0'):
                raise InvalidTransactionError("price must be positive for trade")
            
            # Compute amount = qty * price (then quantize to cents)
            amt = (qty * pr).quantize(_CENT, rounding=ROUND_HALF_UP)
            object.__setattr__(self, 'quantity', qty)
            object.__setattr__(self, 'price', pr)
            object.__setattr__(self, 'amount', amt)
            
            # Normalize profit_loss if provided
            if self.profit_loss is not None:
                try:
                    pl = _to_decimal(self.profit_loss)
                except InvalidTransactionError:
                    raise InvalidTransactionError("Invalid profit_loss value")
                object.__setattr__(self, 'profit_loss', pl)
                
            # Convenience factories\n    @classmethod\n    def deposit(cls, account_id: str, amount: object, transaction_id: Optional[str] = None, *, created_at: Optional[datetime] = None, executed_at: Optional[datetime] = None, metadata: Optional[Dict[str, Any]] = None) -> \"Transaction\":\n        \"\"\"Create a deposit transaction.\"\"\"\n        tid = transaction_id if transaction_id is not None else uuid.uuid4().hex\n        ca = created_at if created_at is not None else datetime.now(timezone.utc)\n        return cls(transaction_id=tid, kind='deposit', account_id=account_id, amount=_to_decimal(amount), created_at=ca, executed_at=executed_at, metadata=metadata)\n\n    @classmethod\n    def withdrawal(cls, account_id: str, amount: object, transaction_id: Optional[str] = None, *, created_at: Optional[datetime] = None, executed_at: Optional[datetime] = None, metadata: Optional[Dict[str, Any]] = None) -> \"Transaction\":\n        \"\"\"Create a withdrawal transaction.\"\"\"\n        tid = transaction_id if transaction_id is not None else uuid.uuid4().hex\n        ca = created_at if created_at is not None else datetime.now(timezone.utc)\n        return cls(transaction_id=tid, kind='withdrawal', account_id=account_id, amount=_to_decimal(amount), created_at=ca, executed_at=executed_at, metadata=metadata)\n\n    @classmethod\n    def trade(cls, account_id: str, side: str, quantity: object, price: object, transaction_id: Optional[str] = None, *, created_at: Optional[datetime] = None, executed_at: Optional[datetime] = None, profit_loss: Optional[object] = None, metadata: Optional[Dict[str, Any]] = None) -> \"Transaction\":\n        \"\"\"Create a trade transaction (buy or sell).\n\n        side must be 'buy' or 'sell'. quantity and price are required.\n        \"\"\"\n        side = side.lower()\n        if side not in ('buy', 'sell'):\n            raise InvalidTransactionError(\"side must be 'buy' or 'sell'\")\n        tid = transaction_id if transaction_id is not None else uuid.uuid4().hex\n        ca = created_at if created_at is not None else datetime.now(timezone.utc)\n        pl = _to_decimal(profit_loss) if profit_loss is not None else None\n        # Note: quantity and price will be normalized in __post_init__\n        return cls(transaction_id=tid, kind=side, account_id=account_id, quantity=_to_quantity(quantity), price=_to_decimal(price), profit_loss=pl, created_at=ca, executed_at=executed_at, metadata=metadata)\n\n    def to_dict(self) -> Dict[str, Any]:\n        \"\"\"Serialize the transaction to a plain dict with stringified Decimals and ISO times.\"\"\"\n        def _fmt_decimal(d: Optional[Decimal]) -> Optional[str]:\n            return None if d is None else format(d, 'f')\n\n        def _fmt_dt(dt: Optional[datetime]) -> Optional[str]:\n            return None if dt is None else dt.astimezone(timezone.utc).isoformat()\n\n        return {\n            'transaction_id': self.transaction_id,\n            'kind': self.kind,\n            'account_id': self.account_id,\n            'from_account': self.from_account,\n            'to_account': self.to_account,\n            'quantity': None if self.quantity is None else format(self.quantity, 'f'),\n            'price': _fmt_decimal(self.price),\n            'amount': _fmt_decimal(self.amount),\n            'profit_loss': _fmt_decimal(self.profit_loss),\n            'created_at': _fmt_dt(self.created_at),\n            'executed_at': _fmt_dt(self.executed_at),\n            'metadata': dict(self.metadata) if self.metadata is not None else None,\n        }\n\n    def __repr__(self) -> str:  # pragma: no cover - simple human-friendly repr\n        return (f\"Transaction(transaction_id={self.transaction_id!r}, kind={self.kind!r}, account_id={self.account_id!r}, amount={str(self.amount)!r})\")\n\n\n__all__ = [\n    'Transaction',\n    'TransactionError',\n    'InvalidTransactionError',\n]\n"}