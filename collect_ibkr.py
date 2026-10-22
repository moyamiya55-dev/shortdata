"""
숏감시 1단계 — IBKR 대차 데이터 15분 수집기 (깃허브 액션용)

하는 일
  1. IBKR 공개 FTP에서 usa.txt(전 종목 대차 가능 수량·수수료)를 받는다.
  2. 추적 대상만 고른다: 수수료 20% 이상 또는 data/watchlist.txt에 있는 종목.
  3. 직전 스냅샷과 비교해 "달라진 줄만" data/ibkr/YYYY-MM-DD.csv 에 추가한다.
  4. 하루 첫 실행 때는 전체 원본을 data/ibkr/raw/YYYY-MM-DD.txt.gz 로 보관한다.

저장 형식 (data/ibkr/2026-10-23.csv)
  ts_utc,symbol,fee,rebate,available
  2026-10-23T05:30:12Z,SHFS,150.03,-146.0,0

available 이 ">10000000" 이면 10000000 으로 기록한다.
"""

import csv
import gzip
import io
import json
import os
import sys
from datetime import datetime, timezone
from ftplib import FTP

FTP_HOST = "ftp2.interactivebrokers.com"
FTP_USER = "shortstock"
FTP_FILE = "usa.txt"

FEE_MIN = 20.0           # 이 수수료(%) 이상이면 자동 추적
DATA_DIR = "data/ibkr"
WATCHLIST = "data/watchlist.txt"
STATE_FILE = os.path.join(DATA_DIR, "last.json")


def download_usa_txt() -> str:
    buf = io.BytesIO()
    ftp = FTP(FTP_HOST, timeout=60)
    ftp.login(FTP_USER, "")
    ftp.retrbinary(f"RETR {FTP_FILE}", buf.write)
    ftp.quit()
    return buf.getvalue().decode("utf-8", errors="replace")


def parse(text: str) -> dict:
    """{symbol: (fee, rebate, available)} 로 변환"""
    rows = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        sym, _cur, _name, _con, _isin, rebate, fee, avail = parts[:8]
        try:
            fee_v = float(fee)
            rebate_v = float(rebate)
        except ValueError:
            continue
        avail = avail.strip().lstrip(">")
        try:
            avail_v = int(avail) if avail else 0
        except ValueError:
            avail_v = 0
        rows[sym.strip()] = (fee_v, rebate_v, avail_v)
    return rows


def load_watchlist() -> set:
    if not os.path.exists(WATCHLIST):
        return set()
    with open(WATCHLIST, encoding="utf-8") as f:
        return {ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")}


def main() -> int:
    os.makedirs(os.path.join(DATA_DIR, "raw"), exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.strftime("%Y-%m-%d")

    text = download_usa_txt()
    if "|" not in text:
        print("FTP 파일이 비어 있음, 종료")
        return 1

    # 하루 첫 실행이면 원본 보관
    raw_path = os.path.join(DATA_DIR, "raw", f"{day}.txt.gz")
    if not os.path.exists(raw_path):
        with gzip.open(raw_path, "wt", encoding="utf-8") as f:
            f.write(text)

    rows = parse(text)
    watch = load_watchlist()

    # 직전 상태
    last = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            last = json.load(f)

    tracked = {s: v for s, v in rows.items() if v[0] >= FEE_MIN or s in watch}
    # 추적에서 빠졌지만 직전엔 있던 종목도 한 번은 기록 (수수료가 20% 아래로 떨어진 경우)
    for s in list(last.keys()):
        if s not in tracked and s in rows:
            tracked[s] = rows[s]

    changed = []
    for s, (fee, rebate, avail) in tracked.items():
        prev = last.get(s)
        if prev is None or prev != [fee, rebate, avail]:
            changed.append((ts, s, fee, rebate, avail))

    out_path = os.path.join(DATA_DIR, f"{day}.csv")
    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["ts_utc", "symbol", "fee", "rebate", "available"])
        w.writerows(changed)

    # 상태 갱신 (추적 대상만 저장)
    new_state = {s: [v[0], v[1], v[2]] for s, v in tracked.items() if v[0] >= FEE_MIN or s in watch}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(new_state, f)

    print(f"{ts} 전체 {len(rows)}종목 / 추적 {len(new_state)} / 변경 {len(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
