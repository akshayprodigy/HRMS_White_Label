from datetime import datetime, timezone

from app.services import adms_protocol as p


def test_attlog_parses_and_skips_blank():
    body = (
        "12\t2026-11-14 09:30:00\t0\t1\t0\t0\t0\n"
        "\n"
        "7\t2026-11-14 18:05:10\n"
    )
    recs, errs = p.parse_attlog(body)
    assert errs == []
    assert len(recs) == 2
    assert recs[0].pin == "12"
    assert recs[0].local_time == datetime(2026, 11, 14, 9, 30, 0)
    assert recs[0].status == "0" and recs[0].verify == "1"
    assert recs[1].pin == "7" and recs[1].status is None and recs[1].verify is None


def test_attlog_bad_lines_go_to_errors():
    body = "12\tnot-a-date\t0\t1\na b\t2026-11-14 09:30:00\t0\t1\n12\t2026-11-14 09:30:00\t0\t1\n"
    recs, errs = p.parse_attlog(body)
    assert len(recs) == 1
    assert len(errs) == 2
    assert errs[0].startswith("line 1:")
    assert errs[1].startswith("line 2:")


def test_attlog_truncates_at_max_lines():
    line = "1\t2026-11-14 09:30:00\t0\t1\n"
    recs, _ = p.parse_attlog(line * (p.MAX_LINES + 10))
    assert len(recs) == p.MAX_LINES


def test_attlog_crlf():
    recs, errs = p.parse_attlog("12\t2026-11-14 09:30:00\t0\t1\r\n13\t2026-11-14 09:31:00\t1\t1\r\n")
    assert errs == [] and [r.pin for r in recs] == ["12", "13"]
    assert recs[1].verify == "1"


def test_operlog_users_only():
    body = (
        "USER PIN=12\tName=Ravi\tPri=0\tPasswd=\tCard=\tGrp=1\r\n"
        "FP PIN=12\tFID=0\tTMP=AAAA\n"
        "OPLOG 4\t0\t2026-11-14 09:00:00\t0\t0\t0\t0\n"
        "USER PIN=13\tPri=0\n"
    )
    users = p.parse_operlog_users(body)
    assert [(u.pin, u.name) for u in users] == [("12", "Ravi"), ("13", None)]


def test_to_utc():
    out = p.to_utc(datetime(2026, 11, 14, 9, 30), 330)
    assert out == datetime(2026, 11, 14, 4, 0, tzinfo=timezone.utc)


def _hs(offset_tz):
    return (
        "GET OPTION FROM: SN1\n"
        "ATTLOGStamp=None\n"
        "OPERLOGStamp=99\n"
        "ATTPHOTOStamp=None\n"
        "ErrorDelay=30\n"
        "Delay=10\n"
        "TransTimes=00:00;14:05\n"
        "TransInterval=1\n"
        "TransFlag=TransData AttLog OpLog\n"
        f"TimeZone={offset_tz}\n"
        "Realtime=1\n"
        "Encrypt=None\n"
    )


def test_handshake_exact():
    assert p.handshake_response("SN1", None, "99", 330) == _hs("5.5")
    assert p.handshake_response("SN1", None, "99", 480) == _hs("8")


def test_ok_count():
    assert p.ok_count(3) == "OK: 3"
