"""accounts.py

Provides the Account class representing a user account with a cash balance.
Supports creating accounts, depositing, and withdrawing while enforcing basic
invariants (non-negative balances, positive amounts for operations, and
insufficient funds checks).

This module is self-contained and uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from threading import Lock
from typing import Optional, Dict
import uuid

# Set a reasonable default precision for monetary operations
getcontext().prec = 28

# A helper constant for two decimal places (cents)
_CENT = Decimal('0.01')


class AccountError(Exception):
    """Base class for account-related errors."""


class InvalidAmountError(AccountError):
    """Raised when an invalid amount (e.g., negative or zero) is provided."""


class InsufficientFundsError(AccountError):
    """Raised when a withdrawal would overdraw the account."""


def _to_decimal(amount) -> Decimal:
    """Convert an input amount to Decimal rounded to 2 decimal places.

    Accepts Decimal, int, float, or str. Raises InvalidAmountError for
    unconvertible values.
    """
    try:
        dec = Decimal(amount)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidAmountError(f"Invalid monetary amount: {amount!r}") from exc

    # Quantize to cents using a sensible rounding mode
    return dec.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass
class Account:
    """Represents a user account with a cash balance.

    Attributes:
        account_id: Unique identifier for the account. If not provided, a
            UUID4-based string will be generated.
        owner: Name or identifier of the account owner.
        balance: Current balance as Decimal (always >= 0).
        currency: Currency code (informational only), default 'USD'.
    """

    owner: str
    account_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    balance: Decimal = field(default_factory=lambda: Decimal('0.00'))
    currency: str = 'USD'

    # Internal lock to make deposit/withdraw thread-safe
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        # Ensure balance is a Decimal with two decimal places and non-negative
        self.balance = _to_decimal(self.balance)
        if self.balance < 0:
            raise InvalidAmountError("Initial balance cannot be negative")

    @classmethod
    def create(cls, owner: str, initial_deposit: Optional[object] = 0, currency: str = 'USD', account_id: Optional[str] = None) -> 'Account':
        """Factory method to create a new Account.

        Args:
            owner: Owner name or identifier (required).
            initial_deposit: Initial balance (defaults to 0). Must be >= 0.
            currency: Currency code string (informational).
            account_id: Optional explicit account id. If omitted a UUID is used.
        """
        if not owner:
            raise ValueError("owner must be provided")

        balance = _to_decimal(initial_deposit)
        if balance < 0:
            raise InvalidAmountError("Initial deposit must be non-negative")

        acct_id = account_id if account_id is not None else str(uuid.uuid4())
        return cls(owner=owner, account_id=acct_id, balance=balance, currency=currency)

    def deposit(self, amount: object) -> Decimal:
        """Deposit a positive amount into the account.

        Returns the new balance.
        """
        dec_amount = _to_decimal(amount)
        if dec_amount <= Decimal('0'):
            raise InvalidAmountError("Deposit amount must be positive")

        with self._lock:
            self.balance = (self.balance + dec_amount).quantize(_CENT, rounding=ROUND_HALF_UP)
            return self.balance

    def withdraw(self, amount: object) -> Decimal:
        """Withdraw a positive amount from the account.

        Raises InsufficientFundsError if the requested amount exceeds the
        available balance. Returns the new balance.
        """
        dec_amount = _to_decimal(amount)
        if dec_amount <= Decimal('0'):
            raise InvalidAmountError("Withdrawal amount must be positive")

        with self._lock:
            if dec_amount > self.balance:
                raise InsufficientFundsError(f"Insufficient funds: requested {dec_amount}, available {self.balance}")
            self.balance = (self.balance - dec_amount).quantize(_CENT, rounding=ROUND_HALF_UP)
            return self.balance

    def get_balance(self) -> Decimal:
        """Return the current balance as Decimal.

        The returned Decimal is already quantized to two decimal places.
        """
        # Return a copy to avoid accidental external mutation
        return Decimal(self.balance)

    def to_dict(self) -> Dict[str, object]:
        """Serialize core account information to a dict."""
        return {
            'account_id': self.account_id,
            'owner': self.owner,
            'balance': str(self.balance),
            'currency': self.currency,
        }

    def __repr__(self) -> str:
        return f"Account(account_id={self.account_id!r}, owner={self.owner!r}, balance={str(self.balance)!r}, currency={self.currency!r})"