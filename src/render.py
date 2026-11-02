# -*- coding: utf-8 -*-
"""多信息走势图：USD/CNY + 均线 + 结售汇差额 + 美元指数 + 指标条"""
from chartlib import Canvas

INK   = (26, 40, 56)
GRID  = (228, 233, 238)
RED   = (198, 58, 52)
GREEN = (32, 138, 108)
BLUE  = (48, 108, 186)
GREY  = (122, 132, 142)
AMBER = (192, 134, 36)
SOFT  = (246, 248, 250)

def _ma(x, k):
    out = [None]*(k-1)
    s = sum(x[:k]); out.append(s/k)
    for i in range(k, len(x)):
        s += x[i]-x[i-k]; out.append(s/k)
    return out

def _sc(lo, hi, top, bot):
    if hi <= lo: hi = lo + 1
    return lambda v: bot - (v-lo)/(hi-lo)*(bot-top)

def render(out_path, dates, vals, settle, dxy, info, title_right=""):
    W, H = 1000, 1240
    c = Canvas(W, H)
    L, R = 86, 936

    c.text(L, 24, "USD/CNY  SIGNAL  MONITOR", INK, 2)
    c.line(L, 50, R, 50, GRID, 2)
    if title_right:
        c.text(R - c.tw(title_right), 28, title_right, GREY, 1)

    # ---------- 指标条 ----------
    items = info.get("strip", [])
    if items:
        bw = (R-L)/len(items)
        c.rect_fill(L, 60, R, 108, SOFT)
        for i, (k, v, col) in enumerate(items):
            x0 = L + bw*i + 8
            c.text(x0, 68, k, GREY, 1)
            c.text(x0, 84, v, col, 2)
        c.line(L, 108, R, 108, GRID, 1)

    # ---------- 面板1 ----------
    top, bot = 136, 470
    seg = min(len(vals), 780)
    v = vals[-seg:]; d = dates[-seg:]
    lo, hi = min(v), max(v); pad = (hi-lo)*0.08
    lo -= pad; hi += pad
    y = _sc(lo, hi, top, bot)
    n = len(v)
    X = lambda i: L + (R-L)*i/max(1, n-1)

    for k in range(5):
        yy = top + (bot-top)*k/4
        c.line(L, yy, R, yy, GRID)
        lab = "%.2f" % (hi - (hi-lo)*k/4)
        c.text(L-8-c.tw(lab), int(yy)-3, lab, GREY, 1)

    for k, (col, name) in enumerate([(AMBER,"MA250"),(GREEN,"MA60"),(BLUE,"MA20")]):
        m = _ma(vals, int(name[2:]))[-seg:]
        pts = [(X(i), y(m[i])) for i in range(n) if m[i] is not None]
        for i in range(1, len(pts)):
            c.line(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1], col, 2)
        c.text(L+10+k*74, bot+12, name, col, 1)

    for i in range(1, n):
        c.line(X(i-1), y(v[i-1]), X(i), y(v[i]), INK, 2)
    # 现价标记
    cy = y(v[-1])
    c.line(L, cy, R, cy, RED, 1)
    c.dot(X(n-1), cy, RED, 4)
    lab = "%.4f" % v[-1]
    lx, ly = R - c.tw(lab, 2) - 14, int(cy) - 30
    c.rect_fill(lx-4, ly-3, lx + c.tw(lab, 2) + 4, ly + 17, (255,255,255))
    c.text(lx, ly, lab, RED, 2)

    c.text(L+10, top-16, "SPOT  +  MA20 / MA60 / MA250", INK, 1)
    c.text(R - c.tw(dates[-1]) - 10, bot+12, dates[-1], GREY, 1)

    # ---------- 面板2 ----------
    p2t, p2b = 540, 730
    c.text(L, p2t-18, "BANK FX SETTLEMENT BALANCE  (USD BN, MONTHLY)", INK, 1)
    if settle:
        s = settle[-16:]
        vmax = max(abs(x[1]) for x in s) or 1
        neg = any(x[1] < 0 for x in s)
        if neg:
            zero = (p2t+p2b)/2; hi2, lo2 = vmax, -vmax
        else:
            zero = p2b; hi2, lo2 = vmax*1.12, 0
        y2 = _sc(lo2, hi2, p2t, p2b)
        c.line(L, zero, R, zero, GRID, 2)
        bw = (R-L)/len(s)*0.55
        for i, (mon, val) in enumerate(s):
            cx = L + (R-L)*(i+0.5)/len(s)
            yv = y2(val)
            col = GREEN if val >= 0 else RED
            c.rect_fill(cx-bw/2, min(yv, zero), cx+bw/2, max(yv, zero), col)
            c.text(cx - c.tw(mon,1)/2, p2b+6, mon, GREY, 1)
        c.text(L-8-c.tw("%.0f" % hi2), p2t-3, "%.0f" % hi2, GREY, 1)
        last = s[-1][1]
        c.text(L+10, p2t-2, "LAST %.0f" % last, GREEN if last >= 0 else RED, 1)

    # ---------- 面板3 ----------
    p3t, p3b = 800, 1150
    c.text(L, p3t-18, "DOLLAR INDEX  (DXY)", INK, 1)
    if dxy and len(dxy) > 2:
        dv = [x[1] for x in dxy]
        lo3, hi3 = min(dv), max(dv); pad3 = (hi3-lo3)*0.12 or 1
        y3 = _sc(lo3-pad3, hi3+pad3, p3t, p3b)
        for k in range(4):
            yy = p3t + (p3b-p3t)*k/3
            c.line(L, yy, R, yy, GRID)
            lab = "%.0f" % (hi3+pad3 - (hi3-lo3+2*pad3)*k/3)
            c.text(L-8-c.tw(lab), int(yy)-3, lab, GREY, 1)
        for i in range(1, len(dv)):
            c.line(L + (R-L)*(i-1)/max(1,len(dv)-1), y3(dv[i-1]),
                   L + (R-L)*i/max(1,len(dv)-1), y3(dv[i]), BLUE, 2)
        lab = "%.1f" % dv[-1]
        lx = R - c.tw(lab, 2) - 14; ly = int(y3(dv[-1])) - 30
        c.rect_fill(lx-4, ly-3, lx + c.tw(lab, 2) + 4, ly + 17, (255,255,255))
        c.text(lx, ly, lab, BLUE, 2)

    c.line(L, H-40, R, H-40, GRID, 2)
    c.text(L, H-28, "SOURCE: SINA / CFETS / SAFE / ECB / NY FED", GREY, 1)
    c.text(R - c.tw("AUTO-GENERATED"), H-28, "AUTO-GENERATED", GREY, 1)
    c.png(out_path)
    return out_path