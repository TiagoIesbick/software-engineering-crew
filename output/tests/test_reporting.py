from decimal import Decimal
import pytest

from output.backend.reporting import ReportingService, ReportingError


class FakeAccount:
    def __init__(self, account_id, owner, balance, currency='USD'):
        self._account_id = account_id
        self.owner = owner
        self.balance = Decimal(balance)
        self.currency = currency

    def to_dict(self):
        return {
            'account_id': self._account_id,
            'owner': self.owner,
            'balance': format(self.balance, 'f'),
            'currency': self.currency,
        }

    def get_balance(self):
        # Return Decimal as expected by ReportingService
        return Decimal(self.balance)


class FakeHistoryService:
    def __init__(self, txs=None, holdings=None):
        self._txs = txs or []
        self._holdings = holdings or []

    def list_transactions_for_account(self, account_id):
        return list(self._txs)

    def holdings_snapshot(self, portfolio_id):
        return list(self._holdings)


class FakeValuation:
    def __init__(self, breakdown=None, realized=None, raise_on_breakdown=False):
        self.breakdown = breakdown or {'dummy': True}
        self.realized = realized if realized is not None else Decimal('0.00')
        self.raise_on_breakdown = raise_on_breakdown

    def portfolio_breakdown(self, holdings, price_overrides=None):
        if self.raise_on_breakdown:
            raise RuntimeError('valuation failure')
        return self.breakdown

    def realized_pl_from_transactions(self, transactions):
        return Decimal(self.realized)


class FakeTransactionRepo:
    def __init__(self, txs=None):
        self._txs = list(txs or [])

    def list_for_account(self, account_id):
        return list(self._txs)


class FakePortfolio:
    def __init__(self, holdings):
        # holdings: list of mapping or objects
        self._holdings = list(holdings)

    def list_holdings(self):
        return list(self._holdings)


class FakePortfolioRepo:
    def __init__(self, portfolio_map):
        self._map = dict(portfolio_map)

    def get(self, portfolio_id):
        return self._map.get(portfolio_id)


class BadAccountService:
    def get_account(self, account_id):
        raise RuntimeError('boom')


def test_account_summary_with_history_service_and_valuation():
    # Arrange
    acct = FakeAccount('acct-1', 'alice', '100.00')

    txs = [
        {'transaction_id': 't1', 'profit_loss': '1.23', 'created_at': '2020-01-01T00:00:00+00:00'},
        {'transaction_id': 't2', 'profit_loss': '2.27', 'created_at': '2020-01-02T00:00:00+00:00'},
    ]
    holdings = [
        {'symbol': 'AAPL', 'quantity': '2', 'average_cost': '150.00', 'currency': 'USD'},
    ]

    history = FakeHistoryService(txs=txs, holdings=holdings)
    valuation = FakeValuation(breakdown={'ok': True}, realized=Decimal('3.50'))

    svc = ReportingService(account_service=type('AS', (), {'get_account': lambda self, aid: acct})(),
                           history_service=history,
                           valuation_engine=valuation)

    # Act
    report = svc.account_summary('acct-1', portfolio_id='p1', include_transactions=True, include_holdings=True)

    # Assert
    assert report['account']['account_id'] == 'acct-1'
    assert report['balance'] == '100.00'
    assert isinstance(report['transactions'], list) and len(report['transactions']) == 2
    assert report['holdings'] == holdings
    assert report['valuation'] == {'ok': True}
    # realized_pl should be formatted string from valuation (3.50)
    assert report['realized_pl'] == '3.50'


def test_account_summary_uses_transaction_and_portfolio_repo_when_no_history():
    acct = FakeAccount('acct-2', 'bob', '50.00')

    txs = [
        {'transaction_id': 't10', 'profit_loss': '0.50'},
    ]
    tx_repo = FakeTransactionRepo(txs=txs)

    holdings = [
        {'symbol': 'TSLA', 'quantity': '1', 'average_cost': '720.50', 'currency': 'USD'},
    ]
    portfolio = FakePortfolio(holdings)
    port_repo = FakePortfolioRepo({'p2': portfolio})

    # Provide a valuation engine to avoid automatic instantiation complexities
    valuation = FakeValuation(breakdown={'x': 'y'}, realized=Decimal('0.50'))

    svc = ReportingService(account_service=type('AS2', (), {'get_account': lambda self, aid: acct})(),
                           transaction_repo=tx_repo,
                           portfolio_repo=port_repo,
                           valuation_engine=valuation)

    report = svc.account_summary('acct-2', portfolio_id='p2', include_transactions=True, include_holdings=True)

    assert report['account']['account_id'] == 'acct-2'
    assert report['balance'] == '50.00'
    # transaction repo was used
    assert len(report['transactions']) == 1
    # holdings normalized from portfolio.list_holdings
    assert len(report['holdings']) == 1
    # valuation included
    assert report['valuation'] == {'x': 'y'}
    assert report['realized_pl'] == '0.50'


def test_valuation_error_is_handled_gracefully_and_report_includes_error():
    acct = FakeAccount('acct-3', 'carl', '10.00')
    tx_repo = FakeTransactionRepo(txs=[])
    holdings = [{'symbol': 'X', 'quantity': '1', 'average_cost': '1.00'}]
    portfolio = FakePortfolio(holdings)
    port_repo = FakePortfolioRepo({'p3': portfolio})
    # valuation that will raise
    valuation = FakeValuation(raise_on_breakdown=True)

    svc = ReportingService(account_service=type('AS3', (), {'get_account': lambda self, aid: acct})(),
                           transaction_repo=tx_repo,
                           portfolio_repo=port_repo,
                           valuation_engine=valuation)

    report = svc.account_summary('acct-3', portfolio_id='p3')
    # valuation should be an error dict, not raise
    assert isinstance(report['valuation'], dict) and 'error' in report['valuation']


def test_realized_pl_fallback_without_valuation_and_error_on_invalid_profit_loss():
    acct = FakeAccount('acct-4', 'd', '20.00')

    # Transactions include one valid profit_loss and one invalid that should trigger ReportingError
    txs_valid = [
        {'transaction_id': 'tv1', 'profit_loss': '1.00'},
        {'transaction_id': 'tv2', 'profit_loss': None},
    ]
    tx_repo_valid = FakeTransactionRepo(txs=txs_valid)

    svc = ReportingService(account_service=type('AS4', (), {'get_account': lambda self, aid: acct})(),
                           transaction_repo=tx_repo_valid)
    # Remove valuation so fallback is used
    svc._valuation = None

    report = svc.account_summary('acct-4', portfolio_id=None)
    assert report['realized_pl'] == '1.00'

    # Now invalid profit_loss (non-coercible)
    txs_bad = [
        {'transaction_id': 'tb1', 'profit_loss': object()},
    ]
    tx_repo_bad = FakeTransactionRepo(txs=txs_bad)
    svc_bad = ReportingService(account_service=type('AS5', (), {'get_account': lambda self, aid: acct})(),
                               transaction_repo=tx_repo_bad)
    svc_bad._valuation = None

    with pytest.raises(ReportingError):
        svc_bad.account_summary('acct-4', portfolio_id=None)


def test_missing_account_service_and_account_lookup_failure_raise_reporting_error():
    # ReportingService without account_service should raise when account_service is None at call time
    svc = ReportingService(account_service=type('AS6', (), {'get_account': lambda self, aid: None})())
    # force no account service
    svc.account_service = None
    with pytest.raises(ReportingError):
        svc.account_summary('noacct')

    # If account lookup raises, it should be surfaced as ReportingError
    svc2 = ReportingService(account_service=BadAccountService())
    with pytest.raises(ReportingError):
        svc2.account_summary('acct-x')