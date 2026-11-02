# -*- coding: utf-8 -*-
"""候选模型横向对比：谁真的能预测"""
import json, math, os
import numpy as np

D = os.path.dirname(os.path.abspath(__file__))
px = [(r[0], float(r[1])) for r in json.load(open(os.path.join(D, "usdcny.json")))]
dx = dict(json.load(open(os.path.join(D, "dxy.json"))))
dates = [d for d, _ in px]; v = np.array([x for _, x in px]); n = len(v)
dv = np.array([dx.get(d, np.nan) for d in dates])

def roll_max(x, k): return np.array([x[max(0, i-k+1):i+1].max() for i in range(len(x))])
def roll_mean(x, k):
    out = np.full(len(x), np.nan); c = np.cumsum(np.insert(x, 0, 0))
    out[k-1:] = (c[k:]-c[:-k])/k; return out
def pct(x, k):
    o = np.full(len(x), np.nan); o[k:] = (x[k:]/x[:-k]-1)*100; return o
def rsi(x, k=14):
    o = np.full(len(x), np.nan); g = l = 0.0
    for i in range(1, k+1):
        d = x[i]-x[i-1]; g += max(d, 0); l += max(-d, 0)
    ag, al = g/k, l/k; o[k] = 100-100/(1+ag/al) if al > 0 else 100
    for i in range(k+1, len(x)):
        d = x[i]-x[i-1]; ag = (ag*(k-1)+max(d, 0))/k; al = (al*(k-1)+max(-d, 0))/k
        o[i] = 100-100/(1+ag/al) if al > 0 else 100
    return o
def avol(x, k):
    r = np.diff(np.log(x)); o = np.full(len(x), np.nan)
    for i in range(k, len(x)):
        w = r[i-k:i]; o[i] = w.std(ddof=1)*math.sqrt(231)*100
    return o

dd = (v/roll_max(v, 500)-1)*100
vol20 = avol(v, 20); vol60 = avol(v, 60)
ma250 = roll_mean(v, 250)
dist250 = (v/ma250-1)*100
r14 = rsi(v); mom60 = pct(v, 60); mom120 = pct(v, 120)
dxy60 = pct(dv, 60); div120 = mom120-dxy60

H = 60
fwd = np.full(n, np.nan); fwd[:n-H] = (v[H:]/v[:n-H]-1)*100

FEATS = {"dd": dd, "vol20": vol20, "dist250": dist250, "rsi": r14,
         "mom60": mom60, "div120": div120, "dxy60": dxy60}
ALL = list(FEATS)
X = np.column_stack([FEATS[k] for k in ALL])
okbase = ~np.isnan(X).any(axis=1) & ~np.isnan(fwd)

def auc(y, p):
    y = np.asarray(y).astype(int); p = np.asarray(p)
    if y.sum() == 0 or (1-y).sum() == 0: return float("nan")
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p)+1)
    return (r[y == 1].sum()-y.sum()*(y.sum()+1)/2)/(y.sum()*(len(y)-y.sum()))

def sig(z): return 1/(1+np.exp(-np.clip(z, -30, 30)))
def fit_lr(Xa, y, l2=1.0, iters=600, lr=0.5, w=None):
    m, d = Xa.shape; Xb = np.hstack([np.ones((m, 1)), Xa])
    th = np.zeros(d+1); w = np.ones(m) if w is None else w; w = w/w.sum()*m
    for _ in range(iters):
        p = sig(Xb@th); g = Xb.T@(w*(p-y))/m; g[1:] += l2*th[1:]/m; th -= lr*g
    return th
def pred(th, Xa): return sig(np.hstack([np.ones((len(Xa), 1)), Xa])@th)

def run(label_fn, cols, l2=3.0, tag=""):
    lab = np.where(np.isnan(fwd), np.nan, label_fn(fwd).astype(float))
    ok = okbase & ~np.isnan(lab)
    idx = np.where(ok)[0]
    folds = 5; step = len(idx)//(folds+1)
    res = []
    for f in range(folds):
        tr = idx[:step*(f+1)-60]; te = idx[step*(f+1)+60:step*(f+2)]
        if len(tr) < 600 or len(te) < 80: continue
        mu, sd = X[tr][:, cols].mean(0), X[tr][:, cols].std(0)+1e-9
        th = fit_lr((X[tr][:, cols]-mu)/sd, lab[tr], l2=l2, w=np.full(len(tr), 1/H))
        p = pred(th, (X[te][:, cols]-mu)/sd)
        res.append((auc(lab[te], p), len(te), lab[te].mean()))
    a = [r[0] for r in res]
    return (np.mean(a) if a else float("nan")), a

print("标签定义 A: 未来60日涨幅 >= 1%（跑赢人民币定存）")
for nm, cols, l2 in [
    ("规则分(4信号)", None, None),
    ("单特征 -dd", [0], None),
    ("单特征 -vol20", [1], None),
    ("LR 3特征 dd/vol/rsi", [0, 1, 3], 3.0),
    ("LR 3特征 dd/vol/div", [0, 1, 5], 3.0),
    ("LR 6特征 全部", list(range(6)), 3.0),
]:
    pass

def rule_score(rows):
    s = np.zeros(len(rows))
    s += (dd[rows] <= -8.5).astype(float)
    s += (vol20[rows] < 1.0).astype(float)
    s += (r14[rows] < 25).astype(float)
    s += (v[rows] > ma250[rows]).astype(float)
    return s

def eval_rule(lab):
    ok = okbase & ~np.isnan(lab); idx = np.where(ok)[0]
    folds = 5; step = len(idx)//(folds+1); a = []
    for f in range(folds):
        te = idx[step*(f+1)+60:step*(f+2)]
        if len(te) < 80: continue
        a.append(auc(lab[te], rule_score(te)))
    return (np.mean(a) if a else float("nan")), a

def eval_single(lab, arr, invert=False):
    ok = okbase & ~np.isnan(lab); idx = np.where(ok)[0]
    folds = 5; step = len(idx)//(folds+1); a = []
    for f in range(folds):
        te = idx[step*(f+1)+60:step*(f+2)]
        if len(te) < 80: continue
        s = -arr[te] if invert else arr[te]
        a.append(auc(lab[te], s))
    return (np.mean(a) if a else float("nan")), a

for name, fn in [("A: fwd>=1%", lambda f: f >= 1.0), ("B: fwd>0", lambda f: f > 0)]:
    lab = np.where(np.isnan(fwd), np.nan, fn(fwd).astype(float))
    print("")
    print("=== %s  基率 %.1f%% ===" % (name, np.nanmean(lab)*100))
    m, a = eval_rule(lab); print("  规则分(4信号)          %.3f  %s" % (m, ["%.2f" % x for x in a]))
    m, a = eval_single(lab, dd, invert=True); print("  单特征 回撤(取反)      %.3f  %s" % (m, ["%.2f" % x for x in a]))
    m, a = eval_single(lab, vol20, invert=True); print("  单特征 波动率(取反)    %.3f  %s" % (m, ["%.2f" % x for x in a]))
    for nm, cols, l2 in [("LR 3 dd/vol/rsi", [0, 1, 3], 3.0),
                         ("LR 3 dd/vol/div", [0, 1, 5], 3.0),
                         ("LR 6 全部", list(range(6)), 3.0)]:
        m, a = run(fn, cols, l2); print("  %-20s %.3f  %s" % (nm, m, ["%.2f" % x for x in a]))