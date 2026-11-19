from dataclasses import asdict
from datetime import date

from app.services.asset_depreciation import book_value, months_between

D = date(2026, 1, 15)


def bv(on, cost=12_000_000, salvage=0, life=12, purchase=D):
    return book_value(cost_paise=cost, salvage_paise=salvage,
                      purchase_date=purchase, life_months=life, on=on)


def test_before_day_reached():
    r = bv(date(2026, 1, 14))
    assert r.months_elapsed == 0 and r.book_value_paise == 12_000_000


def test_purchase_day():
    assert bv(date(2026, 1, 15)).months_elapsed == 0


def test_one_month():
    r = bv(date(2026, 2, 15))
    assert r.months_elapsed == 1 and r.accumulated_paise == 1_000_000
    assert r.book_value_paise == 11_000_000 and not r.fully_depreciated


def test_end_of_life():
    r = bv(date(2027, 1, 15))
    assert r.fully_depreciated and r.book_value_paise == 0


def test_long_after_life():
    r = bv(date(2030, 1, 1))
    assert r.book_value_paise == 0 and r.accumulated_paise == 12_000_000


def test_salvage_floor():
    r = bv(date(2035, 1, 1), salvage=2_000_000)
    assert r.book_value_paise == 2_000_000


def test_salvage_exceeds_cost():
    r = bv(date(2030, 1, 1), cost=1_000_000, salvage=5_000_000)
    assert r.salvage_paise == 1_000_000
    assert r.book_value_paise == 1_000_000 and r.accumulated_paise == 0


def test_negative_salvage():
    r = bv(date(2035, 1, 1), salvage=-500)
    assert r.salvage_paise == 0 and r.book_value_paise == 0


def test_default_life():
    assert bv(D, life=None).life_months == 36
    assert bv(D, life=0).life_months == 36


def test_none_inputs():
    assert bv(D, cost=None) is None
    assert bv(D, purchase=None) is None


def test_negative_cost():
    assert bv(D, cost=-1) is None


def test_on_before_purchase():
    assert bv(date(2025, 1, 1)).months_elapsed == 0


def test_all_ints():
    r = bv(date(2026, 6, 20))
    for k, v in asdict(r).items():
        if k == "fully_depreciated":
            assert isinstance(v, bool)
        else:
            assert isinstance(v, int) and not isinstance(v, bool)


def test_month_end_purchase_documented():
    p = date(2026, 1, 31)
    assert months_between(p, date(2026, 2, 28)) == 0
    assert months_between(p, date(2026, 3, 31)) == 2
