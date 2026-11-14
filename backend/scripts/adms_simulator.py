"""Emulate a ZKTeco / eSSL ADMS device for QA.

    python scripts/adms_simulator.py --base http://localhost:8005 --sn SIM001 \
        [--pins 101,102] [--date 2031-01-06] [--offset 330] [--repeat]

Steps: handshake, OPERLOG (USER lines), ATTLOG (an in ~09:0x and out ~18:0x
local tap per pin), getrequest. --repeat re-sends the same ATTLOG to show
idempotency.
"""
import argparse
from datetime import date

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8005")
    ap.add_argument("--sn", default="SIM001")
    ap.add_argument("--pins", default="101,102")
    ap.add_argument("--date", default="2031-01-06")
    ap.add_argument("--offset", type=int, default=330,
                    help="device clock offset from UTC in minutes (informational)")
    ap.add_argument("--repeat", action="store_true")
    a = ap.parse_args()
    date.fromisoformat(a.date)
    pins = [p.strip() for p in a.pins.split(",") if p.strip()]
    q = {"SN": a.sn}
    hdr = {"Content-Type": "text/plain"}

    with httpx.Client(base_url=a.base.rstrip("/"), timeout=20) as c:
        def show(label, r):
            print(f"== {label}: HTTP {r.status_code}\n{r.text.rstrip()}\n")

        show("handshake", c.get("/iclock/cdata", params={**q, "options": "all",
                                                         "pushver": "2.4.1"}))
        oper = "\n".join(
            f"USER PIN={p}\tName=Sim User {p}\tPri=0\tPasswd=\tCard=\tGrp=1"
            for p in pins) + "\n"
        show("OPERLOG", c.post("/iclock/cdata",
                               params={**q, "table": "OPERLOG", "Stamp": "1"},
                               content=oper, headers=hdr))
        att = ""
        for i, p in enumerate(pins):
            att += f"{p}\t{a.date} 09:0{i % 10}:00\t0\t1\t0\t0\n"
            att += f"{p}\t{a.date} 18:0{i % 10}:00\t1\t1\t0\t0\n"
        show("ATTLOG", c.post("/iclock/cdata",
                              params={**q, "table": "ATTLOG", "Stamp": "9999"},
                              content=att, headers=hdr))
        if a.repeat:
            show("ATTLOG (repeat, idempotent)", c.post(
                "/iclock/cdata", params={**q, "table": "ATTLOG", "Stamp": "9999"},
                content=att, headers=hdr))
        show("getrequest", c.get("/iclock/getrequest", params=q))


if __name__ == "__main__":
    main()
