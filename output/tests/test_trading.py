from decimal import Decimal
import pytest

from output.backend.trading import TradingEngine, TradingError
from output.backend.account_service import AccountService
from output.backend.portfolio_repository import PortfolioRepository
from output.backend.transaction_repository import TransactionRepository
from output.backend.pricing import PriceService
from output.backend.validators import InsufficientFundsError, InsufficientHoldingsError
from output.backend.portfolio import Portfolio


def test_buy_with_market_price_successful():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    # create account and portfolio
    acct_svc.create_account(owner='alice', initial_deposit='1000.00', account_id='acct-1')
    p = Portfolio(portfolio_id='p1', owner='alice', account_id='acct-1')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo, price_service=PriceService())

    tx = engine.buy(account_id='acct-1', portfolio_id='p1', symbol='AAPL', quantity='2', use_market_price=True)

    # AAPL price is 150.00, amount should be 300.00
    assert tx.amount == Decimal('300.00')

    # Account balance decreased
    acct = acct_svc.get_account('acct-1')
    assert acct.get_balance() == Decimal('700.00')

    # Holding created and quantity updated
    holding = port_repo.get('p1').get_holding('AAPL')
    assert holding is not None
    assert holding.quantity == Decimal('2').quantize(Decimal('0.00000001'))

    # Transaction persisted in transaction repository
    assert tx_repo.get(tx.transaction_id) is not None


def test_buy_insufficient_funds_raises_and_no_side_effects():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    acct_svc.create_account(owner='bob', initial_deposit='10.00', account_id='acct-2')
    p = Portfolio(portfolio_id='p2', owner='bob', account_id='acct-2')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo)

    with pytest.raises(InsufficientFundsError):
        engine.buy(account_id='acct-2', portfolio_id='p2', symbol='AAPL', quantity='1', use_market_price=True)

    # Ensure account balance unchanged and no holding created
    acct = acct_svc.get_account('acct-2')
    assert acct.get_balance() == Decimal('10.00')
    assert port_repo.get('p2').get_holding('AAPL') is None


def test_buy_portfolio_not_found_rolls_back_account():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    acct_svc.create_account(owner='carol', initial_deposit='500.00', account_id='acct-3')

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo)

    # portfolio 'missing-p' does not exist; buy should attempt withdraw then refund
    with pytest.raises(TradingError):
        engine.buy(account_id='acct-3', portfolio_id='missing-p', symbol='AAPL', quantity='1', use_market_price=True)

    # balance should have been refunded to original
    acct = acct_svc.get_account('acct-3')
    assert acct.get_balance() == Decimal('500.00')


def test_buy_transaction_persist_failure_rolls_back_portfolio_and_account():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()

    class FailingTransactionRepo:
        def __init__(self):
            self._store = {}

        def save(self, transaction):
            raise RuntimeError('simulated persist failure')

        def get(self, tid):
            return self._store.get(tid)

        def delete(self, tid):
            if tid in self._store:
                del self._store[tid]
            else:
                raise KeyError(tid)

        def list_all(self):
            return list(self._store.values())

        def exists(self, tid):
            return tid in self._store

        def list_for_account(self, account_id):
            return [t for t in self._store.values() if getattr(t, 'account_id', None) == account_id or (isinstance(t, dict) and t.get('account_id') == account_id)]

    failing_tx_repo = FailingTransactionRepo()

    # create account and portfolio
    acct_svc.create_account(owner='dave', initial_deposit='1000.00', account_id='acct-4')
    p = Portfolio(portfolio_id='p4', owner='dave', account_id='acct-4')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=failing_tx_repo)

    with pytest.raises(TradingError):
        engine.buy(account_id='acct-4', portfolio_id='p4', symbol='AAPL', quantity='1', use_market_price=True)

    # Ensure account balance was restored and portfolio has no holding (rollback succeeded)
    acct = acct_svc.get_account('acct-4')
    assert acct.get_balance() == Decimal('1000.00')
    assert port_repo.get('p4').get_holding('AAPL') is None


def test_sell_successful_deposits_and_records_transaction():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    # Create account with small starting balance
    acct_svc.create_account(owner='erin', initial_deposit='0.00', account_id='acct-5')

    # Create portfolio and add a holding
    p = Portfolio(portfolio_id='p5', owner='erin', account_id='acct-5')
    # set a holding directly via buy to ensure correct normalization
    p.buy('AAPL', quantity='5', price='100.00')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo)

    tx = engine.sell(account_id='acct-5', portfolio_id='p5', symbol='AAPL', quantity='2', price='150.00', use_market_price=False)

    # Amount = 2 * 150 = 300.00 deposited to account
    acct = acct_svc.get_account('acct-5')
    assert acct.get_balance() == Decimal('300.00')

    # Holding quantity reduced to 3
    holding = port_repo.get('p5').get_holding('AAPL')
    assert holding is not None
    assert holding.quantity == Decimal('3').quantize(Decimal('0.00000001'))

    # Transaction persisted
    assert tx_repo.get(tx.transaction_id) is not None


def test_sell_insufficient_holdings_raises_and_no_side_effects():
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    acct_svc.create_account(owner='frank', initial_deposit='0.00', account_id='acct-6')
    p = Portfolio(portfolio_id='p6', owner='frank', account_id='acct-6')
    p.buy('TSLA', quantity='1', price='100.00')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo)

    with pytest.raises(InsufficientHoldingsError):
        engine.sell(account_id='acct-6', portfolio_id='p6', symbol='TSLA', quantity='2', price='200.00', use_market_price=False)

    # ensure nothing changed
    assert acct_svc.get_account('acct-6').get_balance() == Decimal('0.00')
    assert port_repo.get('p6').get_holding('TSLA').quantity == Decimal('1').quantize(Decimal('0.00000001'))


def test_resolve_price_failure_raises_trading_error_for_market_price():
    # Using a symbol not supported by PriceService should raise TradingError when use_market_price=True
    acct_svc = AccountService()
    port_repo = PortfolioRepository()
    tx_repo = TransactionRepository()

    acct_svc.create_account(owner='gary', initial_deposit='100.00', account_id='acct-7')
    p = Portfolio(portfolio_id='p7', owner='gary', account_id='acct-7')
    port_repo.save(p)

    engine = TradingEngine(account_service=acct_svc, portfolio_repo=port_repo, transaction_repo=tx_repo, price_service=PriceService())

    with pytest.raises(TradingError):
        engine.buy(account_id='acct-7', portfolio_id='p7', symbol='UNKNOWN', quantity='1', use_market_price=True)


def test_get_portfolio_holdings_portfolio_not_found_raises():
    engine = TradingEngine()
    with pytest.raises(TradingError):
        engine.get_portfolio_holdings('no-such')


def test_list_transactions_for_account_forwards_to_repo():
    tx_repo = TransactionRepository()

    # Create a couple of transactions directly via repo save
    # Use dict transactions so repository assigns ids
    t1 = {'account_id': 'acct-X', 'amount': 10}
    t2 = {'account_id': 'acct-X', 'amount': 20}
    tid1 = tx_repo.save(t1)
    tid2 = tx_repo.save(t2)

    engine = TradingEngine(transaction_repo=tx_repo)
    found = engine.list_transactions_for_account('acct-X')
    # ensure both returned
    ids = { (tx.get('transaction_id') if isinstance(tx, dict) else getattr(tx, 'transaction_id')) for tx in found }
    assert {tid1, tid2} <= ids