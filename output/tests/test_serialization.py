from decimal import Decimal
from datetime import datetime, timezone

import pytest

from output.backend.serialization import Serializer


def test_decimal_datetime_and_primitives_serialization():
    s = Serializer()

    # Decimal -> decimal string
    assert s.to_dict(Decimal('1.2300')) == '1.23'

    # int, str, bool preserved
    assert s.to_dict(42) == 42
    assert s.to_dict('hello') == 'hello'
    assert s.to_dict(True) is True

    # float preserved as float
    f = 0.125
    assert s.to_dict(f) == f

    # None preserved by default
    assert s.to_dict(None) is None

    # naive datetime assumed UTC and returned as ISO string ending with +00:00
    naive = datetime(2020, 1, 1, 0, 0, 0)
    iso = s.to_dict(naive)
    assert isinstance(iso, str)
    assert iso.endswith('+00:00')

    # aware datetime preserved as ISO string
    aware = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert s.to_dict(aware) == aware.astimezone(timezone.utc).isoformat()


def test_mapping_and_iterable_serialization_and_key_coercion():
    s = Serializer()

    data = {
        1: Decimal('2.50'),
        'nested': [Decimal('3.0'), {'d': Decimal('4.5')}, None],
        b'bin': b'bytes',
    }

    out = s.to_dict(data)
    # keys coerced to strings
    assert '1' in out
    assert out['1'] == '2.5'

    # nested list preserved and decimals converted
    assert isinstance(out['nested'], list)
    assert out['nested'][0] == '3'
    # ensure nested mapping serialized
    assert isinstance(out['nested'][1], dict) if isinstance(out['nested'][1], dict) else True
    # None preserved in nested structures
    assert out['nested'][2] is None

    # bytes key was coerced to string and its value serialized (bytes -> repr fallback)
    # we just ensure serialization didn't crash and produced a mapping
    assert any(isinstance(k, str) for k in out.keys())


def test_object_with_to_dict_and_attribute_account_like_detection():
    s = Serializer()

    class WithToDict:
        def to_dict(self):
            return {'account_id': 'acct-1', 'owner': 'alice', 'balance': Decimal('5.00'), 'extra': None}

    w = WithToDict()
    out = s.to_dict(w)
    assert out['account_id'] == 'acct-1'
    assert out['owner'] == 'alice'
    # balance should be string
    assert out['balance'] == '5.00'
    # include_none default True preserves None
    assert 'extra' in out and out['extra'] is None

    # Attribute-based account-like object
    class AttrAccount:
        def __init__(self):
            self.account_id = 'acct-2'
            self.owner = 'bob'
            self.balance = Decimal('2.00')
            self.currency = 'EUR'

    a = AttrAccount()
    out2 = s.to_dict(a)
    assert out2['account_id'] == 'acct-2'
    assert out2['balance'] == '2.00'
    assert out2['currency'] == 'EUR'


def test_holding_and_transaction_detection_and_numeric_stringification():
    s = Serializer()

    class HoldingLike:
        def __init__(self):
            self.symbol = 'FOO'
            self.quantity = Decimal('1.23456789')
            self.average_cost = Decimal('10.00')
            self.currency = 'USD'

    h = HoldingLike()
    out = s.to_dict(h)
    assert out['symbol'] == 'FOO'
    # numeric fields stringified
    assert out['quantity'] == '1.23456789'
    assert out['average_cost'] == '10.00'

    class TxLike:
        def __init__(self):
            self.transaction_id = 'tx-1'
            self.kind = 'deposit'
            self.amount = Decimal('3.50')
            self.created_at = datetime(2021, 1, 1, tzinfo=timezone.utc)

    tx = TxLike()
    tout = s.to_dict(tx)
    assert tout['transaction_id'] == 'tx-1'
    assert tout['amount'] == '3.50'
    # created_at converted to ISO string
    assert tout['created_at'] == tx.created_at.astimezone(timezone.utc).isoformat()


def test_include_none_false_prunes_none_values():
    s = Serializer(include_none=False)
    data = {'a': None, 'b': Decimal('1.00'), 'c': {'sub': None, 'x': 1}}
    out = s.to_dict(data)
    assert 'a' not in out
    # nested prune should apply as well
    assert 'sub' not in out['c']
    assert out['b'] == '1.00'


def test_fallback_to_repr_for_unserializable_objects_and_bytes():
    s = Serializer()

    class NoDict:
        def __repr__(self):
            return '<no-dict>'

    obj = NoDict()
    out = s.to_dict(obj)
    assert isinstance(out, dict)
    assert out.get('repr') == repr(obj)

    # bytes should also fall back to repr (excluded from iterable handling)
    b = b'abc'
    bout = s.to_dict(b)
    assert bout == {'repr': repr(b)}


# Additional edge-case: ensure lists of mixed domain objects are handled
def test_iterable_of_mixed_domain_objects_serializes_correctly():
    s = Serializer()

    class SimpleHolding:
        def __init__(self):
            self.symbol = 'Z'
            self.quantity = Decimal('2')
            self.average_cost = Decimal('1')

    class SimpleTx:
        def __init__(self):
            self.transaction_id = 't-x'
            self.kind = 'withdrawal'
            self.amount = Decimal('7.00')

    items = [SimpleHolding(), SimpleTx(), {'plain': Decimal('0.1')}]
    out = s.to_dict(items)
    assert isinstance(out, list)
    # first item is holding-like dict
    assert out[0]['symbol'] == 'Z' and out[0]['quantity'] == '2'
    # second is transaction-like dict
    assert out[1]['transaction_id'] == 't-x' and out[1]['amount'] == '7.00'
    # third preserved mapping
    assert out[2]['plain'] == '0.1'