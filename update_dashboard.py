# -*- coding: utf-8 -*-
"""
매크로 Daily 대시보드 업데이트 스크립트
- 실행 시 시장 데이터 수집 + 뉴스 폴더 PDF 요약 → HTML 갱신
- 사용법: python update_dashboard.py
"""

import os, sys, re, json, glob, warnings, datetime
warnings.filterwarnings('ignore')

# --no-push 옵션: GitHub Actions에서 push를 직접 처리할 때 사용
NO_PUSH = '--no-push' in sys.argv

import yfinance as yf
import pandas as pd
import pdfplumber

# ── 경로 설정 ───────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
NEWS_DIR   = os.path.join(BASE_DIR, "뉴스")
HTML_PATH  = os.path.join(BASE_DIR, "시장지표_대시보드.html")
TODAY      = datetime.date.today().strftime("%Y-%m-%d")
TODAY_KR   = datetime.date.today().strftime("%Y.%m.%d")

# ── 1. 시장 데이터 수집 ─────────────────────────────────────────────────
def fetch(ticker, period="5y"):
    try:
        d = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        s = d['Close']
        if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]  # MultiIndex 처리
        s = s.dropna()
        if s.empty:
            return None, {}
        latest = round(float(s.iloc[-1].item()), 4)
        # 과거 데이터 포인트 (날짜 기반 필터링)
        def ago(days):
            try:
                target_date = (pd.Timestamp.now() - pd.Timedelta(days=days)).date()
                # 날짜 비교로 검색
                dates = [d.date() if hasattr(d, 'date') else d for d in s.index]
                # target 이전 마지막 인덱스
                candidates = [i for i, d in enumerate(dates) if d <= target_date]
                if not candidates: return round(float(s.iloc[0].item()), 4)
                return round(float(s.iloc[candidates[-1]].item()), 4)
            except:
                return None
        history = {
            "1m": ago(30), "3m": ago(90), "6m": ago(180),
            "1y": ago(365), "3y": ago(365*3), "5y": ago(365*5)
        }
        return latest, history
    except Exception as e:
        print(f"  [fetch 오류] {ticker}: {e}")
        return None, {}

def fetch_series(ticker, period="5y"):
    """시계열 데이터 반환 (차트용, 월말 기준)"""
    try:
        d = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        s = d['Close']
        if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]  # MultiIndex 처리
        s = s.dropna()
        if s.empty: return []
        # timezone 제거
        if s.index.tzinfo:
            s.index = s.index.tz_localize(None)
        # 월별 마지막 값
        monthly = s.resample('ME').last().dropna()
        result = []
        for dt, v in monthly.items():
            result.append({"d": dt.strftime("%Y-%m"), "v": round(float(v), 4)})
        # 최신값 추가
        latest_date = s.index[-1].strftime("%Y-%m-%d")
        result.append({"d": latest_date, "v": round(float(s.iloc[-1].item()), 4)})
        return result[-61:]  # 최대 5년치
    except Exception as e:
        print(f"  [series 오류] {ticker}: {e}")
        return []

print("시장 데이터 수집 중...")

# ── 과거 기준일 계산 (오늘 기준) ─────────────────────────────────────────
def date_ago(months=0, years=0):
    today = datetime.date.today()
    m = today.month - months - years*12
    y = today.year
    while m <= 0:
        m += 12; y -= 1
    import calendar as _cal
    day = min(today.day, _cal.monthrange(y, m)[1])
    return datetime.date(y, m, day)

d1m = date_ago(months=1)   # 2026-06-28
d3m = date_ago(months=3)   # 2026-04-28
d6m = date_ago(months=6)   # 2026-01-28
d1y = date_ago(years=1)    # 2025-07-28
d3y = date_ago(years=3)    # 2023-07-28
d5y = date_ago(years=5)    # 2021-07-28

# 한국 기준금리 경로 (금통위 변경 시 업데이트)
def kr_base_at(d):
    if d >= datetime.date(2026,7,16): return 2.75
    if d >= datetime.date(2025,5,29): return 2.50
    if d >= datetime.date(2025,2,25): return 2.75
    if d >= datetime.date(2024,12,28): return 3.00
    if d >= datetime.date(2024,11,28): return 3.25
    if d >= datetime.date(2023,1,13): return 3.50
    if d >= datetime.date(2022,11,24): return 3.25
    if d >= datetime.date(2022,10,12): return 3.00
    if d >= datetime.date(2022,8,25):  return 2.50
    if d >= datetime.date(2022,7,13):  return 2.25
    if d >= datetime.date(2022,5,26):  return 1.75
    if d >= datetime.date(2022,4,14):  return 1.50
    if d >= datetime.date(2022,1,14):  return 1.25
    if d >= datetime.date(2021,11,25): return 1.00
    if d >= datetime.date(2021,8,26):  return 0.75
    return 0.50

# 미국 기준금리 경로 (FOMC 변경 시 업데이트)
def us_base_at(d):
    if d >= datetime.date(2025,12,10): return 3.75
    if d >= datetime.date(2025,10,29): return 4.00
    if d >= datetime.date(2025,9,17):  return 4.25
    if d >= datetime.date(2024,12,19): return 4.50
    if d >= datetime.date(2024,11,8):  return 4.75
    if d >= datetime.date(2024,9,19):  return 5.00
    if d >= datetime.date(2023,7,27):  return 5.50
    if d >= datetime.date(2023,5,4):   return 5.25
    if d >= datetime.date(2023,3,23):  return 5.00
    if d >= datetime.date(2023,2,2):   return 4.75
    if d >= datetime.date(2022,12,15): return 4.50
    if d >= datetime.date(2022,11,3):  return 4.00
    if d >= datetime.date(2022,9,22):  return 3.25
    if d >= datetime.date(2022,7,28):  return 2.50
    if d >= datetime.date(2022,6,16):  return 1.75
    if d >= datetime.date(2022,5,5):   return 1.00
    if d >= datetime.date(2022,3,17):  return 0.50
    return 0.25

# ── ECOS API (국내 금리 실시간) ─────────────────────────────────────────
ECOS_KEY = '929ZKGC4X65GUL5UTMWP'

def ecos_fetch(stat_code, item_code, from_date='20250101'):
    """ECOS에서 최신값 + 과거 히스토리 수집"""
    import requests as _req
    try:
        today_str = datetime.date.today().strftime('%Y%m%d')
        url = (f'https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/2000/'
               f'{stat_code}/D/{from_date}/{today_str}/{item_code}')
        d = _req.get(url, timeout=10).json()
        if 'StatisticSearch' not in d:
            return None, {}
        rows = [(r['TIME'], float(r['DATA_VALUE'])) for r in d['StatisticSearch']['row']
                if r.get('DATA_VALUE') and r['DATA_VALUE'] not in ('-','')]
        if not rows:
            return None, {}
        latest = rows[-1][1]
        def ecos_ago(days):
            target = (datetime.date.today() - datetime.timedelta(days=days)).strftime('%Y%m%d')
            for dt, v in reversed(rows):
                if dt <= target:
                    return round(v, 4)
            return rows[0][1] if rows else None
        history = {
            "1m": ecos_ago(30),  "3m": ecos_ago(90),  "6m": ecos_ago(180),
            "1y": ecos_ago(365), "3y": ecos_ago(365*3),"5y": ecos_ago(365*5)
        }
        return round(latest, 4), history
    except Exception as e:
        print(f"  [ECOS 오류] {stat_code}/{item_code}: {e}")
        return None, {}

print("  ECOS 국내 금리 수집 중...")
# from_date: 5년치 히스토리 확보 위해 2021년부터, 건수 충분히 확보
# 기준금리는 ECOS 업데이트 시차 문제로 날짜 기반 함수 유지
kr3y_v,      kr3y_h      = ecos_fetch('817Y002', '010200000', from_date='20210101')
kr10y_v,     kr10y_h     = ecos_fetch('817Y002', '010210000', from_date='20210101')
cd_v,        cd_h         = ecos_fetch('817Y002', '010502000', from_date='20210101')
corp_aa_v,   corp_aa_h   = ecos_fetch('817Y002', '010300000', from_date='20210101')

# 기준금리: 날짜 기반 함수로 정확히 관리 (FOMC/금통위 시 kr_base_at 함수 업데이트)
KR_BASE_RATE    = kr_base_at(datetime.date.today())
KR_BASE_HISTORY = {
    "1m": kr_base_at(d1m), "3m": kr_base_at(d3m),
    "6m": kr_base_at(d6m), "1y": kr_base_at(d1y),
    "3y": kr_base_at(d3y), "5y": kr_base_at(d5y)
}
if kr3y_v  is None: kr3y_v,  kr3y_h  = 3.852, {"1m":3.80,"3m":3.45,"6m":3.09,"1y":3.20,"3y":4.10,"5y":1.50}
if kr10y_v is None: kr10y_v, kr10y_h = 4.300, {"1m":4.25,"3m":3.80,"6m":3.55,"1y":3.55,"3y":4.40,"5y":2.10}

# 회사채 AA0(무보증) 3Y = ECOS AA- 3Y + 5.2bp
SPREAD_AA0 = 0.072
corp_aa0_v = round((corp_aa_v or 4.50) - SPREAD_AA0, 3)
corp_aa0_h = {k: round((v or 0) - SPREAD_AA0, 3) for k, v in (corp_aa_h or {}).items()}
corp_aa0 = {"v": corp_aa0_v, "h": corp_aa0_h}
# 금융채(은행채) 1Y — 환경변수로 입력받거나 마지막 저장값 사용
_fin_aaa_input = os.environ.get('FIN_AAA_RATE', '').strip()
_last_file = os.path.join(BASE_DIR, 'fin_aaa_last.txt')
if _fin_aaa_input:
    _fin_aaa_v = float(_fin_aaa_input)
elif os.path.exists(_last_file):
    _fin_aaa_v = float(open(_last_file, encoding='utf-8-sig').read().strip())
else:
    _fin_aaa_v = 4.20
fin_aaa  = {"v": _fin_aaa_v, "h": {"1m":4.10,"3m":3.78,"6m":3.52,"1y":3.68,"3y":4.50,"5y":1.90}}
cd_rate  = {"v": cd_v or 3.85,
            "h": cd_h or {"1m":3.83,"3m":3.60,"6m":3.28,"1y":3.55,"3y":3.75,"5y":0.90}}
print(f"  ECOS - 기준금리:{KR_BASE_RATE}, 3Y:{kr3y_v}, 10Y:{kr10y_v}, CD:{cd_rate['v']}, AA0:{corp_aa0['v']}")

# ── FRED API (미국 금리 실시간) ────────────────────────────────────────
FRED_KEY = 'c68a3a289bab847aa60e7ba4b027068f'

def fred_fetch(series_id):
    """FRED에서 최신값 + 과거 히스토리 수집"""
    import requests as _req
    try:
        url = (f'https://api.stlouisfed.org/fred/series/observations'
               f'?series_id={series_id}&api_key={FRED_KEY}&file_type=json'
               f'&sort_order=desc&limit=2000')
        d = _req.get(url, timeout=10).json()
        if 'observations' not in d:
            return None, {}
        obs = [(o['date'], float(o['value'])) for o in d['observations']
               if o['value'] not in ('.', 'NA', '')]
        if not obs:
            return None, {}
        latest = obs[0][1]
        # 날짜 기반 히스토리
        def fred_ago(days):
            target = (datetime.date.today() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
            for dt, v in obs:
                if dt <= target:
                    return round(v, 4)
            return None
        history = {
            "1m": fred_ago(30), "3m": fred_ago(90), "6m": fred_ago(180),
            "1y": fred_ago(365), "3y": fred_ago(365*3), "5y": fred_ago(365*5)
        }
        return round(latest, 4), history
    except Exception as e:
        print(f"  [FRED 오류] {series_id}: {e}")
        return None, {}

print("  FRED 미국 금리 수집 중...")
us_base_v, us_base_h = fred_fetch('DFEDTARU')  # 미국 기준금리 목표 상단
us2y_v,    us2y_h    = fred_fetch('DGS2')   # 미국채 2Y
us10y_fred, us10y_h_fred = fred_fetch('DGS10')  # 미국채 10Y (FRED)
sofr_v,    sofr_h    = fred_fetch('SOFR')   # SOFR

US_BASE_RATE    = us_base_at(datetime.date.today())
US_BASE_HISTORY = {
    "1m": us_base_at(d1m), "3m": us_base_at(d3m),
    "6m": us_base_at(d6m), "1y": us_base_at(d1y),
    "3y": us_base_at(d3y), "5y": us_base_at(d5y)
}
if us2y_v is None:
    us2y_v, us2y_h = 4.33, {"1m":4.20,"3m":3.90,"6m":4.20,"1y":4.75,"3y":4.85,"5y":0.25}
if sofr_v is None:
    sofr_v = (US_BASE_RATE or 3.75) - 0.02
    sofr_h = {k: (v or 0) - 0.02 for k, v in US_BASE_HISTORY.items()}

us10y_v = us10y_fred or 4.69
us10y_h = us10y_h_fred or {"1m":4.50,"3m":4.40,"6m":4.55,"1y":4.30,"3y":3.85,"5y":1.50}
print(f"  FRED - 기준금리:{US_BASE_RATE}, 2Y:{us2y_v}, 10Y:{us10y_v}, SOFR:{sofr_v}")

# 원자재
wti_v,   wti_h   = fetch("CL=F")
brent_v, brent_h = fetch("BZ=F")
dubai_v, dubai_h = fetch("MCL=F")  # 두바이유 실제 티커
if dubai_v is None:
    dubai_v = round((wti_v or 82) * 1.02, 2)
    dubai_h = {k: round(v*1.02, 2) for k, v in (wti_h or {}).items()}

# 환율
usdkrw_v, usdkrw_h = fetch("KRW=X")
eurkrw_v, eurkrw_h = fetch("EURKRW=X")
jpykrw_v, jpykrw_h = fetch("JPYKRW=X")
dxy_v,    dxy_h    = fetch("DX-Y.NYB")

# ── 차트용 시계열 (5년치 일별, 기간 선택 지원) ──────────────────────────
print("  시계열 데이터 수집 중...")

import calendar

def fetch_daily(ticker, years=5):
    """yfinance에서 최근 N년 일별 종가 반환"""
    try:
        d = yf.download(ticker, period=f"{years}y", progress=False, auto_adjust=True)
        s = d['Close']
        if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
        s = s.dropna()
        if s.empty: return []
        if s.index.tzinfo:
            s.index = s.index.tz_localize(None)
        return [{"d": dt.strftime("%Y-%m-%d"), "v": round(float(v), 4)} for dt, v in s.items()]
    except Exception as e:
        print(f"  [yfinance daily 오류] {ticker}: {e}")
        return []

def ecos_series_daily(stat_code, item_code, years=5):
    """ECOS에서 최근 N년 일별 데이터 반환"""
    import requests as _req
    try:
        today = datetime.date.today()
        from_date = datetime.date(today.year - years, today.month, 1).strftime('%Y%m%d')
        to_date   = today.strftime('%Y%m%d')
        url = (f'https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/2000/'
               f'{stat_code}/D/{from_date}/{to_date}/{item_code}')
        d = _req.get(url, timeout=15).json()
        if 'StatisticSearch' not in d: return []
        rows = [(r['TIME'], float(r['DATA_VALUE'])) for r in d['StatisticSearch']['row']
                if r.get('DATA_VALUE') and r['DATA_VALUE'] not in ('-', '')]
        return [{"d": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}", "v": round(v, 4)} for dt, v in rows]
    except Exception as e:
        print(f"  [ECOS daily 오류] {stat_code}/{item_code}: {e}")
        return []

def fred_series_daily(series_id, years=5):
    """FRED에서 최근 N년 일별 데이터 반환"""
    import requests as _req
    try:
        today = datetime.date.today()
        obs_start = datetime.date(today.year - years, today.month, 1).strftime('%Y-%m-%d')
        url = (f'https://api.stlouisfed.org/fred/series/observations'
               f'?series_id={series_id}&api_key={FRED_KEY}&file_type=json'
               f'&observation_start={obs_start}&sort_order=asc&limit=2000')
        d = _req.get(url, timeout=15).json()
        if 'observations' not in d: return []
        return [{"d": o['date'], "v": round(float(o['value']), 4)}
                for o in d['observations'] if o['value'] not in ('.', 'NA', '')]
    except Exception as e:
        print(f"  [FRED daily 오류] {series_id}: {e}")
        return []

def make_base_rate_daily(rate_fn, years=5):
    """rate_fn(date) → N년치 영업일별 시계열 자동 생성"""
    today = datetime.date.today()
    start = datetime.date(today.year - years, today.month, 1)
    result = []
    current = start
    while current <= today:
        if current.weekday() < 5:
            result.append({"d": current.strftime("%Y-%m-%d"), "v": rate_fn(current)})
        current += datetime.timedelta(days=1)
    return result

print("  차트 시계열 수집 중 (5년치 일별)...")
kr_base_series     = make_base_rate_daily(kr_base_at)
kr3y_series        = ecos_series_daily('817Y002', '010200000')
kr10y_series       = ecos_series_daily('817Y002', '010210000')
_corp_aa_series    = ecos_series_daily('817Y002', '010300000')
corp_aa0_series    = [{"d": p["d"], "v": round(p["v"] - SPREAD_AA0, 4)} for p in _corp_aa_series] if _corp_aa_series else []
us_base_series     = make_base_rate_daily(us_base_at)
us2y_series_manual = fred_series_daily('DGS2')
us10y_series       = fetch_daily("^TNX")
usdkrw_series      = fetch_daily("KRW=X")
wti_series         = fetch_daily("CL=F")

print(f"  완료 - WTI:{wti_v}, USD/KRW:{usdkrw_v}, US10Y:{us10y_v}")

# ── 2. PDF 요약 (카테고리별 핵심 문장 추출) ─────────────────────────────

CATEGORIES = {
    "금리": ["금리","기준금리","국채","채권","금통위","FOMC","연준","Fed","통화정책",
              "인상","인하","긴축","완화","terminal","국고채","회사채","스프레드",
              "BOK","한국은행","중앙은행","bp","bps"],
    "환율": ["환율","원달러","달러","달러화","원화","엔화","유로","위안","DXY",
              "달러인덱스","외환","환시","강세","약세","절상","절하","원/달러"],
    "경기·물가": ["GDP","성장률","CPI","물가","인플레이션","근원물가","기대인플레이션",
                  "경기","수출","무역","ISM","PMI","실업","고용","소비","투자","재정",
                  "공급","수요","에너지","유가","원유","WTI","브렌트"],
}

NOISE_PATTERNS = [
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
    r'https?://\S+',
    r'^\s*(또한|한편|그러나|하지만|따라서|이에|아울러|다만)',
    r'Senior\s+Analyst|Analyst|analyst|researcher',
    r'Tel\s*:\s*\d',
    r'^\s*[\d]+\s*페이지',
    r'Compliance|compliance|저작권|무단',
    r'본\s*(보고서|자료|조사)',
    r'삼성증권|KB증권|미래에셋|NH투자|한투|키움',
]

ENDING_MAP = [
    (r'(했|하였)습니다\.?$', '함'),
    (r'(됩|되었)습니다\.?$', '됨'),
    (r'(입|이)습니다\.?$', '임'),
    (r'(있|없)습니다\.?$', lambda m: m.group(0).replace('습니다','음').rstrip('.')),
    (r'(했|하였)다\.?$', '함'),
    (r'(됐|되었)다\.?$', '됨'),
    (r'(할|해야)\s*(한다|합니다)\.?$', '할 것으로 판단'),
    (r'(것으로)\s*(보인다|판단된다|예상된다|전망된다)\.?$', '것으로 전망'),
    (r'(보인다|판단된다|예상된다|전망된다)\.?$', '전망'),
    (r'(높아졌다|낮아졌다|확대됐다|축소됐다)\.?$', lambda m: m.group(0).replace('다','음').rstrip('.')),
    (r'(하고|해)\s*(있다|있음)\.?$', '하는 중'),
    (r'(우려하고|걱정하고)\s*(있다|있음)\.?$', '우려'),
    (r'(분석하고|판단하고|평가하고)\s*(있다|있음)\.?$', '분석'),
    (r'(주목하고|관찰하고)\s*(있다|있음)\.?$', '주목'),
    (r'고\s*(있다|있음)\.?$', '중'),
    (r'(다)\.?$', ''),
]

def to_noun_ending(s):
    s = s.rstrip('.').strip()
    for pattern, repl in ENDING_MAP:
        if re.search(pattern, s):
            if callable(repl):
                s = re.sub(pattern, repl, s)
            else:
                s = re.sub(pattern, repl, s)
            break
    return s

def clean_text(t):
    lines = t.split('\n')
    merged = []
    buf = ''
    for line in lines:
        line = line.strip()
        if len(line) < 5: continue
        if re.match(r'^[\d\s\.\-\|%,()]+$', line): continue
        if re.match(r'^[A-Za-z\s\d\.\-@_]+$', line) and len(line) < 40: continue
        if re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+', line): continue
        if re.search(r'^\s*\d+\s*$', line): continue
        if buf:
            last_char = buf[-1]
            if last_char in '.?!다음' or re.search(r'[다했음됨임]$', buf):
                merged.append(buf)
                buf = line
            else:
                buf = buf + ' ' + line
        else:
            buf = line
    if buf:
        merged.append(buf)
    result = []
    for line in merged:
        if len(line) < 15: continue
        result.append(line)
    return ' '.join(result)

def is_noise(s):
    for pat in NOISE_PATTERNS:
        if re.search(pat, s):
            return True
    if re.match(r'^(또한|한편|그러나|하지만|따라서|이에|아울러|다만|반면|특히)\s', s):
        return True
    korean_ratio = len(re.findall(r'[가-힣]', s)) / max(len(s), 1)
    if korean_ratio < 0.3:
        return True
    if re.search(r'\(좌\)|\(우\)|\(bp\)|\(%\)|\(pt\)', s):
        return True
    if re.search(r'(이|가|을|를|의|에|은|는|하고|하며|으로|하는|한)\s*$', s):
        return True
    if re.search(r'FIXED INCOME|ISSUE REPORT|Research Report|Daily\s+Research', s):
        return True
    if re.search(r'애널리스트의 의견|압력이나 간섭|저작물|저작권|손해|책임소재', s):
        return True
    return False

def extract_sentences(text, keywords, max_sent=4):
    sentences = re.split(r'(?<=[다했다됩니다습니다었다겠다한다])\s+|(?<=[\.!?])\s+', text)
    scored = []
    for s in sentences:
        s = s.strip()
        if len(s) < 25 or len(s) > 250: continue
        if is_noise(s): continue
        score = sum(1 for kw in keywords if kw in s)
        if score >= 2:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    result = []
    for _, s in scored:
        if not any(len(set(s.split()) & set(r.split())) / max(len(s.split()), 1) > 0.45
                   for r in result):
            result.append(to_noun_ending(s))
        if len(result) >= max_sent:
            break
    return result

def summarize_pdf(pdf_path):
    """PDF → 카테고리별 핵심 문장 딕셔너리 반환"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t and len(t) > 50:
                    full_text += t + "\n"
        if not full_text.strip():
            return None
        full_text = clean_text(full_text)
        result = {}
        for cat, keywords in CATEGORIES.items():
            sentences = extract_sentences(full_text, keywords, max_sent=4)
            if sentences:
                result[cat] = sentences
        return result if result else None
    except Exception as e:
        print(f"  [오류] {e}")
        return None

print("뉴스 PDF 처리 중...")
news_items = []
news_date  = ""
today_str  = datetime.date.today().strftime("%Y.%m.%d")
NEWS_CACHE = os.path.join(BASE_DIR, 'news_cache.json')

pdf_files = sorted([f for f in glob.glob(os.path.join(NEWS_DIR, "*.pdf"))
                    if today_str in os.path.basename(f)])

for pdf_path in pdf_files:
    fname = os.path.basename(pdf_path)
    summary = summarize_pdf(pdf_path)
    if summary:
        total = sum(len(v) for v in summary.values())
        news_items.append({"file": fname, "summary": summary})
        print(f"  {fname}: {total}개 핵심 문장 추출")
    else:
        print(f"  {fname}: 텍스트 추출 불가")

# 수동 작성 캐시(firm/conclusion/bullets 형식)가 오늘 날짜면 우선 사용
_manual_cache_today = False
if os.path.exists(NEWS_CACHE):
    _cache = json.load(open(NEWS_CACHE, encoding='utf-8'))
    if _cache.get("date") == today_str:
        _first = _cache.get("items", [{}])[0]
        if _first.get("firm") or _first.get("conclusion") or _first.get("bullets"):
            news_items = _cache.get("items", [])
            news_date  = _cache.get("date", "")
            _manual_cache_today = True
            print(f"  수동 요약 캐시 사용 ({news_date}) / {len(news_items)}개 리포트")

if not _manual_cache_today:
    if news_items:
        with open(NEWS_CACHE, 'w', encoding='utf-8') as _f:
            json.dump({"date": today_str, "items": news_items}, _f, ensure_ascii=False)
        print(f"  → 캐시 저장 완료 ({today_str})")
    else:
        print(f"  오늘 PDF 없음 → 카드 없이 빈 상태로 표시")

news_date = today_str  # 항상 오늘 날짜 표시

# ── 3. 데이터 JSON 빌드 ─────────────────────────────────────────────────
def mk(v, h, label, unit=""):
    return {"label": label, "unit": unit, "v": v, "h": h or {}}

market_data = {
    "updated": TODAY_KR,
    "domestic": {
        "title": "국내 금리",
        "items": [
            mk(KR_BASE_RATE, KR_BASE_HISTORY, "기준금리", "%"),
            mk(kr3y_v,  kr3y_h,  "국고채 3Y", "%"),
            mk(kr10y_v, kr10y_h, "국고채 10Y", "%"),
            mk(corp_aa0["v"],  corp_aa0["h"],  "회사채 AA0 (무보증) 3Y", "%"),
            mk(fin_aaa["v"],   fin_aaa["h"],   "금융채(은행채) 1Y", "%"),
            mk(cd_rate["v"],   cd_rate["h"],   "CD 금리", "%"),
        ]
    },
    "us": {
        "title": "해외 금리",
        "items": [
            mk(US_BASE_RATE, US_BASE_HISTORY, "미국 기준금리", "%"),
            mk(us2y_v,  us2y_h,  "미국채 2Y", "%"),
            mk(us10y_v, us10y_h, "미국채 10Y", "%"),
            mk(sofr_v,  sofr_h,  "SOFR", "%"),
        ]
    },
    "fx": {
        "title": "환율",
        "items": [
            mk(usdkrw_v, usdkrw_h, "USD/KRW", "원"),
            mk(eurkrw_v, eurkrw_h, "EUR/KRW", "원"),
            mk(jpykrw_v, jpykrw_h, "JPY/KRW (100엔)", "원"),
            mk(dxy_v,    dxy_h,    "달러인덱스 (DXY)", ""),
        ]
    },
    "oil": {
        "title": "국제 유가",
        "items": [
            mk(wti_v,   wti_h,   "WTI",    "$/bbl"),
            mk(brent_v, brent_h, "브렌트",  "$/bbl"),
            mk(dubai_v, dubai_h, "두바이유", "$/bbl"),
        ]
    },
    "charts": {
        "kr_base":   kr_base_series,
        "kr3y":      kr3y_series,
        "kr10y":     kr10y_series,
        "corp_aa0":  corp_aa0_series,
        "us_base":   us_base_series,
        "us2y":      us2y_series_manual,
        "us10y":     us10y_series,
        "usdkrw":    usdkrw_series,
        "wti":       wti_series,
    },
    "news": news_items,
    "news_date": news_date
}

# ── 4. HTML 생성 / 업데이트 ─────────────────────────────────────────────
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>매크로 시장 지표 대시보드</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: \'Malgun Gothic\', sans-serif; background: #f4f6fa; color: #222; font-size: 13px; }
.header {
  background: #1a1a2e; color: #fff; padding: 16px 28px;
  display: flex; align-items: center; justify-content: space-between;
}
.header h1 { font-size: 18px; font-weight: 700; }
.updated { font-size: 11px; color: #aab; margin-top: 3px; }
.badge { background: #e97132; color: #fff; font-size: 11px; padding: 4px 12px; border-radius: 20px; }
.main { padding: 20px 28px; }

/* 섹션 그리드 */
.section-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 20px;
}
.section-card {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.07);
  overflow: hidden;
}
.section-header {
  background: #1a1a2e; color: #fff;
  font-size: 11px; font-weight: 700;
  padding: 8px 12px; letter-spacing: 0.5px;
}
.indicator-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f0f0;
}
.indicator-row:last-child { border-bottom: none; }
.ind-label { color: #555; font-size: 11px; }
.ind-value { font-weight: 700; font-size: 14px; color: #1a1a2e; }
.ind-unit  { font-size: 10px; color: #aaa; margin-left: 2px; }

/* 변화 테이블 */
.change-section { margin-bottom: 20px; }
.change-title {
  font-size: 13px; font-weight: 700; color: #1a1a2e;
  margin-bottom: 10px; padding-bottom: 6px;
  border-bottom: 2px solid #1a1a2e;
}
.change-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 11px; background: #fff;
  border-radius: 10px; overflow: hidden; box-shadow: 0 1px 5px rgba(0,0,0,0.07); }
th { background: #f8f9fc; color: #555; font-weight: 700; padding: 8px 10px;
  text-align: center; border-bottom: 2px solid #e0e4ef; white-space: nowrap; }
td { padding: 7px 10px; border-bottom: 1px solid #f0f0f0; text-align: center; }
td:first-child { text-align: center; color: #444; font-weight: 600; }
td:nth-child(2) { text-align: center; color: #888; font-size: 10px; }
tr:hover td { background: #fafbff; }
.up   { color: #e00; font-weight: 600; }
.down { color: #156082; font-weight: 600; }
.flat { color: #888; }

/* 차트 */
.chart-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 14px; margin-bottom: 20px;
}
.chart-card {
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.07);
  padding: 14px;
}
.chart-label { font-size: 11px; font-weight: 700; color: #1a1a2e; margin-bottom: 6px; }
canvas { max-height: 150px; }
.period-btns {
  display: flex; gap: 4px; margin-bottom: 8px; flex-wrap: wrap;
}
.period-btn {
  font-size: 10px; padding: 2px 7px; border-radius: 10px; border: 1px solid #ccc;
  background: #fff; color: #555; cursor: pointer; transition: all 0.15s;
}
.period-btn.active {
  background: #1a1a2e; color: #fff; border-color: #1a1a2e;
}

/* Daily Macro Brief */
.news-section { margin-bottom: 20px; }
.brief-grid {
  display: grid; gap: 14px;
  margin-bottom: 16px;
}
.brief-card {
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.07);
  overflow: hidden;
}
.brief-firm {
  font-size: 11px; font-weight: 700; color: #fff;
  padding: 7px 12px; background: #888;
  letter-spacing: 0.5px;
}
.brief-conclusion {
  font-size: 12px; font-weight: 600; color: #e97132;
  padding: 8px 12px 4px 12px; line-height: 1.5;
  border-bottom: 1px solid #f0f0f0;
}
.brief-bullets { padding: 8px 12px 10px 12px; }
.brief-bullet {
  font-size: 11px; color: #333; line-height: 1.75;
  padding: 3px 0; border-bottom: 1px solid #f8f8f8;
}
.brief-bullet:last-child { border-bottom: none; }
.brief-bullet::before { content: "•  "; color: #e97132; font-weight: 700; }
.section-divider {
  font-size: 11px; font-weight: 700; color: #888;
  letter-spacing: 1px; text-transform: uppercase;
  margin: 4px 0 10px; padding-bottom: 5px;
  border-bottom: 1px dashed #ddd;
}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>매크로 시장 지표 대시보드</h1>
    <div class="updated" id="updated-date">업데이트: --</div>
  </div>
  <div class="badge" id="badge-date">--</div>
</div>

<div class="main">
  <!-- 최신값 카드 -->
  <div class="section-divider">MARKET SNAPSHOT</div>
  <div class="section-grid" id="snapshot-grid"></div>

  <!-- 뉴스 요약 -->
  <div class="section-divider" style="display:flex;align-items:baseline;gap:8px;">
    DAILY MACRO BRIEF
    <span id="brief-meta" style="font-size:10px;color:#aaa;font-weight:400;letter-spacing:0;text-transform:none;"></span>
  </div>
  <div class="news-section" id="news-section"></div>

  <!-- 시계열 차트 -->
  <div class="section-divider">TREND CHARTS</div>
  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-label">국내 금리 (%)</div>
      <div class="period-btns" id="btns-kr-rates"></div>
      <canvas id="chart-kr-rates"></canvas>
    </div>
    <div class="chart-card">
      <div class="chart-label">미국 금리 (%)</div>
      <div class="period-btns" id="btns-us-rates"></div>
      <canvas id="chart-us-rates"></canvas>
    </div>
    <div class="chart-card">
      <div class="chart-label">USD/KRW (원)</div>
      <div class="period-btns" id="btns-usdkrw"></div>
      <canvas id="chart-usdkrw"></canvas>
    </div>
  </div>

  <!-- 기간별 변화 테이블 -->
  <div class="section-divider">HISTORICAL CHANGE</div>
  <div class="change-section">
    <div class="change-wrap"><table id="change-table"></table></div>
  </div>

</div>

<script>
// ── 데이터 ──────────────────────────────────────────────────────────────
const DATA = __MARKET_DATA__;

// ── 렌더 ──────────────────────────────────────────────────────────────
document.getElementById(\'updated-date\').textContent = \'업데이트: \' + DATA.updated;
document.getElementById(\'badge-date\').textContent = DATA.updated;

const SECTIONS = [\'domestic\',\'us\',\'fx\',\'oil\'];
const SECTION_COLORS = {domestic:\'#1a1a1a\',us:\'#1a1a1a\',fx:\'#1a1a1a\',oil:\'#1a1a1a\'};

// 스냅샷 카드
const grid = document.getElementById(\'snapshot-grid\');
SECTIONS.forEach(sec => {
  const s = DATA[sec];
  const card = document.createElement(\'div\');
  card.className = \'section-card\';
  card.innerHTML = `<div class="section-header" style="background:${SECTION_COLORS[sec]||\'#1a1a2e\'}">${s.title}</div>`
    + s.items.map(item => `
      <div class="indicator-row">
        <span class="ind-label">${item.label}</span>
        <span><span class="ind-value">${item.v != null ? Number(item.v).toLocaleString(\'ko-KR\', {minimumFractionDigits:2, maximumFractionDigits:2}) : \'-\'}</span><span class="ind-unit">${item.unit}</span></span>
      </div>`).join(\'\');
  grid.appendChild(card);
});

// 기간별 변화 테이블
function chgClass(v, base) {
  if (base == null || v == null) return \'flat\';
  const d = v - base;
  if (Math.abs(d) < 0.001) return \'flat\';
  return d > 0 ? \'up\' : \'down\';
}
function chgStr(v, base, unit) {
  if (base == null || v == null) return \'<span class="flat">-</span>\';
  const d = v - base;
  const sign = d > 0 ? \'+\' : \'\';
  const cls = chgClass(v, base);
  const fmt = Math.abs(d) < 1 ? 3 : 1;
  return `<span class="${cls}">${sign}${d.toFixed(fmt)}</span>`;
}

const allItems = SECTIONS.flatMap(sec => DATA[sec].items.map(i => ({...i, sec})));
const periods = [\'1m\',\'3m\',\'6m\',\'1y\',\'3y\',\'5y\'];
const periodLabels = {\'1m\':\'1개월전\',\'3m\':\'3개월전\',\'6m\':\'6개월전\',\'1y\':\'1년전\',\'3y\':\'3년전\',\'5y\':\'5년전\'};

const tbl = document.getElementById(\'change-table\');
tbl.innerHTML = `<thead><tr>
  <th>지표</th><th style="width:5%">단위</th><th style="width:8%">현재</th>
  ${periods.map(p => `<th style="width:10%">${periodLabels[p]}</th>`).join(\'\')}
</tr></thead><tbody>`
  + allItems.map(item => `<tr>
    <td>${item.label}</td>
    <td style="color:#888;font-size:10px;">${item.unit}</td>
    <td style="font-weight:700;color:#1a1a2e;">${item.v != null ? Number(item.v).toLocaleString(\'ko-KR\',{minimumFractionDigits:2,maximumFractionDigits:2}) : \'-\'}</td>
    ${periods.map(p => {
      const hv = item.h && item.h[p] != null ? item.h[p] : null;
      const cls = chgClass(item.v, hv);
      return `<td>${hv != null ? \'<span style="font-size:10px;color:#999;">\'+Number(hv).toLocaleString(\'ko-KR\',{minimumFractionDigits:2,maximumFractionDigits:2})+\'</span> \'+chgStr(item.v,hv,item.unit) : \'<span class="flat">-</span>\'}</td>`;
    }).join(\'\')}
  </tr>`).join(\'\') + \'</tbody>\';

// ── 차트 기간 필터 유틸 ────────────────────────────────────────────────
const PERIODS = [
  {key:\'1w\', label:\'1주\',  days:7},
  {key:\'1m\', label:\'1개월\', days:30},
  {key:\'3m\', label:\'3개월\', days:90},
  {key:\'6m\', label:\'6개월\', days:180},
  {key:\'1y\', label:\'1년\',  days:365},
  {key:\'3y\', label:\'3년\',  days:365*3},
  {key:\'5y\', label:\'5년\',  days:365*5},
];

function filterByDays(series, days) {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  const cutStr = cutoff.toISOString().slice(0,10);
  return series.filter(p => p.d >= cutStr);
}

function xTickCallback(days) {
  return function(val, idx) {
    const lbl = this.getLabelForValue(val);
    if (!lbl) return \'\';
    if (days <= 30)  return lbl.slice(5);     // MM-DD
    return lbl.slice(0,7);                    // YYYY-MM
  };
}

function maxTicks(days) {
  if (days <= 7)   return 7;
  if (days <= 30)  return 6;
  if (days <= 90)  return 6;
  if (days <= 180) return 6;
  return 7;
}

// ── 기간 선택 버튼 + 차트 인스턴스 관리 ──────────────────────────────
function makeChartWithPeriod(canvasId, btnContainerId, datasetsConfig, defaultPeriodKey) {
  const el = document.getElementById(canvasId);
  const btnContainer = document.getElementById(btnContainerId);
  if (!el) return;

  let chartInst = null;
  let currentDays = PERIODS.find(p => p.key === defaultPeriodKey)?.days || 365;

  // 버튼 생성
  PERIODS.forEach(p => {
    const btn = document.createElement(\'button\');
    btn.className = \'period-btn\' + (p.key === defaultPeriodKey ? \' active\' : \'\');
    btn.textContent = p.label;
    btn.onclick = () => {
      btnContainer.querySelectorAll(\'.period-btn\').forEach(b => b.classList.remove(\'active\'));
      btn.classList.add(\'active\');
      currentDays = p.days;
      render(p.days);
    };
    btnContainer.appendChild(btn);
  });

  function render(days) {
    const isSingle = datasetsConfig.length === 1;
    const filtered = datasetsConfig.map(ds => ({
      ...ds,
      filtered: filterByDays(ds.series || [], days)
    }));
    const allDates = [...new Set(filtered.flatMap(ds => ds.filtered.map(p => p.d)))].sort();

    const chartDatasets = filtered.map(ds => {
      const map = Object.fromEntries(ds.filtered.map(p => [p.d, p.v]));
      return {
        label: ds.label,
        data: allDates.map(d => map[d] != null ? map[d] : null),
        borderColor: ds.color,
        backgroundColor: \'transparent\',
        borderWidth: 1.8, pointRadius: 0, tension: 0.1, spanGaps: true
      };
    });

    if (chartInst) {
      chartInst.data.labels = allDates;
      chartInst.data.datasets = chartDatasets;
      chartInst.options.scales.x.ticks.callback = xTickCallback(days);
      chartInst.options.scales.x.ticks.maxTicksLimit = maxTicks(days);
      chartInst.update();
    } else {
      chartInst = new Chart(el, {
        type: \'line\',
        data: { labels: allDates, datasets: chartDatasets },
        options: {
          responsive: true, maintainAspectRatio: true,
          interaction: { mode: \'index\', intersect: false },
          plugins: {
            legend: { display: !isSingle, position: \'top\', labels: { font:{size:9}, boxWidth:10 } },
            tooltip: {
              callbacks: {
                title: items => items[0].label,
                label: item => ` ${isSingle ? \'\' : item.dataset.label + \': \'}${item.parsed.y != null ? item.parsed.y.toFixed(2) : \'-\'}`
              }
            }
          },
          scales: {
            x: { ticks:{ font:{size:8}, maxRotation:0,
                   maxTicksLimit: maxTicks(days),
                   callback: xTickCallback(days)
                 }, grid:{display:false} },
            y: { ticks:{ font:{size:8}, callback: v => v.toFixed(2) }, grid:{color:\'#f0f0f0\'} }
          }
        }
      });
    }
  }

  render(currentDays);
}

// 국내 금리
makeChartWithPeriod(\'chart-kr-rates\', \'btns-kr-rates\', [
  {label:\'기준금리\',            series: DATA.charts.kr_base,  color:\'#e97132\'},
  {label:\'국고채 3Y\',          series: DATA.charts.kr3y,     color:\'#156082\'},
  {label:\'국고채 10Y\',         series: DATA.charts.kr10y,    color:\'#1a1a2e\'},
  {label:\'회사채 AA0(무보증) 3Y\',  series: DATA.charts.corp_aa0, color:\'#999\'},
], \'3m\');

// 미국 금리
makeChartWithPeriod(\'chart-us-rates\', \'btns-us-rates\', [
  {label:\'기준금리\',   series: DATA.charts.us_base, color:\'#e97132\'},
  {label:\'미국채 2Y\', series: DATA.charts.us2y,    color:\'#156082\'},
  {label:\'미국채 10Y\',series: DATA.charts.us10y,   color:\'#1a1a2e\'},
], \'3m\');

// USD/KRW
makeChartWithPeriod(\'chart-usdkrw\', \'btns-usdkrw\', [
  {label:\'USD/KRW\', series: DATA.charts.usdkrw, color:\'#e97132\'},
], \'3m\');

// Daily Macro Brief — 증권사 카드(수동) 또는 카테고리 통합(자동) 표시
const newsEl   = document.getElementById(\'news-section\');
const briefMeta = document.getElementById(\'brief-meta\');
if (briefMeta) {
  const nd = DATA.news_date || \'\';
  briefMeta.textContent = nd ? `${nd} 기준 · 주요 리포트 신규 확보 시 업데이트 예정` : \'주요 리포트 신규 확보 시 업데이트 예정\';
}
if (!DATA.news || !DATA.news.length) {
  newsEl.innerHTML = \'\';
} else {
  const esc = s => String(s).replace(/</g,\'&lt;\').replace(/>/g,\'&gt;\');
  const wrap = document.createElement(\'div\');

  // 증권사 카드 형식(firm + conclusion + bullets) 여부 확인
  const isFirmFormat = DATA.news.some(item => item.firm || item.conclusion || item.bullets);

  if (isFirmFormat) {
    // ── 증권사별 카드 (수동 요약 입력 시) ──────────────────────
    const cols = DATA.news.length || 1;
    wrap.innerHTML = `<div class="brief-grid" style="grid-template-columns:repeat(${cols},1fr)">
      ${DATA.news.map(item => {
        const firm = item.firm || \'\';
        const conclusion = item.conclusion || \'\';
        const bullets = Array.isArray(item.bullets) ? item.bullets : [];
        return `
          <div class="brief-card">
            ${firm ? `<div class="brief-firm">${esc(firm)}</div>` : \'\'}
            ${conclusion ? `<div class="brief-conclusion">${esc(conclusion)}</div>` : \'\'}
            <div class="brief-bullets">
              ${bullets.map(b => `<div class="brief-bullet">${esc(b)}</div>`).join(\'\')}
            </div>
          </div>`;
      }).join(\'\')}
    </div>`;
  } else {
    // ── 카테고리 통합 (자동 키워드 추출 시) ────────────────────
    const merged = {};
    DATA.news.forEach(item => {
      if (!item.summary) return;
      Object.entries(item.summary).forEach(([cat, sents]) => {
        if (!merged[cat]) merged[cat] = [];
        sents.forEach(s => {
          if (!merged[cat].some(existing =>
            existing.length > 0 && s.length > 0 &&
            [...s].filter(c => existing.includes(c)).length / s.length > 0.6
          )) merged[cat].push(s);
        });
      });
    });
    const CAT_ORDER = [\'금리\', \'환율\', \'경기·물가\'];
    const cats = CAT_ORDER.filter(c => merged[c]);
    const catCols = cats.length || 1;
    wrap.innerHTML = `<div class="brief-grid" style="grid-template-columns:repeat(${catCols},1fr)">
      ${cats.map(cat => `
        <div class="brief-card">
          <div class="brief-firm" style="background:#444">${cat}</div>
          <div class="brief-bullets">
            ${merged[cat].slice(0,6).map(s =>
              `<div class="brief-bullet">${esc(s)}</div>`
            ).join(\'\')}
          </div>
        </div>`).join(\'\')}
    </div>`;
  }
  newsEl.appendChild(wrap);
}
</script>
</body>
</html>'''

# 데이터 JSON 삽입
data_json = json.dumps(market_data, ensure_ascii=False)
html_out  = HTML_TEMPLATE.replace('__MARKET_DATA__', data_json)

with open(HTML_PATH, 'w', encoding='utf-8') as f:
    f.write(html_out)

print(f"\n완료: {HTML_PATH}")

# ── 5. GitHub Pages 자동 push ───────────────────────────────────────────
import subprocess, shutil

# index.html 항상 갱신
shutil.copy(HTML_PATH, os.path.join(BASE_DIR, "index.html"))

if NO_PUSH:
    # GitHub Actions에서 실행 시 — Actions가 직접 push 처리
    print("GitHub push 생략 (--no-push 모드, Actions가 처리)")
else:
    GIT   = r"C:\Program Files\Git\bin\git.exe"
    TOKEN = os.environ.get('GH_PAT', '')
    REMOTE_URL = f"https://leo-1092:{TOKEN}@github.com/leo-1092/macro-dashboard.git" if TOKEN else None
    try:
        print("GitHub push 중...")
        subprocess.run([GIT, "remote", "set-url", "origin", REMOTE_URL],
                       cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run([GIT, "add", "index.html", os.path.basename(HTML_PATH)],
                       cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run([GIT, "commit", "-m", f"Update: {TODAY_KR}"],
                       cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run([GIT, "push", "origin", "main"],
                       cwd=BASE_DIR, check=True, capture_output=True)
        print(f"  → 배포 완료: https://leo-1092.github.io/macro-dashboard")
        print(f"  → 1~3분 후 반영됩니다")
    except subprocess.CalledProcessError as e:
        print(f"  [push 오류] {e.stderr.decode('utf-8','ignore') if e.stderr else e}")
    except Exception as e:
        print(f"  [push 오류] {e}")
