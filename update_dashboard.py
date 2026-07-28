# -*- coding: utf-8 -*-
"""
매크로 Daily 대시보드 업데이트 스크립트
- 실행 시 시장 데이터 수집 + 뉴스 폴더 PDF 요약 → HTML 갱신
- 사용법: python update_dashboard.py
"""

import os, sys, re, json, glob, warnings, datetime
warnings.filterwarnings('ignore')

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

# 한국 기준금리 (수동, 최신 반영)
KR_BASE_RATE = 2.75
KR_BASE_HISTORY = {"1m": 2.75, "3m": 2.75, "6m": 2.50, "1y": 2.50, "3y": 2.50, "5y": 0.50}

# 국내 금리 (yfinance에서 한국 국채는 제한적 → 실제값 수동 + yfinance 보조)
# 국고채 3Y, 10Y: KR 데이터 수집 시도
kr3y_v,  kr3y_h  = fetch("KR3YT=X")
kr10y_v, kr10y_h = fetch("KR10YT=X")

# yfinance 미지원 시 최근 알려진 값 사용
if kr3y_v  is None: kr3y_v,  kr3y_h  = 3.852, {"1m":3.80,"3m":3.60,"6m":3.30,"1y":3.10,"3y":3.50,"5y":1.50}
if kr10y_v is None: kr10y_v, kr10y_h = 4.300, {"1m":4.25,"3m":4.05,"6m":3.80,"1y":3.80,"3y":4.00,"5y":2.10}

# 회사채 AA0, 금융채 AAA, CD (수동 — Bloomberg/KOFIA 기준 최근값)
corp_aa0  = {"v": 4.50, "h": {"1m":4.45,"3m":4.20,"6m":3.95,"1y":3.80,"3y":4.30,"5y":2.30}}
fin_aaa   = {"v": 4.20, "h": {"1m":4.15,"3m":3.90,"6m":3.65,"1y":3.50,"3y":4.00,"5y":1.90}}
cd_rate   = {"v": 3.85, "h": {"1m":3.83,"3m":3.70,"6m":3.50,"1y":3.45,"3y":3.60,"5y":0.90}}

# 미국 금리
us2y_v,   us2y_h   = fetch("^FiveYear")  # 2Y 대안
us2y_v2,  us2y_h2  = fetch("^IRX")
if us2y_v is None:
    us2y_v, us2y_h = 4.16, {"1m":4.20,"3m":4.30,"6m":4.40,"1y":4.80,"3y":4.50,"5y":0.50}

us10y_v,  us10y_h  = fetch("^TNX")
if us10y_v is None:
    us10y_v, us10y_h = 4.57, {"1m":4.50,"3m":4.40,"6m":4.30,"1y":4.60,"3y":4.00,"5y":1.50}

US_BASE_RATE = 3.75
US_BASE_HISTORY = {"1m": 3.75, "3m": 3.75, "6m": 4.25, "1y": 5.25, "3y": 0.25, "5y": 0.25}

# SOFR (수동 — 연준 기준금리와 근접)
sofr_v = 3.73
sofr_h = {"1m":3.73,"3m":3.73,"6m":4.23,"1y":5.23,"3y":0.23,"5y":0.23}

# 원자재
wti_v,   wti_h   = fetch("CL=F")
brent_v, brent_h = fetch("BZ=F")
# 두바이유 (yfinance 미지원 → WTI 기반 추정 또는 수동)
dubai_v = round((wti_v or 82) * 1.02, 2)
dubai_h = {k: round(v*1.02, 2) for k, v in (wti_h or {}).items()}

gold_v, gold_h = fetch("GC=F")

# 환율
usdkrw_v, usdkrw_h = fetch("KRW=X")
eurkrw_v, eurkrw_h = fetch("EURKRW=X")
jpykrw_v, jpykrw_h = fetch("JPYKRW=X")
dxy_v,    dxy_h    = fetch("DX-Y.NYB")

# 차트용 시계열
print("  시계열 데이터 수집 중...")
us10y_series  = fetch_series("^TNX")
wti_series    = fetch_series("CL=F")
gold_series   = fetch_series("GC=F")
usdkrw_series = fetch_series("KRW=X")

print(f"  완료 — WTI:{wti_v}, Gold:{gold_v}, USD/KRW:{usdkrw_v}, US10Y:{us10y_v}")

# ── 2. PDF 뉴스 요약 ────────────────────────────────────────────────────
ECON_KEYWORDS = [
    '금리','기준금리','국채','채권','금통위','연준','FOMC','Fed','통화정책',
    '환율','원달러','달러','외환','유가','원유','WTI','브렌트','인플레이션',
    'CPI','물가','국고채','회사채','스프레드','금융시장','증시','주가','코스피',
    'GDP','성장률','경기','수출','무역','ISM','PMI','실업','고용','긴축','완화',
    '인상','인하','SOFR','리보','스왑','RP','CP','CD','자금','유동성','재정',
    '미국','한국은행','중앙은행','연방준비','시장','투자','금융','경제','증권',
    '달러화','원화','엔화','유로','위안','환시','금값','유증','펀드','채권시장',
    '국제','글로벌','신흥국','선진국','무역수지','경상수지','외환보유','외채'
]

def extract_econ_content(pdf_path):
    """PDF에서 경제 관련 단락만 추출"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

        paragraphs = re.split(r'\n{2,}|(?<=[.!?])\s*\n', full_text)
        econ_paras = []
        for para in paragraphs:
            para = para.strip()
            if len(para) < 20:
                continue
            if any(kw in para for kw in ECON_KEYWORDS):
                econ_paras.append(para)

        return econ_paras[:30]  # 최대 30개 단락
    except Exception as e:
        return [f"PDF 읽기 오류: {e}"]

print("뉴스 PDF 처리 중...")
news_items = []
pdf_files = sorted(glob.glob(os.path.join(NEWS_DIR, "*.pdf")), reverse=True)[:5]  # 최신 5개

for pdf_path in pdf_files:
    fname = os.path.basename(pdf_path)
    date_m = re.search(r'(\d{4}\.\d{2}\.\d{2})', fname)
    date_str = date_m.group(1) if date_m else fname
    paras = extract_econ_content(pdf_path)
    if paras:
        news_items.append({"date": date_str, "file": fname, "paras": paras})
        print(f"  {fname}: {len(paras)}개 단락 추출")
    else:
        print(f"  {fname}: 경제 관련 내용 없음")

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
            mk(corp_aa0["v"],  corp_aa0["h"],  "회사채 AA0 (무보증)", "%"),
            mk(fin_aaa["v"],   fin_aaa["h"],   "금융채 AAA", "%"),
            mk(cd_rate["v"],   cd_rate["h"],   "CD 금리", "%"),
        ]
    },
    "us": {
        "title": "해외 금리",
        "items": [
            mk(US_BASE_RATE, US_BASE_HISTORY, "미 연준 기준금리", "%"),
            mk(us2y_v,  us2y_h,  "미국채 2Y", "%"),
            mk(us10y_v, us10y_h, "미국채 10Y", "%"),
            mk(sofr_v,  sofr_h,  "SOFR", "%"),
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
    "gold": {
        "title": "국제 금",
        "items": [
            mk(gold_v, gold_h, "금 현물", "$/oz"),
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
    "charts": {
        "us10y":  us10y_series,
        "wti":    wti_series,
        "gold":   gold_series,
        "usdkrw": usdkrw_series,
    },
    "news": news_items
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
  grid-template-columns: repeat(5, 1fr);
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
td { padding: 7px 10px; border-bottom: 1px solid #f0f0f0; text-align: right; }
td:first-child { text-align: left; color: #444; font-weight: 600; }
td:nth-child(2) { text-align: center; color: #888; font-size: 10px; }
tr:hover td { background: #fafbff; }
.up   { color: #e00; font-weight: 600; }
.down { color: #156082; font-weight: 600; }
.flat { color: #888; }

/* 차트 */
.chart-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; margin-bottom: 20px;
}
.chart-card {
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.07);
  padding: 14px;
}
.chart-label { font-size: 11px; font-weight: 700; color: #1a1a2e; margin-bottom: 10px; }
canvas { max-height: 140px; }

/* 뉴스 */
.news-section { margin-bottom: 20px; }
.news-date {
  font-size: 12px; font-weight: 700; color: #1a1a2e;
  background: #fff; border-radius: 10px; padding: 10px 16px;
  margin-bottom: 8px; box-shadow: 0 1px 5px rgba(0,0,0,0.07);
  display: flex; align-items: center; gap: 8px;
}
.news-date .dot { width: 8px; height: 8px; border-radius: 50%; background: #e97132; display:inline-block; }
.news-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
.news-para {
  background: #fff; border-radius: 8px;
  padding: 10px 12px; font-size: 11px; color: #444;
  line-height: 1.7; border-left: 3px solid #e97132;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
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

  <!-- 기간별 변화 테이블 -->
  <div class="section-divider">HISTORICAL CHANGE</div>
  <div class="change-section">
    <div class="change-wrap"><table id="change-table"></table></div>
  </div>

  <!-- 시계열 차트 -->
  <div class="section-divider">TREND CHARTS</div>
  <div class="chart-grid">
    <div class="chart-card"><div class="chart-label">미국채 10Y (%)</div><canvas id="chart-us10y"></canvas></div>
    <div class="chart-card"><div class="chart-label">WTI 유가 ($/bbl)</div><canvas id="chart-wti"></canvas></div>
    <div class="chart-card"><div class="chart-label">금 현물 ($/oz)</div><canvas id="chart-gold"></canvas></div>
    <div class="chart-card"><div class="chart-label">USD/KRW (원)</div><canvas id="chart-usdkrw"></canvas></div>
  </div>

  <!-- 뉴스 요약 -->
  <div class="section-divider">ECONOMIC NEWS SUMMARY</div>
  <div class="news-section" id="news-section"></div>
</div>

<script>
// ── 데이터 ──────────────────────────────────────────────────────────────
const DATA = __MARKET_DATA__;

// ── 렌더 ──────────────────────────────────────────────────────────────
document.getElementById(\'updated-date\').textContent = \'업데이트: \' + DATA.updated;
document.getElementById(\'badge-date\').textContent = DATA.updated;

const SECTIONS = [\'domestic\',\'us\',\'oil\',\'gold\',\'fx\'];
const SECTION_COLORS = {domestic:\'#1a1a2e\',us:\'#156082\',oil:\'#7b4f00\',gold:\'#b8860b\',fx:\'#333\'};

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
        <span><span class="ind-value">${item.v != null ? item.v.toLocaleString() : \'-\'}</span><span class="ind-unit">${item.unit}</span></span>
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
  <th>지표</th><th>단위</th><th>현재</th>
  ${periods.map(p => `<th>${periodLabels[p]}</th>`).join(\'\')}
</tr></thead><tbody>`
  + allItems.map(item => `<tr>
    <td>${item.label}</td>
    <td style="text-align:center;color:#888;font-size:10px;">${item.unit}</td>
    <td style="font-weight:700;color:#1a1a2e;">${item.v != null ? item.v.toLocaleString() : \'-\'}</td>
    ${periods.map(p => {
      const hv = item.h && item.h[p] != null ? item.h[p] : null;
      const cls = chgClass(item.v, hv);
      return `<td>${hv != null ? \'<span style="font-size:10px;color:#999;">\'+hv.toLocaleString()+\'</span> \'+chgStr(item.v,hv,item.unit) : \'<span class="flat">-</span>\'}</td>`;
    }).join(\'\')}
  </tr>`).join(\'\') + \'</tbody>\';

// 차트
function makeLineChart(id, series, color) {
  if (!series || !series.length) return;
  const labels = series.map(p => p.d);
  const vals   = series.map(p => p.v);
  new Chart(document.getElementById(id), {
    type: \'line\',
    data: { labels, datasets: [{ data: vals, borderColor: color,
      backgroundColor: \'transparent\', borderWidth: 1.5,
      pointRadius: 0, tension: 0.2 }] },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { font:{size:8}, maxRotation:0, maxTicksLimit:6 }, grid:{display:false} },
        y: { ticks: { font:{size:8} }, grid:{color:\'#f0f0f0\'} }
      }
    }
  });
}
makeLineChart(\'chart-us10y\',  DATA.charts.us10y,  \'#156082\');
makeLineChart(\'chart-wti\',    DATA.charts.wti,    \'#7b4f00\');
makeLineChart(\'chart-gold\',   DATA.charts.gold,   \'#b8860b\');
makeLineChart(\'chart-usdkrw\', DATA.charts.usdkrw, \'#e97132\');

// 뉴스
const newsEl = document.getElementById(\'news-section\');
if (!DATA.news || !DATA.news.length) {
  newsEl.innerHTML = \'<div style="color:#aaa;font-size:12px;padding:12px;">뉴스 폴더에 PDF가 없습니다.</div>\';
} else {
  DATA.news.forEach(item => {
    const div = document.createElement(\'div\');
    div.innerHTML = `<div class="news-date"><span class="dot"></span>${item.date} — ${item.file}</div>
      <div class="news-grid">${item.paras.map(p =>
        `<div class="news-para">${p.replace(/</g,\'&lt;\').replace(/>/g,\'&gt;\')}</div>`
      ).join(\'\')}</div>`;
    newsEl.appendChild(div);
  });
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
print(f"  → 브라우저에서 열어 확인하세요")
