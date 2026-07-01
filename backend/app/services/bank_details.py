"""Employee bank-detail validators.

Pure helpers — no DB. Endpoints use these to warn (never block) HR when
they enter a value that doesn't match the standard shape. The Section D
bank_advice report will list rows with `bank_valid=False` so Finance
can chase them BEFORE cutting the NEFT file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
# Indian bank account numbers vary (9-18 digits typically). Anything
# outside that band earns a warning, not a hard block.
ACCOUNT_MIN_LEN = 9
ACCOUNT_MAX_LEN = 18


@dataclass
class BankValidationResult:
    ok: bool
    warnings: List[str]

    @property
    def is_valid(self) -> bool:
        return self.ok


def validate_ifsc(ifsc: Optional[str]) -> BankValidationResult:
    """Return a validation result. `.ok=True` means "matches the standard
    RBI IFSC shape". Endpoints treat False as a WARN — never a hard
    block — because a few smaller banks / co-op banks can legitimately
    fail the regex."""
    warnings: List[str] = []
    if not ifsc:
        return BankValidationResult(ok=False, warnings=["IFSC is empty"])
    if not IFSC_REGEX.match(ifsc.strip().upper()):
        warnings.append(
            "IFSC does not match RBI shape (AAAA0NNNNNN — 4 alpha, 0, 6 alphanum)"
        )
        return BankValidationResult(ok=False, warnings=warnings)
    return BankValidationResult(ok=True, warnings=warnings)


def validate_account_number(account: Optional[str]) -> BankValidationResult:
    """Return a validation result. `.ok=True` means numeric + within
    the normal Indian bank account length band [9,18]."""
    warnings: List[str] = []
    if not account:
        return BankValidationResult(ok=False, warnings=["Account number is empty"])
    stripped = account.strip()
    if not stripped.isdigit():
        warnings.append("Account number contains non-numeric characters")
        return BankValidationResult(ok=False, warnings=warnings)
    n = len(stripped)
    if n < ACCOUNT_MIN_LEN or n > ACCOUNT_MAX_LEN:
        warnings.append(
            f"Account number length {n} is outside the usual "
            f"range [{ACCOUNT_MIN_LEN}, {ACCOUNT_MAX_LEN}] — "
            "double-check before NEFT"
        )
        return BankValidationResult(ok=False, warnings=warnings)
    return BankValidationResult(ok=True, warnings=warnings)


def validate_bank_bundle(
    *, ifsc: Optional[str], account: Optional[str],
    holder_name: Optional[str],
) -> BankValidationResult:
    """Convenience: run all field validators, return a merged result."""
    combined: List[str] = []
    ifsc_result = validate_ifsc(ifsc)
    combined.extend(ifsc_result.warnings)
    acct_result = validate_account_number(account)
    combined.extend(acct_result.warnings)
    if not holder_name or not holder_name.strip():
        combined.append("Account holder name is empty")
    ok = ifsc_result.ok and acct_result.ok and bool(
        holder_name and holder_name.strip()
    )
    return BankValidationResult(ok=ok, warnings=combined)


def bank_details_complete(
    *, account: Optional[str], ifsc: Optional[str],
    holder_name: Optional[str],
) -> bool:
    """A row is 'complete' if every required field is present AND
    passes shape validation. Used by NEFT file writer to decide whether
    to include the row or list it as a warning line."""
    return validate_bank_bundle(
        ifsc=ifsc, account=account, holder_name=holder_name,
    ).ok
