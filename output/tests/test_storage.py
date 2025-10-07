from typing import Any
import pytest

from output.backend.storage import InMemoryStorage


class SimpleObj:
    def __init__(self, id_name: str, id_value: str, **kwargs: Any) -> None:
        # assign identifier under the given attribute name
        setattr(self, id_name, id_value)
        for k, v in kwargs.items():
            setattr(self, k, v)


class NoAttrAssign:
    """Object that refuses attribute assignment to simulate an unattachable
    transaction object.
    """

    def __init__(self, **kwargs: Any) -> None:
        # allow setting initial attributes directly on __dict__ to simulate
        # an object with state but disallow setattr afterwards
        self.__dict__.update(kwargs)

    def __setattr__(self, name, value):
        raise AttributeError("no attribute assignment")


def test_save_get_exists_and_list_accounts_with_mapping_and_object():
    s = InMemoryStorage()

    # Mapping-like account
    acct_map = {"account_id": "m-1", "owner": "alice"}
    s.save_account(acct_map)
    assert s.exists_account("m-1")
    assert s.get_account("m-1") is acct_map

    # Attribute-like account
    acct_obj = SimpleObj("account_id", "o-1", owner="bob")
    s.save_account(acct_obj)
    assert s.exists_account("o-1")
    assert s.get_account("o-1") is acct_obj

    # list_accounts returns both objects (order not important)
    listed = s.list_accounts()
    ids = {getattr(a, "account_id", a.get("account_id")) if isinstance(a, dict) else getattr(a, "account_id") for a in listed}
    assert {"m-1", "o-1"} <= ids


def test_save_account_missing_id_raises_value_error():
    s = InMemoryStorage()
    # dict without account_id
    with pytest.raises(ValueError):
        s.save_account({"owner": "noid"})

    # object without account_id attribute
    class X:
        pass

    with pytest.raises(ValueError):
        s.save_account(X())


def test_delete_account_and_nonexistent_keyerror():
    s = InMemoryStorage()
    a = {"account_id": "to-del", "owner": "z"}
    s.save_account(a)
    assert s.exists_account("to-del")
    s.delete_account("to-del")
    assert not s.exists_account("to-del")
    with pytest.raises(KeyError):
        s.delete_account("to-del")


def test_portfolio_save_get_list_and_owner_query():
    s = InMemoryStorage()

    p1 = {"portfolio_id": "p-1", "owner": "owner-a", "name": "A"}
    p2 = SimpleObj("portfolio_id", "p-2", owner="owner-b", name="B")
    p3 = {"portfolio_id": "p-3", "owner": "owner-a", "name": "C"}

    s.save_portfolio(p1)
    s.save_portfolio(p2)
    s.save_portfolio(p3)

    # list_portfolios returns three entries
    allp = s.list_portfolios()
    assert len(allp) == 3

    # list_portfolios_by_owner should find p1 and p3 for owner-a
    for_owner_a = s.list_portfolios_by_owner("owner-a")
    ids = set()
    for p in for_owner_a:
        if isinstance(p, dict):
            ids.add(p["portfolio_id"])
        else:
            ids.add(p.portfolio_id)
    assert ids == {"p-1", "p-3"}

    # missing portfolio delete raises
    with pytest.raises(KeyError):
        s.delete_portfolio("nope")

    # exists_portfolio
    assert s.exists_portfolio("p-1")
    assert not s.exists_portfolio("no-such")


def test_transaction_save_generates_id_and_attaches_for_mapping():
    s = InMemoryStorage()

    tx = {"from_account": "a1", "to_account": "a2", "amount": 100}
    tid = s.save_transaction(tx)
    # returned id should be present and attached into the mapping
    assert isinstance(tid, str) and len(tid) == 32
    assert tx.get("transaction_id") == tid
    assert s.exists_transaction(tid)
    assert s.get_transaction(tid) is tx


def test_transaction_save_respects_existing_id_and_attribute_objects():
    s = InMemoryStorage()

    # object with attribute transaction_id present
    tx_obj = SimpleObj("transaction_id", "tx-123", account_id="acct-1")
    returned = s.save_transaction(tx_obj)
    assert returned == "tx-123"
    assert s.get_transaction("tx-123") is tx_obj


def test_transaction_save_on_unattachable_object_still_stores_and_returns_id():
    s = InMemoryStorage()

    tx = NoAttrAssign(account_id="x-1", amount=5)
    tid = s.save_transaction(tx)
    # tid should be returned
    assert isinstance(tid, str) and len(tid) == 32
    # object itself will not have transaction_id attribute due to NoAttrAssign
    assert getattr(tx, "transaction_id", None) is None
    # but storage still stores the object under returned id
    assert s.get_transaction(tid) is tx


def test_list_transactions_for_account_match_various_fields():
    s = InMemoryStorage()

    t1 = {"transaction_id": "t1", "account_id": "acc-A", "amount": 1}
    t2 = {"transaction_id": "t2", "from_account": "acc-A", "amount": 2}
    t3 = {"transaction_id": "t3", "to_account": "acc-A", "amount": 3}
    t4 = {"transaction_id": "t4", "account_id": "other", "amount": 4}

    for tx in (t1, t2, t3, t4):
        s.save_transaction(tx)

    found = s.list_transactions_for_account("acc-A")
    ids = {tx["transaction_id"] for tx in found if isinstance(tx, dict)}
    assert ids == {"t1", "t2", "t3"}


def test_transaction_delete_and_exists_and_list_transactions():
    s = InMemoryStorage()
    tx = {"transaction_id": "d1", "account_id": "a"}
    s.save_transaction(tx)
    assert s.exists_transaction("d1")
    s.delete_transaction("d1")
    assert not s.exists_transaction("d1")
    with pytest.raises(KeyError):
        s.delete_transaction("d1")

    # list_transactions reflects current store
    assert s.list_transactions() == []


def test_clear_all_wipes_every_store():
    s = InMemoryStorage()
    s.save_account({"account_id": "aa"})
    s.save_portfolio({"portfolio_id": "pp"})
    s.save_transaction({"transaction_id": "tt"})

    assert s.list_accounts()
    assert s.list_portfolios()
    assert s.list_transactions()

    s.clear_all()

    assert s.list_accounts() == []
    assert s.list_portfolios() == []
    assert s.list_transactions() == []