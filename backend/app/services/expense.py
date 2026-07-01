"""Expense/Travel pure helpers — policy checks, reimbursement decisions,
double-pay guard, travel advance reconciliation.

DB-free. Callers pass in plain dict-shaped inputs. All money is in paise.

Constants (documented + tested):
- REIMBURSE_DEFAULT_MODE = "direct"
  Per HR-configured toggle; direct = Finance marks reimbursed with a
  reference. "payroll" injects a non-taxable line into the next draft
  run. Never both (the double-pay guard enforces this).
- POLICY_DEFAULT_MODE    = "warn"
  Policy violations flag but do not block by default. Categories can
  override with "block".
- ABSENT_MISSING_HANDLING = "next_step"
  If a resolved approver has been absent > skip_if_absent_days, the
  engine hops to the next applicable step. (Encoded here as a comment
  and enforced in resolver code paths.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


REIMBURSE_DEFAULT_MODE = "direct"
POLICY_DEFAULT_MODE = "warn"
ABSENT_MISSING_HANDLING = "next_step"


@dataclass(frozen=True)
class LineItemInput:
    """Input for policy evaluation."""
    amount_paise: int
    category_name: str
    has_receipt: bool
    line_date: Optional[str] = None
    per_diem_cap_paise: Optional[int] = None
    receipt_required_above_paise: Optional[int] = None
    policy_mode: str = "warn"


@dataclass
class PolicyFlag:
    line_index: int
    reason: str
    severity: str  # "warn" | "block"


@dataclass
class PolicyReport:
    flags: List[PolicyFlag] = field(default_factory=list)

    @property
    def has_blocks(self) -> bool:
        return any(f.severity == "block" for f in self.flags)

    def by_line(self) -> Dict[int, List[PolicyFlag]]:
        out: Dict[int, List[PolicyFlag]] = {}
        for f in self.flags:
            out.setdefault(f.line_index, []).append(f)
        return out


def evaluate_policy(lines: Iterable[LineItemInput]) -> PolicyReport:
    """Walk each line and emit warn/block flags. Never mutates the
    lines. Callers decide whether to block submission on has_blocks.
    """
    report = PolicyReport()
    for idx, line in enumerate(lines):
        mode = line.policy_mode or POLICY_DEFAULT_MODE
        # Receipt-required-above rule
        if (
            line.receipt_required_above_paise is not None
            and line.amount_paise > line.receipt_required_above_paise
            and not line.has_receipt
        ):
            report.flags.append(PolicyFlag(
                line_index=idx,
                reason=(
                    f"Receipt required above ₹"
                    f"{line.receipt_required_above_paise / 100:.2f}"
                ),
                severity=mode,
            ))
        # Per-diem cap
        if (
            line.per_diem_cap_paise is not None
            and line.amount_paise > line.per_diem_cap_paise
        ):
            report.flags.append(PolicyFlag(
                line_index=idx,
                reason=(
                    f"Exceeds per-diem cap ₹"
                    f"{line.per_diem_cap_paise / 100:.2f}"
                ),
                severity=mode,
            ))
    return report


# ----------------------------------------------------------------------
# Totals + validation
# ----------------------------------------------------------------------


def sum_line_items(lines: Iterable[LineItemInput]) -> int:
    """Sum in paise. Integer arithmetic — no float rounding drift."""
    return sum(int(l.amount_paise) for l in lines)


# ----------------------------------------------------------------------
# Reimbursement decision — no double-pay
# ----------------------------------------------------------------------


@dataclass
class ReimbursementDecision:
    can_reimburse: bool
    mode: Optional[str] = None
    reason: Optional[str] = None


def decide_reimbursement(
    *,
    claim_status: str,
    reimbursement_mode: Optional[str],
    reimbursed_at: Optional[object],
    payroll_run_id: Optional[int],
    requested_mode: str = REIMBURSE_DEFAULT_MODE,
) -> ReimbursementDecision:
    """Pure guard: refuse to reimburse a claim that has ALREADY been
    reimbursed (direct OR payroll). Refuse to pay if the claim isn't in
    APPROVED status. Refuse if the requested_mode isn't one of
    'direct' / 'payroll'.

    This function is the ONLY authority the endpoint should consult
    before writing a reimbursement row or pushing to payroll.
    """
    if requested_mode not in ("direct", "payroll"):
        return ReimbursementDecision(
            can_reimburse=False,
            reason=f"unknown reimbursement mode {requested_mode!r}",
        )
    if claim_status != "approved":
        return ReimbursementDecision(
            can_reimburse=False,
            reason=(
                f"cannot reimburse from status {claim_status!r} — "
                "must be approved"
            ),
        )
    already_direct = (
        reimbursement_mode == "direct" and reimbursed_at is not None
    )
    already_payroll = (
        reimbursement_mode == "payroll" and payroll_run_id is not None
    )
    if already_direct or already_payroll:
        return ReimbursementDecision(
            can_reimburse=False,
            reason=(
                f"already reimbursed via {reimbursement_mode!r} — "
                "double-pay blocked"
            ),
        )
    return ReimbursementDecision(can_reimburse=True, mode=requested_mode)


# ----------------------------------------------------------------------
# Travel advance recovery
# ----------------------------------------------------------------------


@dataclass
class AdvanceReconciliation:
    """How much of a travel advance still needs to be recovered from the
    employee after they file actuals.
    """
    advance_paid_paise: int
    actual_spend_paise: int
    balance_paise: int         # positive → recover from employee
    surplus_paise: int         # positive → pay employee the difference

    @property
    def needs_recovery(self) -> bool:
        return self.balance_paise > 0

    @property
    def needs_topup(self) -> bool:
        return self.surplus_paise > 0


def reconcile_travel_advance(
    *,
    advance_paid_paise: int,
    actual_spend_paise: int,
) -> AdvanceReconciliation:
    """Compare advance vs actuals; caller decides whether to inject a
    recovery line (like salary-advance recovery) or a top-up payment.
    """
    delta = advance_paid_paise - actual_spend_paise
    balance = max(0, delta)
    surplus = max(0, -delta)
    return AdvanceReconciliation(
        advance_paid_paise=advance_paid_paise,
        actual_spend_paise=actual_spend_paise,
        balance_paise=balance,
        surplus_paise=surplus,
    )
