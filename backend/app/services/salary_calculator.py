import math


def roundup(value: float) -> int:
    """Excel ROUNDUP equivalent - always rounds up to nearest integer."""
    return math.ceil(value)


def calculate_professional_tax(net_earnings: float) -> int:
    """West Bengal Professional Tax slabs."""
    if net_earnings <= 10000:
        return 0
    elif net_earnings <= 15000:
        return 110
    elif net_earnings <= 25000:
        return 130
    elif net_earnings <= 40000:
        return 150
    else:
        return 200


def calculate_salary(
    basic_salary: float,
    conveyance_allowance: float,
    hra: float,
    other_allowance: float,
    esic_applicable: bool,
    paid_days: int,
    days_in_month: int = 31,
    guest_house: float = 0,
    tds: float = 0,
    voluntary_pf: float = 0,
    arrear: float = 0,
    incentive: float = 0,
) -> dict:
    """
    Calculate full salary breakdown based on UEIPL payroll structure.

    Returns dict with all salary components.
    """
    # Fixed earnings
    total_fixed = basic_salary + conveyance_allowance + hra + other_allowance

    # Actual earnings (pro-rated by paid days)
    actual_basic = roundup(basic_salary / days_in_month * paid_days)
    actual_ca = roundup(conveyance_allowance / days_in_month * paid_days)
    actual_hra = roundup(hra / days_in_month * paid_days)
    actual_other = roundup(other_allowance / days_in_month * paid_days)
    prorated_total = roundup(total_fixed / days_in_month * paid_days)
    # Arrear and incentive added on top of pro-rated salary as full amounts
    total_actual = prorated_total + arrear + incentive

    # Employee deductions
    employee_esi = roundup(total_actual * 0.0075) if esic_applicable else 0
    employee_pf = roundup(actual_basic * 0.12)
    professional_tax = calculate_professional_tax(total_actual)
    total_deductions = (
        employee_esi + employee_pf + voluntary_pf
        + guest_house + professional_tax + tds
    )

    # Net salary
    net_salary = total_actual - total_deductions

    # Employer contributions
    employer_esic = (
        roundup(employee_esi / 0.75 * 3.25)
        if esic_applicable and employee_esi > 0 else 0
    )
    employer_pf = roundup(employee_pf / 12 * 13)

    # Total CTC
    total_ctc = net_salary + employer_esic + employer_pf

    return {
        # Fixed earnings
        "basic_salary_fixed": basic_salary,
        "conveyance_fixed": conveyance_allowance,
        "hra_fixed": hra,
        "other_allowance_fixed": other_allowance,
        "total_fixed_earnings": total_fixed,

        # Actual earnings
        "basic_salary_actual": actual_basic,
        "conveyance_actual": actual_ca,
        "hra_actual": actual_hra,
        "other_allowance_actual": actual_other,
        "arrear": arrear,
        "incentive": incentive,
        "total_actual_earnings": total_actual,

        # Paid days
        "paid_days": paid_days,
        "days_in_month": days_in_month,

        # Employee deductions
        "employee_esi": employee_esi,
        "employee_pf": employee_pf,
        "voluntary_pf": voluntary_pf,
        "guest_house": guest_house,
        "professional_tax": professional_tax,
        "tds": tds,
        "total_deductions": total_deductions,

        # Net
        "net_salary": net_salary,

        # Employer contributions
        "employer_esic": employer_esic,
        "employer_pf": employer_pf,

        # CTC
        "total_employer_cost": total_ctc,

        # ESIC status
        "esic_applicable": esic_applicable,
    }


def calculate_salary_contractual(
    basic_salary: float,
    paid_days: int,
    days_in_month: int = 31,
    arrear: float = 0,
    incentive: float = 0,
) -> dict:
    """
    Simplified calculation for contractual employees.
    Gross = pro-rated salary + arrear + incentive.
    Only deduction: 10% TDS on gross.
    """
    total_fixed = basic_salary
    prorated = roundup(total_fixed / days_in_month * paid_days)
    gross = prorated + arrear + incentive
    tds = roundup(gross * 0.10)
    net = gross - tds

    return {
        # Fixed earnings
        "basic_salary_fixed": basic_salary,
        "conveyance_fixed": 0.0,
        "hra_fixed": 0.0,
        "other_allowance_fixed": 0.0,
        "total_fixed_earnings": basic_salary,

        # Actual earnings
        "basic_salary_actual": prorated,
        "conveyance_actual": 0,
        "hra_actual": 0,
        "other_allowance_actual": 0,
        "arrear": arrear,
        "incentive": incentive,
        "total_actual_earnings": gross,

        # Paid days
        "paid_days": paid_days,
        "days_in_month": days_in_month,

        # Employee deductions
        "employee_esi": 0,
        "employee_pf": 0,
        "voluntary_pf": 0,
        "guest_house": 0,
        "professional_tax": 0,
        "tds": tds,
        "total_deductions": tds,

        # Net
        "net_salary": net,

        # Employer contributions (none for contractual)
        "employer_esic": 0,
        "employer_pf": 0,
        "total_employer_cost": gross,

        "esic_applicable": False,
        "employment_type": "contractual",
    }


def calculate_salary_from_basic(
    basic_salary: float,
    esic_applicable: bool = False,
    paid_days: int = 31,
    days_in_month: int = 31,
    guest_house: float = 0,
    tds: float = 0,
    voluntary_pf: float = 0,
    arrear: float = 0,
    incentive: float = 0,
) -> dict:
    """
    Auto-calculate all allowances from basic salary using standard ratios:
    - Conveyance: 30% of Basic
    - HRA: 50% of Basic
    - Other: 20% of Basic
    """
    ca = round(basic_salary * 0.30)
    hra = round(basic_salary * 0.50)
    other = round(basic_salary * 0.20)

    return calculate_salary(
        basic_salary=basic_salary,
        conveyance_allowance=ca,
        hra=hra,
        other_allowance=other,
        esic_applicable=esic_applicable,
        paid_days=paid_days,
        days_in_month=days_in_month,
        guest_house=guest_house,
        tds=tds,
        voluntary_pf=voluntary_pf,
        arrear=arrear,
        incentive=incentive,
    )
