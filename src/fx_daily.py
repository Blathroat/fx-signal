#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""USD/CNY 底部信号监控。

采集 -> 指标 -> 8 项信号 -> 文字 / JSON / 走势图。

用法:
  python3 fx_daily.py                 # 中文文字版（兜底）
  python3 fx_daily.py --json          # JSON 快照（给模型）
  python3 fx_daily.py --chart         # 生成 chart.png
  python3 fx_daily.py --chart --send  # 生成并推送图片
"""
import json, os, re, math, sys, zipfile, subprocess, urllib.request, datetime as dt
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
DATA = os.path.join(ROOT, "data")
CONF = os.path.join(ROOT, "config", "settings.json")
for d in (DATA,):
    os.makedirs(d, exist_ok=True)

STATE = os.path.join(DATA, "state.json")
JSH_XLSX = os.path.join(DATA, "jsh.xlsx")
CHART = os.path.join(DATA, "chart.png")
JSH_URL = "https://www.safe.gov.cn/safe/file/file/20261020/4eeaa0fb8f90475fbd5de27e1cd0ea24.xlsx"
UA = {"User-Agent": "Mozilla/5.0 (fx-monitor)"}
TZ = dt.timezone(dt.timedelta(hours=8))
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

def conf():
    c = {}
    if os.path.exists(CONF):
        try: c = json.load(open(CONF))
        except Exception: c = {}
    c["channel"] = os.environ.get("FX_QQ_CHANNEL") or c.get("channel") or "qqbot"
    c["target"] = os.environ.get("FX_QQ_TARGET") or c.get("target") or ""
    return c

def get_bytes(url, headers=None, timeout=25):
    h = dict(UA); h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()

def getj(url, timeout=25):
    return json.loads(get_bytes(url, timeout=timeout).decode("utf-8", "replace"))

# ---------------- 数据源 ----------------
def fetch_sina():
    """在岸 + 离岸实时报价"""
    raw = get_bytes("https://hq.sinajs.cn/list=fx_susdcny,fx_susdcnh",
                    {"Referer": "https://finance.sina.com.cn"}).decode("gbk", "replace")
    out = {}
    for line in raw.split(";"):
        if "=" not in line or '"' not in line:
            continue
        k = "CNY" if "fx_susdcny" in line else ("CNH" if "fx_susdcnh" in line else None)
        if not k:
            continue
        f = line.split('"')[1].split(",")
        if len(f) < 9:
            continue
        out[k] = {"last": float(f[8]), "time": f[0], "date": f[17] if len(f) > 17 else ""}
    if "CNY" not in out:
        raise RuntimeError("sina parse failed")
    return out

def fetch_series():
    """ECB 日收盘（用于全部技术指标，口径统一）"""
    today = dt.datetime.now(TZ).date()
    j = getj("https://api.frankfurter.dev/v1/%s..%s?base=USD&symbols=CNY"
             % (today.replace(year=today.year - 3), today))
    return sorted((k, v["CNY"]) for k, v in j["rates"].items()), j.get("date")

def fetch_dxy_hist():
    today = dt.datetime.now(TZ).date()
    j = getj("https://api.frankfurter.dev/v1/%s..%s?base=USD&symbols=EUR,JPY,GBP,CAD,SEK,CHF"
             % (today.replace(year=today.year - 1), today))
    def f(r):
        return (50.14348112 * (1/r["EUR"]) ** -0.576 * r["JPY"] ** 0.136
                * (1/r["GBP"]) ** -0.119 * r["CAD"] ** 0.091 * r["SEK"] ** 0.042
                * r["CHF"] ** 0.036)
    return sorted((k, f(v)) for k, v in j["rates"].items())

def fetch_fixing():
    """CFETS 官方中间价（每日 9:15）"""
    j = getj("https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/ccpr.json")
    d = (j.get("data") or {}).get("lastDate", "")[:10]
    for r in j.get("records", []):
        if r.get("vrtEName") == "USD/CNY" or "美元/人民币" in str(r.get("vrtName", "")):
            return float(r["price"]), d
    return None, None

def fetch_sofr():
    return getj("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")["refRates"][0]["percentRate"]

def _col(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    c = 0
    for ch in m.group(1):
        c = c * 26 + (ord(ch) - 64)
    return c, int(m.group(2))

def read_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    rels = {r.get("Id"): r.get("Target").lstrip("/")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    out = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find(NS + "sheets"):
        tgt = rels.get(sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"), "")
        if not tgt.startswith("xl/"):
            tgt = "xl/" + tgt
        if tgt not in z.namelist():
            continue
        cells = {}
        for c in ET.fromstring(z.read(tgt)).iter(NS + "c"):
            ref = c.get("r"); v = c.find(NS + "v")
            if not ref or v is None or v.text is None:
                continue
            raw = v.text
            if c.get("t") == "s":
                try: val = shared[int(raw)]
                except Exception: val = raw
            else:
                try: val = float(raw)
                except Exception: val = raw
            cc, rr = _col(ref)
            cells[(rr, cc)] = val
        out[sh.get("name")] = cells
    return out

def fetch_jsh():
    """外管局银行结售汇差额（亿美元，月度，滞后约 20 天）"""
    try:
        d = get_bytes(JSH_URL, timeout=40)
        if len(d) > 20000:
            open(JSH_XLSX, "wb").write(d)
    except Exception:
        pass
    if not os.path.exists(JSH_XLSX):
        return []
    try:
        book = read_xlsx(JSH_XLSX)
    except Exception:
        return []
    name = next((k for k in book if "美元" in k and "月" in k), None)
    if not name:
        return []
    cells = book[name]
    hdr = {c: (dt.datetime(1899, 12, 30) + dt.timedelta(days=v)).date()
           for (r, c), v in cells.items() if r == 4 and isinstance(v, float) and v > 30000}
    out = []
    for c in sorted(hdr)[-18:]:
        if cells.get((25, c)) is not None:
            out.append([hdr[c].strftime("%Y-%m"), round(cells[(25, c)], 1)])
    return out

# ---------------- 指标 ----------------
def ma(x, k):
    return sum(x[-k:]) / k if len(x) >= k else None

def rsi(x, k=14):
    """Wilder 平滑 RSI。用统一口径序列计算，不混入实时报价。"""
    if len(x) < k + 1:
        return None
    gains = losses = 0.0
    for i in range(1, k + 1):
        d = x[i] - x[i - 1]
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / k, losses / k
    for i in range(k + 1, len(x)):
        d = x[i] - x[i - 1]
        ag = (ag * (k - 1) + max(d, 0.0)) / k
        al = (al * (k - 1) + max(-d, 0.0)) / k
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def ann_vol(x, k):
    if len(x) < k + 1:
        return None
    r = [math.log(x[i] / x[i - 1]) for i in range(len(x) - k, len(x))]
    m = sum(r) / len(r)
    return (sum((a - m) ** 2 for a in r) / (len(r) - 1)) ** 0.5 * (231 ** 0.5) * 100

def down_streak(x):
    n = 0
    for i in range(len(x) - 1, 0, -1):
        if x[i] < x[i - 1]: n += 1
        else: break
    return n

# ---------------- 汇总 ----------------
def build():
    now = dt.datetime.now(TZ)
    rows, hist_date = fetch_series()
    dates = [r[0] for r in rows]
    vals = [r[1] for r in rows]

    spot = cnh = None
    try:
        s = fetch_sina()
        spot, cnh = s["CNY"]["last"], (s.get("CNH") or {}).get("last")
        spot_date, spot_time, src = s["CNY"]["date"] or now.strftime("%Y-%m-%d"), s["CNY"]["time"], "sina"
    except Exception:
        spot, spot_date, spot_time, src = vals[-1], dates[-1], "", "ecb"

    try:
        fixing, fixing_date = fetch_fixing()
    except Exception:
        fixing, fixing_date = None, None
    jsh = fetch_jsh()
    try:
        dxy = fetch_dxy_hist()
    except Exception:
        dxy = []
    try:
        sofr = fetch_sofr()
    except Exception:
        sofr = None

    st = {}
    if os.path.exists(STATE):
        try: st = json.load(open(STATE))
        except Exception: st = {}
    fh = st.get("fixings", {})
    if fixing and fixing_date:
        fh[fixing_date] = fixing
    st["fixings"] = dict(sorted(fh.items())[-180:])
    st["last_run"] = now.isoformat()
    try:
        json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    fix_hist = sorted(st["fixings"].items())

    m20, m60, m250 = ma(vals, 20), ma(vals, 60), ma(vals, 250)
    r14 = rsi(vals)
    v20 = ann_vol(vals, 20)
    dstreak = down_streak(vals)

    seg = vals[-500:]
    peak = max(seg)
    peak_date = dates[-500:][seg.index(peak)]
    dd = (spot / peak - 1) * 100
    months = (dt.datetime.strptime(spot_date, "%Y-%m-%d") - dt.datetime.strptime(peak_date, "%Y-%m-%d")).days / 30.44

    same_day = bool(fixing_date and fixing_date == spot_date)
    gap = (spot / fixing - 1) * 100 if (fixing and same_day) else None
    spread = (cnh - spot) * 10000 if cnh else None

    # 中间价连续调贬（USD/CNY 中间价上行 = 人民币走弱）
    fstreak = 0
    for i in range(len(fix_hist) - 1, 0, -1):
        if fix_hist[i][1] > fix_hist[i - 1][1]:
            fstreak += 1
        else:
            break
    fix_n = len(fix_hist)

    G = []

    # --- 政策面 ---
    pol = []
    if gap is not None:
        pol.append(["ok" if gap < -0.15 else "no", "中间价压制升值",
                    "中间价高于市价 %.2f%%（官方仍在压升值节奏）" % abs(gap) if gap < 0
                    else "中间价低于市价 %.2f%%（官方已不压）" % abs(gap)])
    else:
        pol.append(["skip", "中间价核对", "中间价与现价非同日（%s）" % (fixing_date or "-")])
    if fix_n >= 6:
        pol.append(["ok" if fstreak >= 5 else "no", "中间价转调贬",
                    "已连续 %d 日上调（人民币被引导走弱）" % fstreak])
    else:
        pol.append(["skip", "中间价转调贬", "样本积累中 %d/6 日" % fix_n])
    G.append(("政策面", pol))

    # --- 资金面 ---
    flow = []
    if spread is not None:
        flow.append(["ok" if spread > 5 else "no", "离岸转弱",
                    "CNH 高于在岸 %.0f 点（离岸先转向）" % spread if spread > 5
                    else "CNH 低于在岸 %.0f 点（离岸仍看多人民币）" % abs(spread)])
    else:
        flow.append(["skip", "离岸价差", "无数据"])
    if len(jsh) >= 3:
        b0, bp, b2 = jsh[-1][1], jsh[-2][1], jsh[-3][1]
        shrink = b0 < bp < b2
        flow.append(["ok" if shrink else "no", "结汇盘衰竭",
                    "%s 顺差 %.0f 亿美元，环比 %+.0f%s" % (
                        jsh[-1][0], b0, b0 - bp, "（连续收窄）" if shrink else "（仍在扩大）")])
    else:
        flow.append(["skip", "结汇盘衰竭", "无数据"])
    G.append(("资金面", flow))

    # --- 价格面 ---
    px = []
    px.append(["ok" if dd <= -8.5 else "no", "跌幅近历史下沿",
               "本轮 %.2f%%（历史单轮 -8%%~-12%%）" % dd])
    px.append(["ok" if (v20 is not None and v20 < 1.0) else "no", "波动率压缩",
               "20 日年化 %.2f%%（压缩后往往先破位，方向待定）" % (v20 or 0)])
    if r14 is not None:
        px.append(["ok" if r14 < 25 else "no", "RSI 超卖",
                   "RSI14 %.1f，连续 %d 日下跌" % (r14, dstreak)])
    else:
        px.append(["skip", "RSI 超卖", "数据不足"])
    px.append(["ok" if (m250 and spot > m250) else "no", "站上 MA250",
               "距 MA250（%.4f）%+.2f%%" % (m250, (m250 / spot - 1) * 100) if m250 else "无"])
    G.append(("价格面", px))

    flat = [x for _, items in G for x in items]
    score = sum(1 for x in flat if x[0] == "ok")
    total = sum(1 for x in flat if x[0] in ("ok", "no", "skip"))
    counted = sum(1 for x in flat if x[0] in ("ok", "no"))

    return {
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "spot": spot, "spot_date": spot_date, "spot_time": spot_time, "source": src,
        "cnh": cnh, "cnh_spread_pips": spread,
        "fixing": fixing, "fixing_date": fixing_date, "gap_pct": gap,
        "fixing_streak_up": fstreak, "fixing_samples": fix_n,
        "ma20": m20, "ma60": m60, "ma250": m250,
        "rsi14": r14, "vol20": v20, "down_streak": dstreak,
        "peak": peak, "peak_date": peak_date, "drawdown_pct": dd, "months": months,
        "settle": jsh, "sofr": sofr,
        "dxy": (dxy[-1][1] if dxy else None),
        "dxy_1y_chg": ((dxy[-1][1] / dxy[0][1] - 1) * 100 if len(dxy) > 2 else None),
        "hist_date": hist_date,
        "groups": [{"name": n, "items": items} for n, items in G],
        "score": score, "counted": counted, "total": total,
        "_series_dates": dates[-780:], "_series_vals": vals[-780:],
        "_dxy_hist": [[d, round(v, 2)] for d, v in dxy[-260:]] if dxy else [],
    }

MARK = {"ok": "✅", "no": "❌", "skip": "⏳"}

def text_report(s):
    L = ["💱 人民币汇率日报 · %s" % s["generated"],
         "【现价】USD/CNY %.4f（%s %s %s）" % (s["spot"], s["source"], s["spot_time"], s["spot_date"])]
    if s["cnh"]:
        L.append("【离岸】USD/CNH %.4f（价差 %+.0f 点）" % (s["cnh"], s["cnh_spread_pips"]))
    if s["fixing"]:
        if s["gap_pct"] is not None:
            L.append("【中间价】%.4f　市场%s于中间价 %.2f%%"
                     % (s["fixing"], "强" if s["gap_pct"] < 0 else "弱", abs(s["gap_pct"])))
        else:
            L.append("【中间价】%.4f（%s）" % (s["fixing"], s["fixing_date"]))
    L.append("【位置】MA20 %.4f｜MA60 %.4f｜MA250 %.4f" % (s["ma20"], s["ma60"], s["ma250"]))
    L.append("【极端度】RSI14 %.1f（连跌 %d 日）｜20 日波动率 %.2f%%"
             % (s["rsi14"] or 0, s["down_streak"], s["vol20"] or 0))
    L.append("【本轮】自 %.4f 高点 %+.2f%%（%.1f 个月）" % (s["peak"], s["drawdown_pct"], s["months"]))
    if s["settle"]:
        L.append("【结售汇】%s 差额 %.0f 亿美元" % (s["settle"][-1][0], s["settle"][-1][1]))
    L.append("")
    for g in s["groups"]:
        L.append("【%s】" % g["name"])
        for mk, nm, de in g["items"]:
            L.append("%s %s｜%s" % (MARK[mk], nm, de))
    L.append("")
    L.append("【信号 %d/%d 已亮】（建议与执行由 openclaw 模型生成）" % (s["score"], s["counted"]))
    return "\n".join(L)

if __name__ == "__main__":
    try:
        s = build()
        want_json = "--json" in sys.argv
        want_chart = "--chart" in sys.argv
        if want_json:
            print(json.dumps({k: v for k, v in s.items() if not k.startswith("_")},
                             ensure_ascii=False, indent=1))
        if want_chart:
            sys.path.insert(0, BASE)
            import render
            strip = [("SPOT", "%.4f" % s["spot"], (198, 58, 52)),
                     ("CNH", "%.4f" % s["cnh"] if s["cnh"] else "n/a", (0, 122, 180)),
                     ("FIXING", "%.4f" % s["fixing"] if s["fixing"] else "n/a", (128, 64, 160)),
                     ("GAP", "%+.2f%%" % s["gap_pct"] if s["gap_pct"] is not None else "n/a", (192, 134, 36)),
                     ("RSI14", "%.1f" % (s["rsi14"] or 0), (198, 58, 52)),
                     ("VOL20", "%.2f%%" % (s["vol20"] or 0), (32, 138, 108)),
                     ("SIGNALS", "%d/%d" % (s["score"], s["counted"]), (48, 108, 186))]
            render.render(CHART, s["_series_dates"], s["_series_vals"], s["settle"],
                          s["_dxy_hist"], {"strip": strip}, s["spot_date"])
            print("chart: " + CHART)
            if "--send" in sys.argv:
                c = conf()
                try:
                    r = subprocess.run(
                        ["node", "dist/index.js", "message", "send",
                         "--channel", c["channel"], "--target", c["target"],
                         "--media", CHART, "-m", "USD/CNY 多信息走势图"],
                        cwd="/app", capture_output=True, text=True, timeout=120)
                    print("send: rc=%s %s" % (r.returncode, (r.stdout or r.stderr or "")[-200:]))
                except Exception as e:
                    print("send failed: %s" % e)
        if not want_json and not want_chart:
            print(text_report(s))
    except Exception as e:
        print("⚠️ 生成失败：%s: %s" % (type(e).__name__, e))
