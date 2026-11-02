# -*- coding: utf-8 -*-
import json, math, os
import numpy as np
D = os.path.dirname(os.path.abspath(__file__))
px=[(r[0],float(r[1])) for r in json.load(open(os.path.join(D,"usdcny.json")))]
dates=[d for d,_ in px]; v=np.array([x for _,x in px]); n=len(v)
def rmax(x,k): return np.array([x[max(0,i-k+1):i+1].max() for i in range(len(x))])
def rmean(x,k):
    o=np.full(len(x),np.nan); c=np.cumsum(np.insert(x,0,0)); o[k-1:]=(c[k:]-c[:-k])/k; return o
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
dd=(v/rmax(v,500)-1)*100; vol20=avol(v,20); ma250=rmean(v,250); r14=rsi(v)
H=60
fwd=np.full(n,np.nan); fwd[:n-H]=(v[H:]/v[:n-H]-1)*100
ok=~np.isnan(fwd)&~np.isnan(dd)&~np.isnan(vol20)&~np.isnan(r14)&~np.isnan(ma250)
score=(dd<=-8.5).astype(int)+(vol20<1.0).astype(int)+(r14<25).astype(int)+(v>ma250).astype(int)
print("=== 经验频率表（2010-2026，共 %d 个交易日）===" % ok.sum())
print("%-6s %8s %14s %14s %12s" % ("分数","样本","P(60日涨>0)","P(60日涨≥1%)","平均涨幅"))
for s in range(5):
    m=ok&(score==s)
    if m.sum()<10: 
        print("%-6d %8d  (样本不足)"%(s,m.sum())); continue
    print("%-6d %8d %13.1f%% %13.1f%% %11.2f%%" % (s, m.sum(),
        (fwd[m]>0).mean()*100, (fwd[m]>=1).mean()*100, fwd[m].mean()))
print("")
print("=== 按跌幅分档 ===")
for lo,hi in [(-6,0),(-8,-6),(-10,-8),(-100,-10)]:
    m=ok&(dd>=lo)&(dd<hi) if lo>-100 else ok&(dd<-10)
    if m.sum()<10: continue
    print("回撤 %5.1f~%5.1f%%: n=%4d  P(>0)=%.0f%%  P(≥1%%)=%.0f%%  均值 %+.2f%%" % (
        lo if lo>-100 else -99, hi, m.sum(), (fwd[m]>0).mean()*100, (fwd[m]>=1).mean()*100, fwd[m].mean()))