from decimal import Decimal
import pytest

import importlib

from output.backend.account_repository import AccountRepository
from output.backend.accounts import Account

# Access the module object for some tests
import output.backend.account_repository as account_repository_mod


def test_crud_with_default_inmemory_storage():
    repo = AccountRepository()

    acct = Account.create(owner='alice', initial_deposit='10.00', account_id='acct-a')
    # save should store the account
    repo.save(acct)

    assert repo.exists('acct-a') is True

    got = repo.get('acct-a')
    assert got is acct
    assert got.get_balance() == Decimal('10.00')

    listed = repo.list_all()
    assert any(a.account_id == 'acct-a' for a in listed)

    # delete should remove
    repo.delete('acct-a')
    assert repo.exists('acct-a') is False

    # deleting again should propagate KeyError
    with pytest.raises(KeyError):
        repo.delete('acct-a')


def test_generic_storage_methods_delegation_and_return_values():
    # A generic storage that implements save/get/delete/list_all/exists (generic names)
    class GenericStorage:
        def __init__(self):
            self._store = {}

        def save(self, account):
            self._store[account.account_id] = account
            return 'SAVED'

        def get(self, account_id):
            return self._store.get(account_id)

        def delete(self, account_id):
            if account_id in self._store:
                del self._store[account_id]
            else:
                raise KeyError(account_id)

        def list_all(self):
            return list(self._store.values())

        def exists(self, account_id):
            return account_id in self._store

    gs = GenericStorage()
    repo = AccountRepository(storage=gs)

    acct = Account.create(owner='bob', initial_deposit='5.00', account_id='acct-b')
    # repo.save should return the underlying save() return
    res = repo.save(acct)
    assert res == 'SAVED'

    assert repo.exists('acct-b') is True
    assert repo.get('acct-b') is acct
    assert any(a.account_id == 'acct-b' for a in repo.list_all())

    repo.delete('acct-b')
    assert repo.exists('acct-b') is False


def test_missing_methods_raise_attribute_error():
    class BadStorage:
        # intentionally no relevant methods
        pass

    repo = AccountRepository(storage=BadStorage())

    # save should raise AttributeError because neither save_account nor save exist
    with pytest.raises(AttributeError):
        repo.save(Account.create(owner='c', account_id='c1'))

    with pytest.raises(AttributeError):
        repo.get('x')

    with pytest.raises(AttributeError):
        repo.delete('x')

    with pytest.raises(AttributeError):
        repo.list_all()

    with pytest.raises(AttributeError):
        repo.exists('x')


def test_delete_propagates_storage_keyerror():
    repo = AccountRepository()
    # Ensure deleting a non-existent id raises KeyError from underlying storage
    with pytest.raises(KeyError):
        repo.delete('no-such')


def test_list_all_returns_a_separate_list_copy():
    repo = AccountRepository()
    acct = Account.create(owner='d', account_id='d-1')
    repo.save(acct)

    l = repo.list_all()
    # modifying the returned list should not remove the stored account
    l.clear()
    assert repo.exists('d-1') is True
    # the repository's list_all should still show the account
    assert any(a.account_id == 'd-1' for a in repo.list_all())


def test_init_without_storage_and_no_inmemory_raises(monkeypatch):
    # Simulate the scenario where InMemoryStorage is unavailable
    # by patching the module-level InMemoryStorage to None
    original = getattr(account_repository_mod, 'InMemoryStorage', None)
    monkeypatch.setattr(account_repository_mod, 'InMemoryStorage', None)
    try:
        with pytest.raises(RuntimeError):
            AccountRepository(storage=None)
    finally:
        # monkeypatch fixture will restore automatically at test end, but keep this for clarity
        monkeypatch.setattr(account_repository_mod, 'InMemoryStorage', original)