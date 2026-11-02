# -*- coding: utf-8 -*-
"""USD/CNY 底部概率模型：3 状态 HMM + 状态内逻辑回归
训练：本地 conda；推理：纯 Python（导出 model.json）
"""
import json, math, os, sys
import numpy as np

D = os.path.dirname(os.path.abspath(__file__))
px = [(r[0], float(r[1])) for r in json.load(open(os.path.join(D, "usdcny.json")))]
dx = dict(json.load(open(os.path.join(D, "dxy.json"))))
dates = [d for d, _ in px]; v = np.array([x for _, x in px]); n = len(v)
dv = np.array([dx.get(d, np.nan) for d in dates])

# ---------------- 特征 ----------------
def roll_max(x, k):
    return np.array([x[max(0, i-k+1):i+1].max() for i in range(len(x))])
def roll_mean(x, k):
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.insert(x, 0, 0))
    out[k-1:] = (c[k:] - c[:-k]) / k
    return out
def pct_chg(x, k):
    out = np.full(len(x), np.nan)
    out[k:] = (x[k:] / x[:-k] - 1) * 100
    return out
def rsi(x, k=14):
    out = np.full(len(x), np.nan); g = l = 0.0
    for i in range(1, k+1):
        d = x[i]-x[i-1]; g += max(d, 0); l += max(-d, 0)
    ag, al = g/k, l/k
    out[k] = 100-100/(1+ag/al) if al > 0 else 100
    for i in range(k+1, len(x)):
        d = x[i]-x[i-1]
        ag = (ag*(k-1)+max(d, 0))/k; al = (al*(k-1)+max(-d, 0))/k
        out[i] = 100-100/(1+ag/al) if al > 0 else 100
    return out
def ann_vol(x, k):
    r = np.diff(np.log(x)); out = np.full(len(x), np.nan)
    for i in range(k, len(x)):
        w = r[i-k:i]; out[i] = w.std(ddof=1)*math.sqrt(231)*100
    return out

dd = (v/roll_max(v, 500)-1)*100
vol20 = ann_vol(v, 20); vol60 = ann_vol(v, 60)
volratio = vol20/vol60
ma250 = roll_mean(v, 250); ma120 = roll_mean(v, 120)
dist250 = (v/ma250-1)*100; dist120 = (v/ma120-1)*100
r14 = rsi(v)
mom20 = pct_chg(v, 20); mom60 = pct_chg(v, 60); mom120 = pct_chg(v, 120)
dxy_mom60 = pct_chg(dv, 60)
div120 = mom120 - dxy_mom60
ret1 = np.full(n, np.nan); ret1[1:] = (np.log(v[1:]/v[:-1]))*100

FE = {
 "dd": dd, "vol20": vol20, "volratio": volratio,
 "dist250": dist250, "dist120": dist120, "rsi": r14,
 "mom20": mom20, "mom60": mom60, "mom120": mom120,
 "dxy60": dxy_mom60, "div120": div120, "ret1": ret1,
}
FN = ["dd", "vol20", "volratio", "dist250", "rsi", "mom60", "div120"]

# ---------------- 标签 ----------------
H = 60
fwd = np.full(n, np.nan); fwd[:n-H] = (v[H:]/v[:n-H]-1)*100
lab = np.where(np.isnan(fwd), np.nan, (fwd >= 1.0).astype(float))

X = np.column_stack([FE[k] for k in FN])
ok = ~np.isnan(X).any(axis=1) & ~np.isnan(lab)
idx = np.where(ok)[0]
print("样本 %d  (%s ~ %s)  正例率 %.1f%%" % (len(idx), dates[idx[0]], dates[idx[-1]], lab[idx].mean()*100))

# ---------------- 3 状态对角高斯 HMM ----------------
def gauss_logpdf(X, mu, var):
    return -0.5*(np.log(2*np.pi*var) + (X-mu)**2/var).sum(axis=1)

def hmm_fit(X, K=3, iters=80, seed=0):
    rng = np.random.default_rng(seed)
    m, d = X.shape
    # 初始化：按第一主特征（vol）分位
    q = np.quantile(X[:, 1], [0.33, 0.66])
    lab0 = np.digitize(X[:, 1], q)
    mu = np.array([X[lab0 == k].mean(axis=0) if (lab0 == k).sum() > 10 else X.mean(axis=0)+rng.normal(0, .1, d) for k in range(K)])
    var = np.array([X[lab0 == k].var(axis=0)+1e-3 if (lab0 == k).sum() > 10 else X.var(axis=0)+1e-3 for k in range(K)])
    pi = np.ones(K)/K
    A = np.full((K, K), 1.0/K) + np.eye(K)*0.6
    A /= A.sum(axis=1, keepdims=True)
    for _ in range(iters):
        B = np.column_stack([np.exp(gauss_logpdf(X, mu[k], var[k]))+1e-300 for k in range(K)])
        alpha = np.zeros((m, K)); beta = np.zeros((m, K)); c = np.zeros(m)
        alpha[0] = pi*B[0]; c[0] = alpha[0].sum(); alpha[0] /= c[0]
        for t in range(1, m):
            alpha[t] = (alpha[t-1] @ A)*B[t]
            c[t] = alpha[t].sum(); alpha[t] /= c[t]
        beta[-1] = 1.0
        for t in range(m-2, -1, -1):
            beta[t] = (A @ (B[t+1]*beta[t+1]))/c[t+1]
        gamma = alpha*beta; gamma /= gamma.sum(axis=1, keepdims=True)
        xi = np.zeros((K, K))
        for t in range(m-1):
            num = alpha[t][:, None]*A*(B[t+1]*beta[t+1])[None, :]
            xi += num/num.sum()
        pi = gamma[0]/gamma[0].sum()
        A = xi/xi.sum(axis=1, keepdims=True)
        for k in range(K):
            w = gamma[:, k]
            mu[k] = (w[:, None]*X).sum(0)/w.sum()
            var[k] = (w[:, None]*(X-mu[k])**2).sum(0)/w.sum()+1e-4
    return {"pi": pi, "A": A, "mu": mu, "var": var}

def hmm_post(X, p):
    """前向滤波 + 后向，返回 gamma（后验）"""
    K = len(p["pi"]); m = len(X)
    B = np.column_stack([np.exp(gauss_logpdf(X, p["mu"][k], p["var"][k]))+1e-300 for k in range(K)])
    alpha = np.zeros((m, K)); beta = np.zeros((m, K)); c = np.zeros(m)
    alpha[0] = p["pi"]*B[0]; c[0] = alpha[0].sum(); alpha[0] /= c[0]
    for t in range(1, m):
        alpha[t] = (alpha[t-1] @ p["A"])*B[t]
        c[t] = alpha[t].sum() or 1e-300; alpha[t] /= c[t]
    beta[-1] = 1.0
    for t in range(m-2, -1, -1):
        beta[t] = (p["A"] @ (B[t+1]*beta[t+1]))/c[t+1]
    g = alpha*beta; g /= g.sum(axis=1, keepdims=True)
    return g

# ---------------- 逻辑回归（np 手写，L2） ----------------
def fit_lr(X, y, w=None, l2=1.0, iters=400, lr=0.5):
    m, d = X.shape
    Xb = np.hstack([np.ones((m, 1)), X])
    th = np.zeros(d+1)
    w = np.ones(m) if w is None else w
    w = w/w.sum()*m
    for _ in range(iters):
        z = Xb @ th
        p = 1/(1+np.exp(-np.clip(z, -30, 30)))
        g = Xb.T @ (w*(p-y))/m
        g[1:] += l2*th[1:]/m
        th -= lr*g
    return th

def sig(z): return 1/(1+np.exp(-np.clip(z, -30, 30)))
def pred_lr(th, X):
    return sig(np.hstack([np.ones((len(X), 1)), X]) @ th)

# ---------------- walk-forward ----------------
ZS = ["ret1", "vol20", "mom60"]
HMMX = np.column_stack([FE[k] for k in ZS])
hmm_ok = ~np.isnan(HMMX).any(axis=1)
mu_, sd_ = HMMX[hmm_ok].mean(0), HMMX[hmm_ok].std(0)
HMMXz = (HMMX-mu_)/sd_

def fit_all(tr):
    hmm = hmm_fit(HMMXz[tr], 3)
    g = hmm_post(HMMXz, hmm)
    st = g.argmax(1)
    scaler = (X[tr].mean(0), X[tr].std(0)+1e-9)
    Xz = (X-scaler[0])/scaler[1]
    models = []
    for k in range(3):
        m = tr[st[tr] == k]
        if len(m) < 150 or lab[m].sum() < 20:
            models.append(None); continue
        models.append(fit_lr(Xz[m], lab[m], w=np.full(len(m), 1/H), l2=3.0))
    return {"hmm": hmm, "scaler": scaler, "models": models, "st": st}

def predict(pack, rows):
    g = hmm_post(HMMXz, pack["hmm"])[rows]
    Xz = (X[rows]-pack["scaler"][0])/pack["scaler"][1]
    ps = []
    for k in range(3):
        if pack["models"][k] is None:
            ps.append(np.full(len(rows), lab.mean()))
        else:
            ps.append(pred_lr(pack["models"][k], Xz))
    return (g*np.column_stack(ps)).sum(1)

folds = 5
step = len(idx)//(folds+1)
AUC, BR, FOLD = [], [], []
def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    if y.sum() == 0 or (1-y).sum() == 0: return float("nan")
    order = np.argsort(p); ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p)+1)
    return (ranks[y == 1].sum() - y.sum()*(y.sum()+1)/2)/(y.sum()*(len(y)-y.sum()))

print("")
print("%-6s %-12s %-12s %5s %6s %6s" % ("fold","train_end","test","n","AUC","base"))
for f in range(folds):
    tr_end = idx[step*(f+1)]
    te = idx[step*(f+1)+60 : step*(f+2)]
    tr = idx[:step*(f+1)-60]
    if len(tr) < 600 or len(te) < 80: continue
    pack = fit_all(tr)
    p = predict(pack, te)
    a = auc(lab[te], p)
    AUC.append(a); FOLD.append((f, a, len(te)))
    print("%-6d %-12s %-12s %5d %6.3f %6.2f" % (f, dates[tr[-1]], dates[te[-1]], len(te), a, lab[te].mean()))

print("")
if AUC:
    print("平均 AUC %.3f  (%d 折)" % (np.mean(AUC), len(AUC)))