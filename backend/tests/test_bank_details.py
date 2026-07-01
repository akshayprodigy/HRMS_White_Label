"""Unit tests for bank-detail validators (Section K Item 1)."""
import pytest

from app.services.bank_details import (
    ACCOUNT_MAX_LEN, ACCOUNT_MIN_LEN, IFSC_REGEX,
    bank_details_complete, validate_account_number,
    validate_bank_bundle, validate_ifsc,
)


# ---------------------------------------------------------------------------
# IFSC
# ---------------------------------------------------------------------------


def test_valid_ifsc_passes():
    assert validate_ifsc("HDFC0001234").ok
    assert validate_ifsc("SBIN0000123").ok
    assert validate_ifsc("ICIC0AB1234").ok  # 4 alpha, 0, 6 alphanum


def test_ifsc_missing_is_warned_not_ok():
    r = validate_ifsc(None)
    assert not r.ok
    assert any("empty" in w.lower() for w in r.warnings)


def test_ifsc_wrong_shape_flagged():
    r = validate_ifsc("HDFC01234567")  # 4-0-7 chars, extra digit
    assert not r.ok
    assert any("RBI shape" in w for w in r.warnings)


def test_ifsc_lowercase_uppercased_and_matched():
    r = validate_ifsc("hdfc0001234")
    assert r.ok  # strip+upper before regex


def test_ifsc_regex_5th_char_must_be_zero():
    r = validate_ifsc("HDFC1001234")  # 5th char is 1, not 0
    assert not r.ok


# ---------------------------------------------------------------------------
# Account number
# ---------------------------------------------------------------------------


def test_valid_account_number_passes():
    assert validate_account_number("12345678901").ok
    assert validate_account_number("123456789").ok  # min band
    assert validate_account_number("123456789012345678").ok  # max band


def test_account_number_non_numeric_flagged():
    r = validate_account_number("1234ABC5678")
    assert not r.ok
    assert any("non-numeric" in w for w in r.warnings)


def test_account_number_too_short_flagged():
    r = validate_account_number("12345")
    assert not r.ok
    assert any(str(ACCOUNT_MIN_LEN) in w for w in r.warnings)


def test_account_number_too_long_flagged():
    r = validate_account_number("1" * (ACCOUNT_MAX_LEN + 1))
    assert not r.ok
    assert any(str(ACCOUNT_MAX_LEN) in w for w in r.warnings)


def test_account_number_missing_flagged():
    r = validate_account_number(None)
    assert not r.ok


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


def test_bank_bundle_all_valid_passes():
    r = validate_bank_bundle(
        ifsc="HDFC0001234", account="12345678901", holder_name="Alice Kumar",
    )
    assert r.ok
    assert r.warnings == []


def test_bank_bundle_missing_holder_flagged():
    r = validate_bank_bundle(
        ifsc="HDFC0001234", account="12345678901", holder_name="",
    )
    assert not r.ok
    assert any("holder" in w.lower() for w in r.warnings)


def test_bank_bundle_bad_ifsc_and_short_acct_lists_both():
    r = validate_bank_bundle(
        ifsc="BADIFSC", account="123", holder_name="Alice",
    )
    assert not r.ok
    assert len(r.warnings) >= 2


def test_bank_details_complete_true_only_when_shape_valid():
    assert bank_details_complete(
        account="12345678901", ifsc="HDFC0001234", holder_name="Alice",
    )
    assert not bank_details_complete(
        account="12345678901", ifsc="BADIFSC", holder_name="Alice",
    )
    assert not bank_details_complete(
        account=None, ifsc="HDFC0001234", holder_name="Alice",
    )
