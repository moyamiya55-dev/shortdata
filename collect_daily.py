"""
숏감시 2단계 — 하루 한 번 공개 파일 수집기 (깃허브 액션용)

받는 것
  1. FINRA 일별 공매도 거래량 (CNMSshvol)  → data/finra/YYYY-MM-DD.txt.gz
     형식: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
  2. 나스닥 Reg SHO 스레숄드 리스트          → data/threshold/YYYY-MM-DD.txt
     형식: Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Rule 3210|Filler

스스로 빈칸 메우기
  실행할 때마다 최근 40 평일을 훑어서, 아직 없는 날짜만 받는다.
  그래서 첫 실행 때 과거 약 두 달 치가 한 번에 채워지고(20일 평균 바로 계산 가능),
  하루 실행을 건너뛰어도 다음 실행 때 자동으로 메워진다.
  휴장일·아직 안 올라온 날은 조용히 건너뛴다.
"""

import gzip
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

LOOKBACK_WEEKDAYS = 40
UA = {"User-Agent": "Mozilla/5.0 (shortdata collector)"}

SOURCES = [
    {
        "name": "finra",
        "url": "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt",
        "dir": "data/finra",
        "ext": ".txt.gz",
        "gzip": True,
        "header": "Date|Symbol",
    },
    {
        "name": "threshold",
        "url": "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{ymd}.txt",
        "dir": "data/threshold",
        "ext": ".txt",
        "gzip": False,
        "header": "Symbol|",
    },
]


def et_today():
    # 미국 동부 날짜 (서머타임 무시해도 저녁 실행이라 날짜는 같음)
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def recent_weekdays(n):
    d = et_today()
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise


def main():
    got = {s["name"]: 0 for s in SOURCES}
    for s in SOURCES:
        os.makedirs(s["dir"], exist_ok=True)
        for d in recent_weekdays(LOOKBACK_WEEKDAYS):
            path = os.path.join(s["dir"], d.isoformat() + s["ext"])
            if os.path.exists(path):
                continue
            try:
                text = fetch(s["url"].format(ymd=d.strftime("%Y%m%d")))
            except Exception as e:  # 네트워크 일시 오류는 다음 실행에서 다시
                print(f"{s['name']} {d} 오류: {e}")
                continue
            if not text or not text.startswith(s["header"]):
                continue  # 휴장일 / 아직 미게시
            if s["gzip"]:
                with gzip.open(path, "wt", encoding="utf-8") as f:
                    f.write(text)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            got[s["name"]] += 1
    print("새로 받은 파일:", got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
