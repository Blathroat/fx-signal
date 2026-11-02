# -*- coding: utf-8 -*-
import json, math, os
import numpy as np
D = os.path.dirname(os.path.abspath(__file__))
px = [(r[0], float(r[1])) for r in json.load(open(os.path.join(D, "usdcny.json")))]
dx = dict(json.load(open(os.path.join(D, "dxy.json"))))
dates = [d for d, _ in px]; v = np.array([x for _, x in px]); n = len(v)
dv = np.array([dx.get(d, np.nan) for d in dates])

def roll_max(x,k): return np.array([x[max(0,i-k+1):i+1].max() for i in range(len(x))])
def roll_mean(x,k):
    o=np.full(len(x),np.nan); c=np.cumsum(np.insert(x,0,0)); o[k-1:]=(c[k:]-c[:-k])/k; return o
def pct(x,k):
    o=np.full(len(x),np.nan); o[k:]=(x[k:]/x[:-k]-1)*100; return o
def rsi(x,k=14):
    o=np.full(len(x),np.nan); g=l=0.0
    for i in range(1,k+1):
        d=x[i]-x[i-1]; g+=max(d,0); l+=max(-d,0)
    ag,al=g/k,l/k; o[k]=100-100/(1+ag/al) if al>0 else 100
    for i in range(k+1,len(x)):
        d=x[i]-x[i-1]; ag=(ag*(k-1)+max(d,0))/k; al=(al*(k-1)+max(-d,0))/k
        o[i]=100-100/(1+ag/al) if al>0 else 100
    return o
def avol(x,k):
    r=np.diff(np.log(x)); o=np.full(len(x),np.nan)
    for i in range(k,len(x)):
        w=r[i-k:i]; o[i]=w.std(ddof=1)*math.sqrt(231)*100
    return o

dd=(v/roll_max(v,500)-1)*100; vol20=avol(v,20); ma250=roll_mean(v,250); r14=rsi(v)
mom60=pct(v,60); mom120=pct(v,120); dxy60=pct(dv,60); div120=mom120-dxy60
X=np.column_stack([dd,vol20,r14,div120])
okbase=~np.isnan(X).any(axis=1)

def auc(y,p):
    y=np.asarray(y).astype(int); p=np.asarray(p)
    if y.sum()==0 or (1-y).sum()==0: return float("nan")
    o=np.argsort(p); r=np.empty(len(p)); r[o]=np.arange(1,len(p)+1)
    return (r[y==1].sum()-y.sum()*(y.sum()+1)/2)/(y.sum()*(len(y)-y.sum()))
def sig(z): return 1/(1+np.exp(-np.clip(z,-30,30)))
def fit_lr(Xa,y,l2,iters=600,lr=0.5,w=None):
    m,d=Xa.shape; Xb=np.hstack([np.ones((m,1)),Xa]); th=np.zeros(d+1)
    w=np.ones(m) if w is None else w; w=w/w.sum()*m
    for _ in range(iters):
        p=sig(Xb@th); g=Xb.T@(w*(p-y))/m; g[1:]+=l2*th[1:]/m; th-=lr*g
    return th
def pred(th,Xa): return sig(np.hstack([np.ones((len(Xa),1)),Xa])@th)
def rule(rows):
    return (dd[rows]<=-8.5).astype(float)+(vol20[rows]<1.0).astype(float)+(r14[rows]<25).astype(float)+(v[rows]>ma250[rows]).astype(float)

print("%-6s %8s %8s %8s %-26s" % ("H(天)","基率","规则AUC","模型AUC","逐折模型"))
for H in (20,60,120,250):
    fwd=np.full(n,np.nan); fwd[:n-H]=(v[H:]/v[:n-H]-1)*100
    lab=np.where(np.isnan(fwd),np.nan,(fwd>0).astype(float))
    ok=okbase&~np.isnan(lab); idx=np.where(ok)[0]
    folds=5; step=len(idx)//(folds+1)
    ra=[]; ma=[]
    for f in range(folds):
        tr=idx[:step*(f+1)-H]; te=idx[step*(f+1)+H:step*(f+2)]
        if len(tr)<600 or len(te)<80: continue
        ra.append(auc(lab[te],rule(te)))
        mu,sd=X[tr].mean(0),X[tr].std(0)+1e-9
        th=fit_lr((X[tr]-mu)/sd,lab[tr],3.0,w=np.full(len(tr),1/H))
        ma.append(auc(lab[te],pred(th,(X[te]-mu)/sd)))
    print("%-6d %7.1f%% %8.3f %8.3f  %s" % (H, np.nanmean(lab)*100, np.mean(ra), np.mean(ma),
        " ".join("%.2f"%x for x in ma)))