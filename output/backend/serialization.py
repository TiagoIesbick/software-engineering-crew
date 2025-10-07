"""\"\"\"serialization.py

Serializer: utility to convert domain objects (accounts, holdings, transactions)
into JSON-friendly dictionaries. The Serializer is intentionally tolerant of
several shapes of inputs:
 - mapping-like objects (dict)
 - objects exposing a to_dict() method
 - objects with common attributes (e.g. account_id, balance, symbol, quantity)

Numeric Decimals are rendered as plain decimal strings (no exponent).
Datetimes are converted to ISO-8601 strings and naive datetimes are assumed
UTC. Iterables are converted to lists. None values are preserved by default
but can be omitted by configuration.

Only Python standard library is used.
\"\"\"

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from decimal import Decimal
from datetime import datetime, timezone
from collections.abc import Mapping


class Serializer:
    \"\"\"Convert domain objects into JSON-friendly structures.

    Usage:
        s = Serializer()
        d = s.to_dict(obj)

    By default None values are preserved. Pass include_none=False to omit
    keys with None values when serializing mappings produced by this class.
    \"\"\"

    def __init__(self, include_none: bool = True) -> None:
        self.include_none = bool(include_none)

    # Public API -------------------------------------------------
    def to_dict(self, obj: Any) -> Any:
        \"\"\"Serialize an arbitrary object into JSON-friendly Python structures.

        Returns primitives (str/int/bool), lists, or dicts composed of those
        primitives. Decimal instances are converted to decimal strings; datetimes
        to ISO strings. Mapping-like and iterable inputs are handled
        recursively. Objects exposing to_dict() are respected.
        \"\"\"
        # Primitives
        if obj is None:
            return None
        if isinstance(obj, (str, int, bool)):
            return obj
        if isinstance(obj, Decimal):
            return self._format_decimal(obj)
        if isinstance(obj, float):
            # floats are JSON-serializable; keep them as-is to avoid surprising
            # formatting. Caller may prefer to pass Decimals instead.
            return obj

        # Datetime
        if isinstance(obj, datetime):
            return self._format_datetime(obj)

        # Mapping-like
        if isinstance(obj, Mapping):
            return self._serialize_mapping(obj)

        # Iterable (but not str/bytes) -> list
        if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray)):
            return [self.to_dict(i) for i in obj]

        # Objects with to_dict
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
            try:
                raw = obj.to_dict()  # type: ignore[call-arg]
            except Exception:
                # Fall through to attribute-based extraction
                raw = None
            if isinstance(raw, Mapping):
                return self._serialize_mapping(raw)
            if raw is not None:
                return self.to_dict(raw)

        # Best-effort: try to detect known domain objects by attributes
        # Account-like
        if any(hasattr(obj, name) for name in ('account_id', 'owner', 'balance')):
            return self.to_account_dict(obj)

        # Holding-like
        if any(hasattr(obj, name) for name in ('symbol', 'quantity', 'average_cost')):
            return self.to_holding_dict(obj)

        # Transaction-like
        if any(hasattr(obj, name) for name in ('transaction_id', 'kind', 'amount')):
            return self.to_transaction_dict(obj)

        # Fallback: try to read __dict__ if available
        if hasattr(obj, '__dict__'):
            return self._serialize_mapping(dict(getattr(obj, '__dict__')))

        # As a last resort return the string representation
        return {'repr': repr(obj)}

    def to_account_dict(self, account: Any) -> Dict[str, Any]:
        \"\"\"Serialize an account-like object to a dict with stringified balance.

        Accepts mapping-like shapes or objects with attributes. Ensures balance
        (if Decimal) is converted to a string.
        \"\"\"
        if isinstance(account, Mapping):
            raw = dict(account)
        elif hasattr(account, 'to_dict') and callable(getattr(account, 'to_dict')):
            raw = account.to_dict()  # type: ignore[call-arg]
        else:
            raw = {
                'account_id': getattr(account, 'account_id', None),
                'owner': getattr(account, 'owner', None),
                'balance': getattr(account, 'balance', None),
                'currency': getattr(account, 'currency', None),
            }

        # Normalize balance and other fields
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if k == 'balance':
                if isinstance(v, Decimal):
                    out[k] = self._format_decimal(v)
                else:
                    # attempt to coerce numeric-ish values to string form
                    if v is None:
                        out[k] = None
                    else:
                        out[k] = str(v)
            else:
                out[k] = self.to_dict(v)

        return self._prune_none(out)

    def to_holding_dict(self, holding: Any) -> Dict[str, Any]:
        \"\"\"Serialize a Holding-like object to a dict with stringified numerics.\"\"\"
        if isinstance(holding, Mapping):
            raw = dict(holding)
        elif hasattr(holding, 'to_dict') and callable(getattr(holding, 'to_dict')):
            raw = holding.to_dict()  # type: ignore[call-arg]
        else:
            raw = {
                'symbol': getattr(holding, 'symbol', None),
                'quantity': getattr(holding, 'quantity', None),
                'average_cost': getattr(holding, 'average_cost', None),
                'currency': getattr(holding, 'currency', None),
            }

        out: Dict[str, Any] = {}
        # Expected keys: symbol, quantity, average_cost, currency
        for k in ('symbol', 'quantity', 'average_cost', 'currency'):
            v = raw.get(k)
            if v is None:
                out[k] = None
                continue
            if k in ('quantity', 'average_cost'):
                if isinstance(v, Decimal):
                    out[k] = self._format_decimal(v)
                else:
                    # keep numeric string form
                    out[k] = str(v)
            else:
                out[k] = self.to_dict(v)

        return self._prune_none(out)

    def to_transaction_dict(self, tx: Any) -> Dict[str, Any]:
        \"\"\"Serialize a Transaction-like object to a dict with normalized fields.

        Ensures numeric fields (quantity, price, amount, profit_loss) are strings
        and datetimes are ISO-formatted strings.
        \"\"\"
        if isinstance(tx, Mapping):
            raw = dict(tx)
        elif hasattr(tx, 'to_dict') and callable(getattr(tx, 'to_dict')):
            raw = tx.to_dict()  # type: ignore[call-arg]
        else:
            # attempt to extract common attributes
            raw = {}
            for name in ('transaction_id', 'kind', 'account_id', 'from_account', 'to_account', 'quantity', 'price', 'amount', 'profit_loss', 'created_at', 'executed_at', 'metadata'):
                try:
                    val = getattr(tx, name)
                except Exception:
                    try:
                        val = tx[name]  # type: ignore[index]
                    except Exception:
                        val = None
                if val is not None:
                    raw[name] = val

        out: Dict[str, Any] = {}
        # Simple string fields
        for key in ('transaction_id', 'kind', 'account_id', 'from_account', 'to_account'):
            if key in raw:
                out[key] = self.to_dict(raw.get(key))

        # Numeric fields: quantity, price, amount, profit_loss
        for key in ('quantity', 'price', 'amount', 'profit_loss'):
            if key in raw:
                val = raw.get(key)
                if val is None:
                    out[key] = None
                elif isinstance(val, Decimal):
                    out[key] = self._format_decimal(val)
                else:
                    # if it's a datetime accidentally placed here, route it
                    if isinstance(val, datetime):
                        out[key] = self._format_datetime(val)
                    else:
                        out[key] = str(val)

        # timestamps
        for key in ('created_at', 'executed_at'):
            if key in raw:
                v = raw.get(key)
                if isinstance(v, datetime):
                    out[key] = self._format_datetime(v)
                else:
                    # try to interpret strings as-is; if None preserve
                    out[key] = v if v is None else str(v)

        # metadata: ensure nested serializable
        if 'metadata' in raw:
            out['metadata'] = self.to_dict(raw.get('metadata'))

        return self._prune_none(out)

    # --- Internal helpers -----------------------------------------
    def _serialize_mapping(self, mapping: Mapping) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in mapping.items():
            # ensure keys are strings
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            out[key] = self.to_dict(v)
        return self._prune_none(out)

    def _format_decimal(self, d: Decimal) -> str:
        # Use plain format to avoid scientific notation
        return format(d, 'f')

    def _format_datetime(self, dt: datetime) -> str:
        # Ensure timezone-aware; assume UTC for naive datetimes
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def _prune_none(self, mapping: Dict[str, Any]) -> Dict[str, Any]:
        if self.include_none:
            return mapping
        return {k: v for k, v in mapping.items() if v is not None}


__all__ = ['Serializer']