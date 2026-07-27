#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""特征扩充验证 - 回答: 是不是变量给少了"""
import json, os, sys, warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression, LassoCV, Lasso, LinearRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etf_model_run import (
    SECTOR_ETF_MAP, HS300_CODE, ETF_HISTORY_PATH, NEWSPAPERS_PATH,
    load_json, get_trading_days, find_record, get_index, compute_volume_ratio,
    analyze_newspaper_sentiment,
)
warnings.filterwarnings('ignore')

FEAT_OLD = ['sentiment_score','bullish_count','bearish_count','prev_change_pct',
            'prev_volume_ratio','prev_intraday_return','sector_mentioned','sector_mention_count']
FEAT_NEW = ['mom_5d','mom_10d','mom_20d','vol_10d','sharpe_mom10','vol_ratio_5d',
            'overnight_gap','range_pct','hs300_mom_5d','hs300_mom_10d','relative_strength']
FEAT_ALL = FEAT_OLD + FEAT_NEW


def past_return(etf_data, code, idx, window):
    if idx < window: return None
    base = etf_data[code]['data'][idx-window]['close']; cur = etf_data[code]['data'][idx]['close']
    return (cur-base)/base if base else None

def past_vol(etf_data, code, idx, window=10):
    if idx < window: return None
    rets=[]
    for j in range(idx-window+1, idx+1):
        a=etf_data[code]['data'][j-1]['close']; b=etf_data[code]['data'][j]['close']
        if a: rets.append((b-a)/a)
    return float(np.std(rets)) if rets else None

def build_panel(etf_data, news_data):
    td = get_trading_days(etf_data); rows=[]
    for i in range(2, len(td)):
        T, Tm1, Tm2 = td[i], td[i-1], td[i-2]
        news_T = news_data.get(T, {}); sent = analyze_newspaper_sentiment(news_T)
        mention={}
        for code,info in SECTOR_ETF_MAP.items():
            cnt=0
            for paper,titles in news_T.items():
                for t in titles:
                    if any(kw in t for kw in info['keywords']): cnt+=1; break
            mention[code]=cnt
        hs_idx = get_index(etf_data, HS300_CODE, Tm1)
        hs_mom5 = past_return(etf_data, HS300_CODE, hs_idx, 5) if hs_idx>=5 else None
        hs_mom10 = past_return(etf_data, HS300_CODE, hs_idx, 10) if hs_idx>=10 else None
        for code, info in SECTOR_ETF_MAP.items():
            rT=find_record(etf_data,code,T); r1=find_record(etf_data,code,Tm1); r2=find_record(etf_data,code,Tm2)
            if not(rT and r1 and r2): continue
            if not(rT['open'] and r1['open'] and r2['close']): continue
            idx1 = get_index(etf_data, code, Tm1)
            today_return=(rT['close']-rT['open'])/rT['open']*100
            c2c_return=(rT['close']-r1['close'])/r1['close']*100
            prev_change_pct=(r1['close']-r2['close'])/r2['close']*100
            prev_vol_ratio=compute_volume_ratio(etf_data,code,Tm1)
            prev_intraday=(r1['close']-r1['open'])/r1['open']*100
            m5=past_return(etf_data,code,idx1,5); m10=past_return(etf_data,code,idx1,10)
            m20=past_return(etf_data,code,idx1,20); v10=past_vol(etf_data,code,idx1,10)
            sharpe=(m10/v10) if (m10 is not None and v10 and v10>0) else None
            on_gap=(r1['open']-r2['close'])/r2['close']*100 if r2['close'] else None
            rng=(r1['high']-r1['low'])/r1['open']*100 if r1['open'] else None
            rs=(m10-hs_mom10) if (m10 is not None and hs_mom10 is not None) else None
            rows.append({
                'date':T,'etf_code':code,'sentiment_score':float(sent['score']),
                'bullish_count':int(sent['bullish_count']),'bearish_count':int(sent['bearish_count']),
                'prev_change_pct':round(prev_change_pct,4),'prev_volume_ratio':float(prev_vol_ratio),
                'prev_intraday_return':round(prev_intraday,4),'sector_mentioned':1 if mention[code]>0 else 0,
                'sector_mention_count':int(mention[code]),
                'mom_5d':round(m5*100,4) if m5 is not None else None,
                'mom_10d':round(m10*100,4) if m10 is not None else None,
                'mom_20d':round(m20*100,4) if m20 is not None else None,
                'vol_10d':round(v10*100,4) if v10 is not None else None,
                'sharpe_mom10':round(sharpe,4) if sharpe is not None else None,
                'vol_ratio_5d':float(prev_vol_ratio),
                'overnight_gap':round(on_gap,4) if on_gap is not None else None,
                'range_pct':round(rng,4) if rng is not None else None,
                'hs300_mom_5d':round(hs_mom5*100,4) if hs_mom5 is not None else None,
                'hs300_mom_10d':round(hs_mom10*100,4) if hs_mom10 is not None else None,
                'relative_strength':round(rs*100,4) if rs is not None else None,
                'today_return':round(today_return,4),'today_direction':1 if today_return>0 else 0,
                'c2c_return':round(c2c_return,4),'c2c_direction':1 if c2c_return>0 else 0,
            })
    return pd.DataFrame(rows).dropna()


def add_const(X):
    X=np.asarray(X,dtype=float)
    if X.ndim==1: X=X.reshape(-1,1)
    return np.column_stack([np.ones(X.shape[0]),X])

def ts_cv_clf(df, feats, target, k=5):
    dates=sorted(df['date'].unique()); n=len(dates); fs=max(1,n//k); cv=[]
    for f in range(1,k):
        tr=df['date'].isin(dates[:f*fs]); te=df['date'].isin(dates[f*fs:(f+1)*fs] if f<k-1 else dates[f*fs:])
        if tr.sum()==0 or te.sum()==0: continue
        m=LogisticRegression(max_iter=2000).fit(df.loc[tr,feats].values,df.loc[tr,target].values)
        cv.append(float((m.predict(df.loc[te,feats].values)==df.loc[te,target].values).mean()))
    return float(np.mean(cv)) if cv else 0

def ts_cv_reg(df, feats, target, k=5):
    dates=sorted(df['date'].unique()); n=len(dates); fs=max(1,n//k); cv=[]
    for f in range(1,k):
        tr=df['date'].isin(dates[:f*fs]); te=df['date'].isin(dates[f*fs:(f+1)*fs] if f<k-1 else dates[f*fs:])
        if tr.sum()==0 or te.sum()==0: continue
        m=LinearRegression().fit(df.loc[tr,feats].values,df.loc[tr,target].values)
        p=m.predict(df.loc[te,feats].values); yt=df.loc[te,target].values
        s_r=float(((yt-p)**2).sum()); s_t=float(((yt-yt.mean())**2).sum())
        cv.append(1-s_r/s_t if s_t>0 else 0)
    return float(np.mean(cv)) if cv else 0

def main():
    etf_data=load_json(ETF_HISTORY_PATH); news_data=load_json(NEWSPAPERS_PATH)
    df=build_panel(etf_data, news_data)
    print('='*100)
    print(f'特征扩充验证 | 面板观测 {len(df)} | ETF {df.etf_code.nunique()} | 日期 {df.date.nunique()}')
    print(f'特征: 原{len(FEAT_OLD)}个 + 新增{len(FEAT_NEW)}个 = 共{len(FEAT_ALL)}个')
    print('='*100)

    for target,tname in [('today_direction','日内涨跌'),('c2c_direction','隔夜持有涨跌')]:
        print(f'\n{"="*70}\n【Logit】目标: {tname}\n{"="*70}')
        print(f'{"特征组":<20}{"准确率":>10}{"伪R²":>9}{"时序CV":>9}{"显著p<0.05":>12}')
        print('-'*60)
        for fname,feats in [('原8变量',FEAT_OLD),('仅新增11变量',FEAT_NEW),('全部19变量',FEAT_ALL)]:
            X=df[feats].values.astype(float); y=df[target].values.astype(int); Xc=add_const(X)
            try:
                res=sm.Logit(y,Xc).fit(disp=False,maxiter=500,method='bfgs')
                pred=(res.predict(Xc)>0.5).astype(int); acc=float((pred==y).mean()); pr2=float(res.prsquared)
                pv=[res.pvalues[i] for i in range(1,len(feats)+1)]
            except Exception:
                m=LogisticRegression(max_iter=2000).fit(X,y); pred=m.predict(X)
                acc=float((pred==y).mean()); pr2=0.0; pv=[1]*len(feats)
            cv=ts_cv_clf(df,feats,target); sig=sum(1 for p in pv if p<0.05)
            print(f'{fname:<18}{acc:>10.4f}{pr2:>9.4f}{cv:>9.4f}{sig:>12}')

    for target,tname in [('today_return','日内收益%'),('c2c_return','隔夜持有收益%')]:
        print(f'\n{"="*70}\n【OLS】目标: {tname}\n{"="*70}')
        print(f'{"特征组":<20}{"R²":>9}{"调整R²":>9}{"时序CV R²":>11}{"显著":>6}{"RMSE":>9}')
        print('-'*64)
        for fname,feats in [('原8变量',FEAT_OLD),('仅新增11变量',FEAT_NEW),('全部19变量',FEAT_ALL)]:
            X=df[feats].values.astype(float); y=df[target].values.astype(float); Xc=add_const(X)
            res=sm.OLS(y,Xc).fit(); pred=res.predict(Xc)
            rmse=float(np.sqrt(((y-pred)**2).mean())); pv=[res.pvalues[i] for i in range(1,len(feats)+1)]
            sig=sum(1 for p in pv if p<0.05); cv=ts_cv_reg(df,feats,target)
            print(f'{fname:<18}{float(res.rsquared):>9.4f}{float(res.rsquared_adj):>9.4f}{cv:>11.4f}{sig:>6}{rmse:>9.4f}')

    # 新变量显著性 (全模型, 隔夜目标)
    print(f'\n{"="*70}\n【新增变量显著性排序】(全19变量Logit, 目标=c2c_direction)\n{"="*70}')
    X=df[FEAT_ALL].values.astype(float); y=df['c2c_direction'].values.astype(int); Xc=add_const(X)
    res=sm.Logit(y,Xc).fit(disp=False,maxiter=500,method='bfgs')
    newc=[(FEAT_ALL[i],round(float(res.params[i+1]),5),round(float(res.pvalues[i+1]),4)) for i in range(len(FEAT_ALL))]
    newc.sort(key=lambda x:x[2])
    print(f'{"特征":<22}{"系数":>11}{"p值":>8}{"显著?":>8}')
    print('-'*49)
    for f,c,p in newc:
        s='***' if p<0.01 else ('**' if p<0.05 else ('*' if p<0.1 else ''))
        print(f'{f:<20}{c:>11.5f}{p:>8.4f}{s:>8}')

    # Lasso
    print(f'\n{"="*70}\n【Lasso变量选择】(全19变量, c2c_return, 标准化)\n{"="*70}')
    Xs=StandardScaler().fit_transform(X); ys=(df['c2c_return'].values-df['c2c_return'].mean())/df['c2c_return'].std()
    lcv=LassoCV(cv=5,max_iter=50000,n_alphas=200).fit(Xs,ys)
    la=Lasso(alpha=max(lcv.alpha_*3,1e-4),max_iter=50000).fit(Xs,ys)
    sel=sorted([(FEAT_ALL[i],round(float(la.coef_[i]),5)) for i in range(len(FEAT_ALL))],key=lambda x:-abs(x[1]))
    for f,c in sel:
        print(f'  {f:<20}{c:>10.5f}  {"<-入选" if abs(c)>1e-6 else "(剔除)"}')

if __name__=='__main__':
    main()
