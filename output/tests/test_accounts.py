from decimal import Decimal
import pytest

from output.backend.accounts import (
    Account,
    InvalidAmountError,
    InsufficientFundsError,
)


def test_create_account_defaults():
    acct = Account.create(owner='alice')
    assert acct.owner == 'alice'
    assert isinstance(acct.account_id, str) and acct.account_id
    assert acct.currency == 'USD'
    assert acct.get_balance() == Decimal('0.00')
    d = acct.to_dict()
    assert d['owner'] == 'alice'
    assert d['account_id'] == acct.account_id
    assert d['balance'] == '0.00'
    assert d['currency'] == 'USD'


@pytest.mark.parametrize(
    "initial,expected",
    [
        (100, Decimal('100.00')),
        ("12.3", Decimal('12.30')),
        (Decimal('7.777'), Decimal('7.78')),
        (0.105, Decimal('0.11')),
    ],
)
def test_create_with_various_initial_deposits(initial, expected):
    acct = Account.create(owner='bob', initial_deposit=initial, currency='CAD', account_id='id-1')
    assert acct.owner == 'bob'
    assert acct.account_id == 'id-1'
    assert acct.currency == 'CAD'
    assert acct.get_balance() == expected


def test_create_requires_owner_and_rejects_negative_initial_deposit():
    with pytest.raises(ValueError):
        Account.create(owner='')

    with pytest.raises(InvalidAmountError):
        Account.create(owner='carol', initial_deposit='-1.00')


def test_negative_balance_on_direct_instantiation_raises():
    # Direct dataclass instantiation should validate balance in __post_init__
    with pytest.raises(InvalidAmountError):
        Account(owner='dan', balance=Decimal('-0.01'))


def test_deposit_and_withdraw_sequence():
    acct = Account.create(owner='erin', initial_deposit='10.00')
    new_bal = acct.deposit('5.50')
    assert new_bal == Decimal('15.50')
    assert acct.get_balance() == Decimal('15.50')

    new_bal = acct.withdraw('3.25')
    assert new_bal == Decimal('12.25')
    assert acct.get_balance() == Decimal('12.25')


@pytest.mark.parametrize("amt", [0, '0.00', -1, '-5.00'])
def test_deposit_invalid_amounts_raise(amt):
    acct = Account.create(owner='frank')
    with pytest.raises(InvalidAmountError):
        acct.deposit(amt)


def test_deposit_unconvertible_amount_raises():
    acct = Account.create(owner='gina')
    with pytest.raises(InvalidAmountError):
        acct.deposit(object())


def test_withdraw_invalid_and_insufficient_funds():
    acct = Account.create(owner='harry', initial_deposit='2.00')
    with pytest.raises(InvalidAmountError):
        acct.withdraw(0)

    with pytest.raises(InsufficientFundsError):
        acct.withdraw('3.00')

    # withdrawing exact balance should succeed and leave zero
    new_bal = acct.withdraw('2.00')
    assert new_bal == Decimal('0.00')
    assert acct.get_balance() == Decimal('0.00')


def test_rounding_behavior_for_floats():
    acct = Account.create(owner='ivy')
    # Deposit 0.105 -> should be rounded to 0.11
    acct.deposit(0.105)
    assert acct.get_balance() == Decimal('0.11')

    # Withdraw 0.055 -> rounded to 0.06, leaving 0.05
    acct.withdraw(0.055)
    assert acct.get_balance() == Decimal('0.05')


def test_get_balance_returns_quantized_copy_and_is_immutable_from_caller():
    acct = Account.create(owner='jack', initial_deposit='1.234')
    # initial_deposit '1.234' rounded half-up to '1.23'
    b = acct.get_balance()
    assert b == Decimal('1.23')
    # manipulating returned Decimal should not affect account internal balance
    bumped = b + Decimal('1.00')
    assert bumped == Decimal('2.23')
    assert acct.get_balance() == Decimal('1.23')


def test_to_dict_and_repr_include_core_fields():
    acct = Account.create(owner='kate', initial_deposit='2.00', currency='EUR', account_id='acct-123')
    d = acct.to_dict()
    assert d['account_id'] == 'acct-123'
    assert d['owner'] == 'kate'
    assert d['balance'] == '2.00'
    assert d['currency'] == 'EUR'

    r = repr(acct)
    assert 'acct-123' in r
    assert 'kate' in r
    assert "'2.00'" in r or '2.00' in r