from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from dataclasses import FrozenInstanceError
import pytest

from output.backend.transaction import (
    Transaction,
    InvalidTransactionError,
    TransactionError,
)


def test_deposit_transaction_basics_and_to_dict():
    # deposit amount should be quantized to cents and created_at timezone-aware
    tx = Transaction.deposit(account_id='acct-1', amount='10.125')
    assert tx.kind == 'deposit'
    # 10.125 -> 10.13 with ROUND_HALF_UP
    assert tx.amount == Decimal('10.13')
    assert tx.account_id == 'acct-1'
    assert tx.transaction_id
    assert tx.created_at.tzinfo is not None

    d = tx.to_dict()
    assert d['kind'] == 'deposit'
    assert d['account_id'] == 'acct-1'
    assert d['amount'] == '10.13'
    # created_at should be ISO string
    assert isinstance(d['created_at'], str) and d['created_at'].endswith('+00:00')


def test_withdrawal_requires_account_and_positive_amount():
    # Missing account_id should raise during post-init
    with pytest.raises(InvalidTransactionError):
        Transaction.withdrawal(account_id=None, amount='1.00')

    # Negative or zero amount should raise
    with pytest.raises(InvalidTransactionError):
        Transaction.withdrawal(account_id='a', amount='0')

    with pytest.raises(InvalidTransactionError):
        Transaction.withdrawal(account_id='a', amount='-5.00')


def test_trade_buy_computes_amount_and_quantizes_fields():
    # Use values that require quantization
    qty_in = '1.234567891'  # will be quantized to 8 dp
    price_in = '2.345'      # will be quantized to cents

    tx = Transaction.trade(account_id='tr-1', side='buy', quantity=qty_in, price=price_in)

    # quantity quantized to 8 decimal places
    expected_qty = Decimal(qty_in).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
    assert tx.quantity == expected_qty

    # price quantized to cents
    expected_price = Decimal(price_in).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    assert tx.price == expected_price

    # amount = qty * price quantized to cents
    expected_amount = (expected_qty * expected_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    assert tx.amount == expected_amount

    # to_dict should represent numbers as strings
    d = tx.to_dict()
    assert d['quantity'] == format(expected_qty, 'f')
    assert d['price'] == format(expected_price, 'f')
    assert d['amount'] == format(expected_amount, 'f')


def test_trade_side_validation_and_invalid_values():
    # invalid side
    with pytest.raises(InvalidTransactionError):
        Transaction.trade(account_id='x', side='hold', quantity='1', price='1')

    # missing quantity results in InvalidTransactionError from _to_quantity when None is passed
    with pytest.raises(InvalidTransactionError):
        Transaction.trade(account_id='x', side='buy', quantity=None, price='1')

    # negative quantity
    with pytest.raises(InvalidTransactionError):
        Transaction.trade(account_id='x', side='sell', quantity='-1', price='1')

    # zero price
    with pytest.raises(InvalidTransactionError):
        Transaction.trade(account_id='x', side='sell', quantity='1', price='0')


def test_profit_loss_normalization_and_invalid_profit_loss():
    # valid profit_loss should be normalized to cents
    tx = Transaction.trade(account_id='acct-pl', side='buy', quantity='1', price='2', profit_loss='0.555')
    # profit_loss 0.555 -> 0.56
    assert tx.profit_loss == Decimal('0.56')

    # invalid profit_loss should raise
    with pytest.raises(InvalidTransactionError):
        Transaction.trade(account_id='acct-pl', side='sell', quantity='1', price='1', profit_loss='not-a-number')


def test_immutability_of_transaction():
    tx = Transaction.deposit(account_id='im', amount='1.00')
    with pytest.raises(FrozenInstanceError):
        tx.amount = Decimal('2.00')


def test_invalid_kind_on_direct_construction():
    # Directly constructing with invalid kind should raise
    with pytest.raises(InvalidTransactionError):
        Transaction(transaction_id='t1', kind='unknown', account_id='a', amount='1.00')


def test_transaction_id_auto_and_provided_and_uniqueness():
    t1 = Transaction.deposit(account_id='u1', amount='1.00')
    t2 = Transaction.deposit(account_id='u1', amount='1.00')
    assert t1.transaction_id != t2.transaction_id

    # Provided id respected
    t3 = Transaction.deposit(account_id='u2', amount='2.00', transaction_id='fixed-id')
    assert t3.transaction_id == 'fixed-id'


def test_created_at_naive_is_converted_to_utc():
    naive = datetime(2020, 1, 1, 12, 0, 0)  # naive datetime
    tx = Transaction.deposit(account_id='naive', amount='1.00', created_at=naive)
    assert tx.created_at.tzinfo is not None
    assert tx.created_at.tzinfo == timezone.utc


def test_repr_contains_core_information():
    tx = Transaction.deposit(account_id='r1', amount='3.50', transaction_id='repr-1')
    r = repr(tx)
    assert 'repr-1' in r
    assert "'3.50'" in r or '3.50' in r