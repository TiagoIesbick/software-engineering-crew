from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest

from output.backend.history import HistoryService, HistoryError


class ObjWithToDict:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


class AttrObj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class RaisesOnAttr:
    def __getattr__(self, name):
        raise RuntimeError("cannot access")


def test_list_transactions_for_account_normalizes_and_sorts():
    # Prepare three transactions with different created_at values and shapes
    # Oldest: dict without created_at -> will be treated as epoch sentinel
    t_old = {"transaction_id": "old", "kind": "deposit", "amount": "1.00"}

    # Middle: object with to_dict and created_at as ISO string
    t_mid_obj = ObjWithToDict({
        "transaction_id": "mid",
        "kind": "withdrawal",
        "amount": "2.00",
        "created_at": "2020-01-02T12:00:00+00:00",
    })

    # Newest: attribute object with created_at as aware datetime
    newest_dt = datetime(2021, 1, 3, 15, 0, 0, tzinfo=timezone.utc)
    t_new_attr = AttrObj(transaction_id="new", kind="deposit", amount="3.00", created_at=newest_dt)

    repo = type("R", (), {"list_for_account": lambda self, aid: [t_old, t_mid_obj, t_new_attr]})()

    svc = HistoryService(transaction_repo=repo)
    out = svc.list_transactions_for_account("any")

    # All items normalized to dicts
    assert all(isinstance(x, dict) for x in out)

    # Expect newest first (created_at: newest_dt, then t_mid, then t_old which lacks created_at)
    ids_in_order = [d.get("transaction_id") for d in out]
    assert ids_in_order == ["new", "mid", "old"]

    # Ensure created_at preserved in normalized dicts when present
    assert out[0]["created_at"] == newest_dt
    assert out[1]["created_at"] == "2020-01-02T12:00:00+00:00"


def test_transactions_between_filters_by_inclusive_range_and_includes_unknown_dates():
    # Create three txs with explicit created_at datetimes
    base = datetime(2020, 6, 1, tzinfo=timezone.utc)
    t_before = {"transaction_id": "b", "created_at": (base - timedelta(days=2)).isoformat()}
    t_during = {"transaction_id": "m", "created_at": (base).isoformat()}
    t_after = {"transaction_id": "a", "created_at": (base + timedelta(days=2)).isoformat()}
    # And one without a date which should be included by the implementation
    t_nodate = {"transaction_id": "x"}

    repo = type("R2", (), {"list_for_account": lambda self, aid: [t_before, t_during, t_after, t_nodate]})()
    svc = HistoryService(transaction_repo=repo)

    # Range inclusive: start=base, end=base -> should include t_during and t_nodate
    res = svc.transactions_between("a", start=base.isoformat(), end=base.isoformat())
    ids = {r["transaction_id"] for r in res}
    assert "m" in ids
    # t_nodate has no created_at -> implementation includes unknown-date txs conservatively
    assert "x" in ids
    assert "b" not in ids and "a" not in ids


def test_holdings_snapshot_normalizes_various_holding_shapes_and_handles_unintrospectable():
    # holdings: mapping, object with to_dict, attribute object, raises-on-attr
    h_map = {"symbol": "A", "quantity": "1", "average_cost": "10.00", "currency": "USD"}

    class HWithToDict:
        def to_dict(self):
            return {"symbol": "B", "quantity": "2", "average_cost": "5.00", "currency": "EUR"}

    h_attr = AttrObj(symbol="C", quantity="3", average_cost="1.00", currency="GBP")
    h_bad = RaisesOnAttr()

    # portfolio object exposing list_holdings()
    class Port:
        def list_holdings(self):
            return [h_map, HWithToDict(), h_attr, h_bad]

    port_repo = type("PRepo", (), {"get": lambda self, pid: Port()})()
    svc = HistoryService(portfolio_repo=port_repo)

    snap = svc.holdings_snapshot("p1")
    # Expect 4 entries
    assert isinstance(snap, list) and len(snap) == 4

    # First should match mapping copy
    assert snap[0]["symbol"] == "A"
    # Second should come from to_dict
    assert snap[1]["symbol"] == "B"
    # Third should be from attributes
    assert snap[2]["symbol"] == "C"
    # Fourth couldn't be introspected -> should include a 'repr' key
    assert "repr" in snap[3]


def test_holdings_snapshot_raises_keyerror_when_portfolio_missing_and_repo_get_missing_raises_historyerror():
    # repo.get returns None -> holdings_snapshot should raise KeyError
    repo_none = type("RNone", (), {"get": lambda self, pid: None})()
    svc_none = HistoryService(portfolio_repo=repo_none)
    with pytest.raises(KeyError):
        svc_none.holdings_snapshot("no-such")

    # repo lacking get method should cause HistoryError
    class BadRepo:
        pass

    svc_bad = HistoryService(portfolio_repo=BadRepo())
    with pytest.raises(HistoryError):
        svc_bad.holdings_snapshot("pid")


def test_account_snapshot_combines_transactions_and_holdings_and_handles_missing_portfolio():
    # transaction repo that returns a couple of tx dicts
    tx1 = {"transaction_id": "t1", "created_at": "2020-01-01T00:00:00+00:00"}
    tx2 = {"transaction_id": "t2"}
    tx_repo = type("TR", (), {"list_for_account": lambda self, aid: [tx1, tx2]})()

    # portfolio repo that returns None for missing portfolio
    port_repo = type("PR", (), {"get": lambda self, pid: None})()

    svc = HistoryService(transaction_repo=tx_repo, portfolio_repo=port_repo)

    # include_transactions True, include_holdings True but portfolio missing => holdings becomes []
    snap = svc.account_snapshot(account_id="acct", portfolio_id="missing", include_transactions=True, include_holdings=True)
    assert "transactions" in snap and isinstance(snap["transactions"], list)
    assert snap.get("holdings") == []

    # If include_holdings False, holdings key should be absent
    snap2 = svc.account_snapshot(account_id="acct", portfolio_id="missing", include_transactions=True, include_holdings=False)
    assert "transactions" in snap2
    assert "holdings" not in snap2

    # If transaction repo is missing list_for_account, the call should raise HistoryError
    class BadTxRepo:
        pass

    svc_badtx = HistoryService(transaction_repo=BadTxRepo(), portfolio_repo=port_repo)
    with pytest.raises(HistoryError):
        svc_badtx.account_snapshot(account_id="a", portfolio_id=None)