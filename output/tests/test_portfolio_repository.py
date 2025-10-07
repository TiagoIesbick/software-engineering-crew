from decimal import Decimal
import pytest

from output.backend.portfolio_repository import PortfolioRepository
from output.backend.portfolio import Portfolio


class SimpleObj:
    def __init__(self, portfolio_id: str = None, owner: str = None, **kwargs):
        if portfolio_id is not None:
            self.portfolio_id = portfolio_id
        if owner is not None:
            self.owner = owner
        for k, v in kwargs.items():
            setattr(self, k, v)


class RaisesOnAttr:
    """Object that raises on attribute access to simulate introspection failures."""

    def __getattr__(self, name):
        raise RuntimeError("cannot access attributes")


def test_crud_with_default_inmemory_storage():
    repo = PortfolioRepository()

    p = Portfolio(portfolio_id='p-a', owner='alice')
    # save should store the portfolio (InMemoryStorage.save_portfolio returns None)
    res = repo.save(p)
    assert res is None

    assert repo.exists('p-a') is True

    got = repo.get('p-a')
    assert got is p
    assert got.owner == 'alice'

    listed = repo.list_all()
    assert any(x.portfolio_id == 'p-a' for x in listed)

    # delete should remove
    repo.delete('p-a')
    assert repo.exists('p-a') is False

    # deleting again should propagate KeyError
    with pytest.raises(KeyError):
        repo.delete('p-a')


def test_generic_storage_methods_delegation_and_return_values():
    # Generic storage that implements save/get/delete/list_all/exists (generic names)
    class GenericStorage:
        def __init__(self):
            self._store = {}

        def save(self, portfolio):
            # store and return a sentinel value
            self._store[portfolio.portfolio_id] = portfolio
            return 'SAVED'

        def get(self, portfolio_id):
            return self._store.get(portfolio_id)

        def delete(self, portfolio_id):
            if portfolio_id in self._store:
                del self._store[portfolio_id]
            else:
                raise KeyError(portfolio_id)

        def list_all(self):
            return list(self._store.values())

        def exists(self, portfolio_id):
            return portfolio_id in self._store

    gs = GenericStorage()
    repo = PortfolioRepository(storage=gs)

    p = Portfolio(portfolio_id='p-b', owner='bob')
    # repo.save should return the underlying save() return
    ret = repo.save(p)
    assert ret == 'SAVED'

    assert repo.exists('p-b') is True
    assert repo.get('p-b') is p
    assert any(x.portfolio_id == 'p-b' for x in repo.list_all())

    repo.delete('p-b')
    assert repo.exists('p-b') is False


def test_missing_methods_raise_attribute_error():
    class BadStorage:
        # intentionally no relevant methods
        pass

    repo = PortfolioRepository(storage=BadStorage())

    with pytest.raises(AttributeError):
        repo.save(Portfolio(portfolio_id='x', owner='o'))

    with pytest.raises(AttributeError):
        repo.get('x')

    with pytest.raises(AttributeError):
        repo.delete('x')

    with pytest.raises(AttributeError):
        repo.list_all()

    with pytest.raises(AttributeError):
        repo.exists('x')


def test_delete_propagates_storage_keyerror():
    repo = PortfolioRepository()
    with pytest.raises(KeyError):
        repo.delete('no-such')


def test_list_all_returns_a_separate_list_copy():
    repo = PortfolioRepository()
    p = Portfolio(portfolio_id='p-copy', owner='d')
    repo.save(p)

    l = repo.list_all()
    # modifying returned list should not remove stored portfolio
    l.clear()
    assert repo.exists('p-copy') is True
    assert any(x.portfolio_id == 'p-copy' for x in repo.list_all())


def test_init_without_storage_and_no_inmemory_raises(monkeypatch):
    import importlib
    mod = importlib.import_module('output.backend.portfolio_repository')
    original = getattr(mod, 'InMemoryStorage', None)
    monkeypatch.setattr(mod, 'InMemoryStorage', None)
    try:
        with pytest.raises(RuntimeError):
            PortfolioRepository(storage=None)
    finally:
        # restore
        monkeypatch.setattr(mod, 'InMemoryStorage', original)


def test_list_by_owner_uses_storage_specific_method_when_present():
    # Create a storage subclass that implements list_portfolios_by_owner
    from output.backend.storage import InMemoryStorage

    class FilterStorage(InMemoryStorage):
        def list_portfolios_by_owner(self, owner):
            return [p for p in self.list_portfolios() if (isinstance(p, dict) and p.get('owner') == owner) or (getattr(p, 'owner', None) == owner)]

    s = FilterStorage()
    p1 = {'portfolio_id': 'pa', 'owner': 'alice'}
    p2 = SimpleObj('pb', 'bob')
    p3 = {'portfolio_id': 'pc', 'owner': 'alice'}
    s.save_portfolio(p1)
    s.save_portfolio(p2)
    s.save_portfolio(p3)

    repo = PortfolioRepository(storage=s)
    found = repo.list_by_owner('alice')
    ids = { (x['portfolio_id'] if isinstance(x, dict) else getattr(x, 'portfolio_id')) for x in found }
    assert {'pa', 'pc'} <= ids


def test_list_by_owner_fallback_filters_and_handles_bad_objects():
    # Generic storage that provides list_all but no list_portfolios_by_owner
    class GenericListStorage:
        def __init__(self):
            self._store = {}

        def save(self, p):
            pid = getattr(p, 'portfolio_id', None) or (p.get('portfolio_id') if isinstance(p, dict) else None) or 'g1'
            self._store[pid] = p
            return pid

        def list_all(self):
            return list(self._store.values())

        def get(self, pid):
            return self._store.get(pid)

        def delete(self, pid):
            if pid in self._store:
                del self._store[pid]
            else:
                raise KeyError(pid)

        def exists(self, pid):
            return pid in self._store

    gs = GenericListStorage()
    t1 = {'portfolio_id': 't1', 'owner': 'ownerA'}
    t2 = SimpleObj('t2', 'ownerA')
    bad = RaisesOnAttr()

    gs.save(t1)
    gs.save(t2)
    gs._store['bad'] = bad

    repo = PortfolioRepository(storage=gs)
    found = repo.list_by_owner('ownerA')
    ids = { (x['portfolio_id'] if isinstance(x, dict) else getattr(x, 'portfolio_id')) for x in found }
    assert ids == {'t1', 't2'}