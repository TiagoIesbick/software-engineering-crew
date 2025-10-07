from decimal import Decimal
import re
import pytest

from output.backend.transaction_repository import TransactionRepository
from output.backend.storage import InMemoryStorage


class SimpleObj:
    def __init__(self, transaction_id: str = None, account_id: str = None, **kwargs):
        if transaction_id is not None:
            self.transaction_id = transaction_id
        if account_id is not None:
            self.account_id = account_id
        for k, v in kwargs.items():
            setattr(self, k, v)


class RaisesOnAttr:
    "Object that raises on attribute access to simulate introspection failures."

    def __getattr__(self, name):
        raise RuntimeError("cannot access attributes")


def test_save_with_default_inmemory_storage_attaches_and_returns_id():
    repo = TransactionRepository()
    tx = {"account_id": "acct-1", "amount": 100}

    tid = repo.save(tx)
    assert isinstance(tid, str)
    assert re.fullmatch(r"[0-9a-f]{32}", tid)

    # Should exist and be retrievable
    assert repo.exists(tid)
    got = repo.get(tid)
    assert got is tx

    # list_all contains the transaction
    all_tx = repo.list_all()
    assert any((isinstance(t, dict) and t.get("transaction_id") == tid) or (hasattr(t, "transaction_id") and getattr(t, "transaction_id") == tid) for t in all_tx)

    # delete works and subsequent delete raises KeyError
    repo.delete(tid)
    assert not repo.exists(tid)
    with pytest.raises(KeyError):
        repo.delete(tid)


def test_save_respects_preexisting_transaction_id_on_attribute_object():
    repo = TransactionRepository()
    obj = SimpleObj(transaction_id="fixed-tx", account_id="a")

    returned = repo.save(obj)
    assert returned == "fixed-tx"
    assert repo.exists("fixed-tx")
    assert repo.get("fixed-tx") is obj

    # cleanup
    repo.delete("fixed-tx")


def test_generic_storage_save_delegation_and_return_behavior():
    # Generic storage implementing save/get/delete/list_all/exists (generic names)
    class GenericStorage:
        def __init__(self):
            self._store = {}

        def save(self, tx):
            # return a string id to simulate storage that returns id
            tid = getattr(tx, "transaction_id", None)
            if tid is None and isinstance(tx, dict) and "transaction_id" in tx:
                tid = tx["transaction_id"]
            # store under either provided tid or a synthetic id
            key = tid or "gen-1"
            self._store[key] = tx
            return key

        def get(self, transaction_id):
            return self._store.get(transaction_id)

        def delete(self, transaction_id):
            if transaction_id in self._store:
                del self._store[transaction_id]
            else:
                raise KeyError(transaction_id)

        def list_all(self):
            return list(self._store.values())

        def exists(self, transaction_id):
            return transaction_id in self._store

    gs = GenericStorage()
    repo = TransactionRepository(storage=gs)

    # If save returns a value, repo.save should return it
    tx_obj = SimpleObj(transaction_id=None, account_id="acct-x")
    # provide a mapping form to ensure returned id is 'gen-1'
    tx_map = {"account_id": "acct-x"}
    tid = repo.save(tx_map)
    assert tid == "gen-1"
    assert repo.get(tid) is tx_map

    # If save returns None but object has transaction_id attribute, repo.save should return it
    class GenericNoneSave:
        def __init__(self):
            self._store = {}

        def save(self, tx):
            # simulate no return
            key = None
            if isinstance(tx, dict) and "transaction_id" in tx:
                key = tx["transaction_id"]
            elif hasattr(tx, "transaction_id"):
                key = getattr(tx, "transaction_id")
            if key is not None:
                self._store[key] = tx
            else:
                # store under synthetic key but return None
                self._store["x"] = tx
            return None

        def get(self, transaction_id):
            return self._store.get(transaction_id)

        def delete(self, transaction_id):
            if transaction_id in self._store:
                del self._store[transaction_id]
            else:
                raise KeyError(transaction_id)

        def list_all(self):
            return list(self._store.values())

        def exists(self, transaction_id):
            return transaction_id in self._store

    gns = GenericNoneSave()
    repo2 = TransactionRepository(storage=gns)

    tx_with_id = {"transaction_id": "explicit-id", "account_id": "a"}
    returned = repo2.save(tx_with_id)
    assert returned == "explicit-id"
    assert repo2.get("explicit-id") is tx_with_id

    # If save returns None and no id attached, expect RuntimeError
    tx_no_id = {"account_id": "b"}
    with pytest.raises(RuntimeError):
        repo2.save(tx_no_id)


def test_missing_methods_raise_attribute_error():
    class BadStorage:
        pass

    repo = TransactionRepository(storage=BadStorage())

    with pytest.raises(AttributeError):
        repo.save({"account_id": "a"})

    with pytest.raises(AttributeError):
        repo.get("x")

    with pytest.raises(AttributeError):
        repo.delete("x")

    with pytest.raises(AttributeError):
        repo.list_all()

    with pytest.raises(AttributeError):
        repo.exists("x")


def test_list_for_account_uses_storage_specific_method_when_present():
    class FilterStorage(InMemoryStorage):
        def list_transactions_for_account(self, account_id):
            # reuse parent store but demonstrate the method is called
            return [t for t in self.list_transactions() if (isinstance(t, dict) and t.get("account_id") == account_id)]

    s = FilterStorage()
    # populate transactions
    t1 = {"transaction_id": "t1", "account_id": "acc-A"}
    t2 = {"transaction_id": "t2", "from_account": "acc-A"}
    t3 = {"transaction_id": "t3", "to_account": "other"}
    s.save_transaction(t1)
    s.save_transaction(t2)
    s.save_transaction(t3)

    repo = TransactionRepository(storage=s)
    found = repo.list_for_account("acc-A")
    ids = { (tx.get("transaction_id") if isinstance(tx, dict) else getattr(tx, "transaction_id")) for tx in found }
    assert {"t1", "t2"} <= ids


def test_list_for_account_fallback_filters_and_handles_bad_objects():
    # Generic storage that provides list_all (list_all) but no list_transactions_for_account
    class GenericListStorage:
        def __init__(self):
            self._store = {}

        def save(self, tx):
            tid = getattr(tx, "transaction_id", None) or (tx.get("transaction_id") if isinstance(tx, dict) else None) or "g1"
            self._store[tid] = tx
            return tid

        def list_all(self):
            return list(self._store.values())

        def get(self, tid):
            return self._store.get(tid)

        def delete(self, tid):
            if tid in self._store:
                del self._store[tid]
            else:
                raise KeyError(tid)

        def exists(self, tid):
            return tid in self._store

    gs = GenericListStorage()
    # mapping tx
    t1 = {"transaction_id": "t1", "account_id": "acc-A"}
    # attribute-like tx
    t2 = SimpleObj(transaction_id="t2", account_id="acc-A")
    # object that raises on attr access should be skipped safely
    bad = RaisesOnAttr()

    gs.save(t1)
    gs.save(t2)
    gs._store["bad"] = bad

    repo = TransactionRepository(storage=gs)
    found = repo.list_for_account("acc-A")
    ids = { (tx["transaction_id"] if isinstance(tx, dict) else getattr(tx, "transaction_id")) for tx in found }
    assert ids == {"t1", "t2"}


def test_init_without_storage_and_no_inmemory_raises(monkeypatch):
    import importlib
    mod = importlib.import_module('output.backend.transaction_repository')
    original = getattr(mod, 'InMemoryStorage', None)
    monkeypatch.setattr(mod, 'InMemoryStorage', None)
    try:
        with pytest.raises(RuntimeError):
            TransactionRepository(storage=None)
    finally:
        # restore for cleanliness
        monkeypatch.setattr(mod, 'InMemoryStorage', original)