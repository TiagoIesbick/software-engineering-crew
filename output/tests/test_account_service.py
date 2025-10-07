from decimal import Decimal
import pytest

from output.backend.account_service import (
    AccountService,
    AccountServiceError,
    AccountNotFoundError,
    AccountAlreadyExistsError,
)
from output.backend.accounts import (
    Account,
    InvalidAmountError,
    InsufficientFundsError,
)


def test_create_get_list_and_close_account_lifecycle():
    svc = AccountService()

    # Create two accounts
    a1 = svc.create_account(owner='alice', initial_deposit='10.00', account_id='acct-1')
    a2 = svc.create_account(owner='bob', initial_deposit='5.00', account_id='acct-2')

    # list_accounts should include both
    all_accts = svc.list_accounts()
    ids = {a.account_id for a in all_accts}
    assert 'acct-1' in ids and 'acct-2' in ids

    # get_account returns the account
    got = svc.get_account('acct-1')
    assert got.owner == 'alice'
    assert got.get_balance() == Decimal('10.00')

    # close_account removes the account
    svc.close_account('acct-2')
    with pytest.raises(AccountNotFoundError):
        svc.get_account('acct-2')


def test_create_with_duplicate_account_id_raises():
    svc = AccountService()
    svc.create_account(owner='carol', initial_deposit='1.00', account_id='dup-id')
    with pytest.raises(AccountAlreadyExistsError):
        svc.create_account(owner='carol', initial_deposit='2.00', account_id='dup-id')


def test_deposit_and_withdraw_persist_and_errors():
    svc = AccountService()
    acct = svc.create_account(owner='dave', initial_deposit='20.00', account_id='dave-1')

    # Deposit positive amount
    new_bal = svc.deposit('dave-1', '5.25')
    assert new_bal == Decimal('25.25')
    assert svc.get_account('dave-1').get_balance() == Decimal('25.25')

    # Withdraw some amount
    new_bal = svc.withdraw('dave-1', '0.25')
    assert new_bal == Decimal('25.00')
    assert svc.get_account('dave-1').get_balance() == Decimal('25.00')

    # Withdraw invalid amount (zero)
    with pytest.raises(InvalidAmountError):
        svc.withdraw('dave-1', 0)

    # Withdraw too much
    with pytest.raises(InsufficientFundsError):
        svc.withdraw('dave-1', '1000.00')


def test_transfer_success_and_persistence():
    svc = AccountService()
    from_acct = svc.create_account(owner='erin', initial_deposit='50.00', account_id='from-1')
    to_acct = svc.create_account(owner='frank', initial_deposit='10.00', account_id='to-1')

    from_new, to_new = svc.transfer('from-1', 'to-1', '15.00')
    assert from_new == Decimal('35.00')
    assert to_new == Decimal('25.00')

    # Ensure persisted
    assert svc.get_account('from-1').get_balance() == Decimal('35.00')
    assert svc.get_account('to-1').get_balance() == Decimal('25.00')


def test_transfer_insufficient_funds_does_not_change_balances():
    svc = AccountService()
    svc.create_account(owner='gina', initial_deposit='5.00', account_id='g-1')
    svc.create_account(owner='harry', initial_deposit='1.00', account_id='h-1')

    before_from = svc.get_account('g-1').get_balance()
    before_to = svc.get_account('h-1').get_balance()

    with pytest.raises(InsufficientFundsError):
        svc.transfer('g-1', 'h-1', '10.00')

    # balances unchanged
    assert svc.get_account('g-1').get_balance() == before_from
    assert svc.get_account('h-1').get_balance() == before_to


def test_transfer_to_same_account_raises():
    svc = AccountService()
    svc.create_account(owner='ivy', initial_deposit='3.00', account_id='same-1')
    with pytest.raises(AccountServiceError):
        svc.transfer('same-1', 'same-1', '1.00')


def test_transfer_deposit_failure_rolls_back():
    "Simulate a deposit failure on the destination account and ensure the\n    service rolls back the withdrawal on the source account."
    svc = AccountService()

    # Normal source account
    from_acct = Account.create(owner='jack', initial_deposit='30.00', account_id='jack-1')

    # Create a BrokenAccount subclass that raises on deposit
    class BrokenAccount(Account):
        def deposit(self, amount: object) -> Decimal:
            raise RuntimeError('simulated deposit failure')

    broken = BrokenAccount(owner='jill', initial_deposit='5.00', account_id='jill-1')

    # Persist both directly into the repository so get_account will return them
    svc._repo.save(from_acct)
    svc._repo.save(broken)

    before_from = svc.get_account('jack-1').get_balance()
    before_to = svc.get_account('jill-1').get_balance()

    with pytest.raises(RuntimeError):
        svc.transfer('jack-1', 'jill-1', '10.00')

    # After a failed transfer the service should have rolled back the withdrawal
    assert svc.get_account('jack-1').get_balance() == before_from
    assert svc.get_account('jill-1').get_balance() == before_to


def test_close_account_nonexistent_raises_and_get_account_not_found():
    svc = AccountService()
    with pytest.raises(AccountNotFoundError):
        svc.close_account('no-such')

    with pytest.raises(AccountNotFoundError):
        svc.get_account('no-such')