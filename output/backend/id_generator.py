"""id_generator.py

Provides IdGenerator for generating unique identifiers for accounts and transactions.

This module is self-contained and uses only the Python standard library.
"""

from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Callable, Optional


class IdGenerator:
    """Generate unique identifiers for accounts and transactions.

    The generator produces IDs with simple, human-readable prefixes and a
    uniqueness component based on UUID4. Optionally it can include a
    monotonic counter and a nanosecond timestamp to make IDs sortable and
    improve traceability.

    Usage:
        gen = IdGenerator()
        acct_id = gen.generate_account_id()
        txn_id = gen.generate_transaction_id()

    Parameters:
        account_prefix: Prefix for generated account IDs (default: 'acct').
        transaction_prefix: Prefix for transaction IDs (default: 'txn').
        include_timestamp: If True, include time.time_ns() in the ID
            (makes IDs roughly sortable by creation time).
        include_counter: If True, append a process-local monotonic counter
            to help avoid collisions in extremely high-throughput scenarios.
        short_uuid: If True, use a shortened UUID hex (12 chars) to reduce
            ID length at the cost of a tiny increase in collision probability.
        uid_fn: Optional custom function returning a unique string; if
            provided it will be used instead of uuid.uuid4().hex.
    """

    def __init__(
        self,
        account_prefix: str = "acct",
        transaction_prefix: str = "txn",
        include_timestamp: bool = False,
        include_counter: bool = False,
        short_uuid: bool = False,
        uid_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        if not isinstance(account_prefix, str) or not account_prefix:
            raise ValueError("account_prefix must be a non-empty string")
        if not isinstance(transaction_prefix, str) or not transaction_prefix:
            raise ValueError("transaction_prefix must be a non-empty string")

        self.account_prefix = account_prefix
        self.transaction_prefix = transaction_prefix
        self.include_timestamp = bool(include_timestamp)
        self.include_counter = bool(include_counter)
        self.short_uuid = bool(short_uuid)
        self._uid_fn = uid_fn if uid_fn is not None else lambda: uuid.uuid4().hex

        # Internal counter and lock for thread-safety
        self._lock = Lock()
        self._counter = 0

    def _next_counter(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def _generate(self, prefix: str) -> str:
        """Core ID generation routine.

        The generated format varies depending on configuration but will always
        include the prefix and a unique component.
        """
        parts = [prefix]

        if self.include_timestamp:
            # time_ns gives nanosecond resolution (monotonic w.r.t. system clock)
            parts.append(str(time.time_ns()))

        if self.include_counter:
            parts.append(str(self._next_counter()))

        uid = self._uid_fn()
        if self.short_uuid:
            # Keep first 12 hex chars (48 bits) which is still low collision
            # probability for typical usages, though not as safe as full uuid4.
            uid = uid.replace('-', '')[:12]
        parts.append(uid)

        # Join with '-' for readability
        return "-".join(parts)

    def generate_account_id(self) -> str:
        """Return a new unique account id (string)."""
        return self._generate(self.account_prefix)

    def generate_transaction_id(self) -> str:
        """Return a new unique transaction id (string)."""
        return self._generate(self.transaction_prefix)

    @staticmethod
    def generate_uuid(short: bool = False) -> str:
        """Utility: generate a UUID-based hex string.

        If short is True, returns a shortened 12-char hex string.
        """
        h = uuid.uuid4().hex
        return h[:12] if short else h


__all__ = ["IdGenerator"]

# For debug/inspection, when executed directly print an example
if __name__ == '__main__':
    gen = IdGenerator(include_timestamp=True, include_counter=True)
    print("Example account id:", gen.generate_account_id())
    print("Example transaction id:", gen.generate_transaction_id())"""