from decimal import Decimal
import re
import threading

import pytest

from output.backend.id_generator import IdGenerator


def test_default_id_format_and_uniqueness():
    gen = IdGenerator()
    acct_id = gen.generate_account_id()
    txn_id = gen.generate_transaction_id()

    # Prefixes
    assert acct_id.startswith('acct-')
    assert txn_id.startswith('txn-')

    # UID component should be present and look like a 32-char hex (uuid4 hex)
    parts = acct_id.split('-')
    assert parts[0] == 'acct'
    assert len(parts) == 2
    uid = parts[1]
    assert re.fullmatch(r"[0-9a-f]{32}", uid)

    # Account and transaction ids should be distinct
    assert acct_id != txn_id


def test_include_timestamp_and_counter_monotonicity():
    gen = IdGenerator(include_timestamp=True, include_counter=True)

    ids = [gen.generate_account_id() for _ in range(3)]

    # Expect format: prefix - timestamp - counter - uid
    for i, idv in enumerate(ids, start=1):
        parts = idv.split('-')
        assert parts[0] == 'acct'
        # timestamp should be numeric
        assert parts[1].isdigit()
        # counter starts at 1 and increments per instance
        assert parts[2] == str(i)
        # uid should be 32 hex chars by default
        assert re.fullmatch(r"[0-9a-f]{32}", parts[3])


def test_counter_is_instance_local():
    g1 = IdGenerator(include_counter=True)
    g2 = IdGenerator(include_counter=True)

    id1 = g1.generate_account_id()
    id2 = g2.generate_account_id()

    # Each generator's counter should start at 1 independently
    assert id1.split('-')[1] == '1' or id1.split('-')[1].isdigit()
    assert id2.split('-')[1] == '1' or id2.split('-')[1].isdigit()
    # Ensure both report counter '1' specifically when only counter is included
    g3 = IdGenerator(include_counter=True, include_timestamp=False)
    g4 = IdGenerator(include_counter=True, include_timestamp=False)
    assert g3.generate_account_id().split('-')[1] == '1'
    assert g4.generate_account_id().split('-')[1] == '1'


def test_short_uuid_reduces_uid_length():
    gen = IdGenerator(short_uuid=True)
    acct_id = gen.generate_account_id()
    parts = acct_id.split('-')
    # When short_uuid=True and no timestamp/counter, parts are [prefix, uid_short]
    assert parts[0] == 'acct'
    uid = parts[1]
    assert len(uid) == 12
    assert re.fullmatch(r"[0-9a-f]{12}", uid)


def test_custom_uid_fn_and_short_uuid_hyphen_handling():
    # custom uid with hyphens: should be stripped before truncation
    def my_uid():
        return 'aa-bb-cc-dd-ee-ff-112233'

    gen = IdGenerator(uid_fn=my_uid, short_uuid=True)
    acct_id = gen.generate_account_id()
    parts = acct_id.split('-')
    # uid should be first 12 chars of the hyphen-removed string
    expected_uid = my_uid().replace('-', '')[:12]
    assert parts[-1] == expected_uid


def test_invalid_prefix_values_raise():
    with pytest.raises(ValueError):
        IdGenerator(account_prefix='')
    with pytest.raises(ValueError):
        IdGenerator(transaction_prefix='')
    with pytest.raises(ValueError):
        IdGenerator(account_prefix=123)  # non-string
    with pytest.raises(ValueError):
        IdGenerator(transaction_prefix=None)


def test_generate_uuid_utility_lengths():
    long = IdGenerator.generate_uuid(short=False)
    short = IdGenerator.generate_uuid(short=True)
    assert isinstance(long, str) and len(long) == 32
    assert isinstance(short, str) and len(short) == 12
    assert re.fullmatch(r"[0-9a-f]{32}", long)
    assert re.fullmatch(r"[0-9a-f]{12}", short)


def test_transaction_prefix_respected():
    gen = IdGenerator(transaction_prefix='payment')
    tid = gen.generate_transaction_id()
    assert tid.startswith('payment-')


def test_thread_safety_of_counter_with_multiple_threads():
    gen = IdGenerator(include_counter=True)
    results = []

    def worker():
        results.append(gen.generate_account_id())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Extract counters and ensure they are unique and form a contiguous set 1..10
    counters = sorted(int(idv.split('-')[1]) for idv in results)
    assert counters == list(range(1, 11))