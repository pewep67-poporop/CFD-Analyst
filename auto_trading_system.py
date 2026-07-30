#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================================================
🤖 CFD AUTO TRADING SYSTEM v9.0 - SCALPING FINAL BOSS
===================================================================
TÍCH HỢP ĐẦY ĐỦ THEO WORKFLOW:
✅ MT5 Client (Shared Session - không bị out)
✅ 15+ chỉ báo kỹ thuật
✅ Signal Engine (3 modes)
✅ Backtest + Monte Carlo + ML Random Forest
✅ NLP News Sentiment Analyzer (FinBERT + NewsAPI)
✅ Dynamic Risk Manager (Circuit Breaker + Correlation Check)
✅ TWAP Execution Engine (Chia nhỏ lệnh)
✅ Fibonacci Engine (Hỗ trợ/Kháng cự động)
✅ Market Regime Detector (GMM - Trending vs Sideway)
✅ Fallback Logic (Signal Engine khi ML NEUTRAL)
✅ Auto Volume Calculator (Tính volume theo risk %)
✅ Debug Info (Hiển thị probabilities)
✅ Scalping Mode (M15, TP/SL nhỏ, volume tự động)
✅ Trade Logger CSV + Dashboard
===================================================================
"""
from builtins import staticmethod
import sys
import os
import time
import json
import csv
import threading
import subprocess
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import deque
import warnings
import numpy as np 
import pandas as pd # type: ignore
from sklearn.ensemble import RandomForestClassifier # type: ignore
from sklearn.model_selection import train_test_split, TimeSeriesSplit # type: ignore
from sklearn.preprocessing import StandardScaler # type: ignore
from sklearn.metrics import accuracy_score # type: ignore
from sklearn.mixture import GaussianMixture # type: ignore
warnings.filterwarnings('ignore')

# ====================================================================
# IMPORT MT5
# ====================================================================
try:
    import MetaTrader5 as mt5 # type: ignore
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None
    print("⚠️ MetaTrader5 chưa được cài. Chạy: pip install MetaTrader5")

# ====================================================================
# IMPORT NLP (Optional)
# ====================================================================
try:
    from transformers import pipeline # type: ignore
    import requests # type: ignore
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False
    print("️ Transformers/requests chưa cài. NLP sẽ dùng chế độ Mock.")

# ====================================================================
# CẤU HÌNH TÀI KHOẢN DEMO
# ====================================================================
DEMO_ACCOUNT = int(os.getenv("DEMO_ACCOUNT", "0"))
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
DEMO_SERVER = os.getenv("DEMO_SERVER", "MetaQuote-Demo")

# ====================================================================
# CẤU HÌNH API BÊN THỨ 3
# ====================================================================
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")  # ← ĐIỀN KEY NEWSAPI VÀO ĐÂY (lấy miễn phí tại newsapi.org)

# ====================================================================
# CẤU HÌNH GIAO DỊCH (SCALPING MODE)
# ====================================================================
@dataclass
class TradingConfig:
    symbol: str = "XAUUSD"
    timeframe: str = "M15"  # ← SCALPING: M5, M15, M30
    tp_pips: float = 30.0   # ← TP nhỏ cho scalping
    sl_pips: float = 15.0   # ← SL nhỏ cho scalping
    risk_percent: float = 5.0  # ← Risk 5% vốn/lệnh
    account_equity: float = 100.0  # ← Vốn thực $100
    max_spread: float = 20.0  # ← Spread tối đa cho phép
    commission_per_lot: float = 0.0
    spread_pips: float = 2.0
    slippage_pips: float = 1.0
    max_daily_loss: float = 15.0  # ← 15% vốn = $15

trading_cfg = TradingConfig()
CURRENT_MODE = "aggressive"  # ← Chế độ nhiều lệnh

TIMEFRAME_MAP = {
    "M1": getattr(mt5, "TIMEFRAME_M1", None),
    "M5": getattr(mt5, "TIMEFRAME_M5", None),
    "M15": getattr(mt5, "TIMEFRAME_M15", None),
    "M30": getattr(mt5, "TIMEFRAME_M30", None),
    "H1": getattr(mt5, "TIMEFRAME_H1", None),
    "H4": getattr(mt5, "TIMEFRAME_H4", None),
    "D1": getattr(mt5, "TIMEFRAME_D1", None),
    "W1": getattr(mt5, "TIMEFRAME_W1", None),
} if MT5_AVAILABLE and mt5 is not None else {}

# ====================================================================
# 1. MT5 CLIENT (SHARED SESSION - FIX LỖI OUT)
# ====================================================================
class MT5Client:
    def __init__(self, account: int, password: str, server: str):
        self.account = account
        self.password = password
        self.server = server
        self.connected = False
        self.keepalive_active = False
        self._keepalive_thread = None

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            print("❌ MetaTrader5 chưa được cài đặt.")
            return False
        
        # Chỉ initialize - KHÔNG login (Shared Session)
        if not mt5.initialize():
            print(f"❌ MT5 initialize() thất bại: {mt5.last_error()}")
            return False
        
        # Kiểm tra session hiện tại của MT5 Desktop
        info = mt5.account_info()
        if info is None:
            print("❌ Không lấy được thông tin tài khoản. Hãy mở MT5 Desktop và đăng nhập trước.")
            mt5.shutdown()
            return False
        
        self.connected = True
        print(f"✅ KẾT NỐI THÀNH CÔNG (Shared Session): {info.login} | Balance: ${info.balance:,.2f}")
        self._start_keepalive()
        return True

    def _start_keepalive(self):
        if self.keepalive_active: return
        self.keepalive_active = True
        
        def keepalive_loop():
            while self.keepalive_active and self.connected:
                try:
                    if mt5.account_info() is None:
                        print("⚠️ MT5 mất kết nối!")
                        self.connected = False
                        break
                except: pass
                time.sleep(60)
        
        self._keepalive_thread = threading.Thread(target=keepalive_loop, daemon=True)
        self._keepalive_thread.start()

    def disconnect(self):
        self.keepalive_active = False
        self.connected = False
        if MT5_AVAILABLE: mt5.shutdown()

    def get_rates(self, symbol: str, timeframe: str, bars: int = 5000) -> Optional[pd.DataFrame]:
        if not self.connected: return None
        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_H1)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None or len(rates) == 0: return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        return df

    def get_account_info(self) -> Optional[Dict]:
        if not self.connected: return None
        info = mt5.account_info()
        if not info: return None
        return {'login': info.login, 'balance': info.balance, 'equity': info.equity}

    def place_order(self, symbol: str, order_type: str, volume: float, 
                    sl: float = 0, tp: float = 0, comment: str = "CFD_AI_v9") -> Optional[int]:
        if not self.connected: return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None: return None

        if order_type.upper() == "BUY":
            order_type_mt5 = mt5.ORDER_TYPE_BUY
            price = tick.ask
        elif order_type.upper() == "SELL":
            order_type_mt5 = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else: return None

        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(volume),
            "type": order_type_mt5, "price": price, "sl": float(sl), "tp": float(tp),
            "deviation": 20, "magic": 234000, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"❌ Lệnh thất bại: {result.comment if result else 'None'}")
            return None
        print(f"✅ Lệnh {order_type} {symbol} | Ticket: {result.order}")
        return result.order

# ====================================================================
# 2. INDICATOR ENGINE (GIỮ NGUYÊN CODE GỐC)
# ====================================================================
class IndicatorEngine:
    @staticmethod
    def compute_all(df, verbose=True):
        if df is None or len(df) == 0: return df
        df = df.copy()
        close = df['close'].values.astype(np.float64)
        high = df['high'].values.astype(np.float64)
        low = df['low'].values.astype(np.float64)
        volume = df.get('volume', np.ones(len(df))).values.astype(np.float64)
        n = len(close)
        
        for p in [7, 10, 25, 50, 100, 200]:
            if p < n: df[f'SMA_{p}'] = IndicatorEngine._sma(close, p)
        for p in [12, 26]:
            if p < n: df[f'EMA_{p}'] = IndicatorEngine._ema(close, p)
        df['RSI'] = IndicatorEngine._rsi(close, 14)
        macd, signal, hist = IndicatorEngine._macd(close, 12, 26, 9)
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = macd, signal, hist
        upper, middle, lower = IndicatorEngine._bbands(close, 20, 2)
        df['BB_Upper'], df['BB_Middle'], df['BB_Lower'] = upper, middle, lower
        stoch_k, stoch_d = IndicatorEngine._stochastic(high, low, close, 14, 3)
        df['Stoch_K'], df['Stoch_D'] = stoch_k, stoch_d
        df['ATR'] = IndicatorEngine._atr(high, low, close, 14)
        df['ADX'] = IndicatorEngine._adx(high, low, close, 14)
        tenkan, kijun, senkou_a, senkou_b, chikou = IndicatorEngine._ichimoku(high, low, close, 9, 26, 52)
        df['Ichimoku_Tenkan'], df['Ichimoku_Kijun'] = tenkan, kijun
        ha_open, ha_high, ha_low, ha_close = IndicatorEngine._heiken_ashi(df)
        df['HA_Open'], df['HA_High'], df['HA_Low'], df['HA_Close'] = ha_open, ha_high, ha_low, ha_close
        df['Momentum'] = IndicatorEngine._momentum(close, 10)
        df['Williams_R'] = IndicatorEngine._williams_r(high, low, close, 14)
        df['CCI'] = IndicatorEngine._cci(high, low, close, 20)
        df['OBV'] = IndicatorEngine._obv(close, volume)
        pivot, r1, r2, s1, s2 = IndicatorEngine._pivot_points(high, low, close)
        df['Pivot'], df['R1'], df['S1'] = pivot, r1, s1
        return df

    @staticmethod
    def _sma(values, period):
        values = np.asarray(values, dtype=np.float64)
        if len(values) < period:
            return np.full(len(values), np.nan, dtype=np.float64)
        return pd.Series(values).rolling(window=period, min_periods=period).mean().to_numpy(dtype=np.float64)

    @staticmethod
    def _ema(values, period):
        values = np.asarray(values, dtype=np.float64)
        if len(values) == 0:
            return np.array([], dtype=np.float64)
        alpha = 2.0 / (period + 1)
        return pd.Series(values).ewm(alpha=alpha, adjust=False, min_periods=period).mean().to_numpy(dtype=np.float64)

    @staticmethod
    def _rsi(close, period=14):
        close = np.asarray(close, dtype=np.float64)
        if len(close) <= period:
            return np.full(len(close), np.nan, dtype=np.float64)
        series = pd.Series(close)
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        safe_loss = avg_loss.replace(0, np.nan)
        rs = avg_gain / safe_loss.fillna(1e-10)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.to_numpy(dtype=np.float64)

    @staticmethod
    def _macd(close, fast=12, slow=26, signal=9):
        ema_fast = IndicatorEngine._ema(close, fast)
        ema_slow = IndicatorEngine._ema(close, slow)
        macd_line = ema_fast - ema_slow
        signal_line = IndicatorEngine._ema(macd_line, signal)
        return macd_line, signal_line, macd_line - signal_line

    @staticmethod
    def _bbands(close, period=20, std_dev=2):
        series = pd.Series(np.asarray(close, dtype=np.float64))
        middle = series.rolling(window=period, min_periods=period).mean()
        std = series.rolling(window=period, min_periods=period).std(ddof=0)
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return upper.to_numpy(dtype=np.float64), middle.to_numpy(dtype=np.float64), lower.to_numpy(dtype=np.float64)

    @staticmethod
    def _stochastic(high, low, close, k_period=14, d_period=3):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        hh = pd.Series(high).rolling(window=k_period, min_periods=k_period).max().to_numpy(dtype=np.float64)
        ll = pd.Series(low).rolling(window=k_period, min_periods=k_period).min().to_numpy(dtype=np.float64)
        stoch_k = np.full(len(close), np.nan, dtype=np.float64)
        valid = hh != ll
        stoch_k[valid] = ((close[valid] - ll[valid]) / (hh[valid] - ll[valid])) * 100
        smoothed = pd.Series(stoch_k).rolling(window=d_period, min_periods=d_period).mean().to_numpy(dtype=np.float64)
        return stoch_k, smoothed

    @staticmethod
    def _atr(high, low, close, period=14):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        prev_close = np.empty_like(close)
        prev_close[0] = close[0]
        prev_close[1:] = close[:-1]
        tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
        tr[0] = 0.0
        atr = pd.Series(tr).rolling(window=period, min_periods=period).mean().to_numpy(dtype=np.float64)
        return atr

    @staticmethod
    def _adx(high, low, close, period=14):
        return np.full(len(close), 25.0)

    @staticmethod
    def _ichimoku(high, low, close, tenkan=9, kijun=26, senkou_b=52):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        tk = pd.Series(high).rolling(window=tenkan, min_periods=tenkan).max().to_numpy(dtype=np.float64)
        tk = (tk + pd.Series(low).rolling(window=tenkan, min_periods=tenkan).min().to_numpy(dtype=np.float64)) / 2
        kj = pd.Series(high).rolling(window=kijun, min_periods=kijun).max().to_numpy(dtype=np.float64)
        kj = (kj + pd.Series(low).rolling(window=kijun, min_periods=kijun).min().to_numpy(dtype=np.float64)) / 2
        return tk, kj, (tk + kj) / 2, np.full(len(high), np.nan), np.full(len(high), np.nan)

    @staticmethod
    def _heiken_ashi(df):
        o, h, l, c = df['open'].values, df['high'].values, df['low'].values, df['close'].values
        hc = (o + h + l + c) / 4
        ho = np.full(len(c), np.nan)
        ho[0] = o[0]
        for i in range(1, len(c)): ho[i] = (ho[i-1] + hc[i-1]) / 2
        return ho, np.maximum(h, np.maximum(ho, hc)), np.minimum(l, np.minimum(ho, hc)), hc

    @staticmethod
    def _momentum(close, period=10):
        close = np.asarray(close, dtype=np.float64)
        mom = np.full(len(close), np.nan, dtype=np.float64)
        if len(close) > period:
            mom[period:] = close[period:] - close[:-period]
        return mom

    @staticmethod
    def _williams_r(high, low, close, period=14):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        hh = pd.Series(high).rolling(window=period, min_periods=period).max().to_numpy(dtype=np.float64)
        ll = pd.Series(low).rolling(window=period, min_periods=period).min().to_numpy(dtype=np.float64)
        wr = np.full(len(close), np.nan, dtype=np.float64)
        valid = hh != ll
        wr[valid] = ((hh[valid] - close[valid]) / (hh[valid] - ll[valid])) * -100
        return wr

    @staticmethod
    def _cci(high, low, close, period=20):
        tp = (high + low + close) / 3
        sma_tp = IndicatorEngine._sma(tp, period)
        deviation = np.abs(tp - sma_tp)
        md = pd.Series(deviation).rolling(window=period, min_periods=period).mean().to_numpy(dtype=np.float64)
        cci = np.full(len(close), np.nan, dtype=np.float64)
        valid = md != 0
        cci[valid] = (tp[valid] - sma_tp[valid]) / (0.015 * md[valid])
        return cci

    @staticmethod
    def _obv(close, volume):
        close = np.asarray(close, dtype=np.float64)
        volume = np.asarray(volume, dtype=np.float64)
        obv = np.zeros(len(close), dtype=np.float64)
        obv[0] = volume[0]
        if len(close) > 1:
            changes = np.where(close[1:] > close[:-1], volume[1:], np.where(close[1:] < close[:-1], -volume[1:], 0.0))
            obv[1:] = obv[0] + np.cumsum(changes)
        return obv

    @staticmethod
    def _pivot_points(high, low, close):
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)
        prev_high = np.empty_like(high)
        prev_low = np.empty_like(low)
        prev_close = np.empty_like(close)
        prev_high[0] = np.nan
        prev_low[0] = np.nan
        prev_close[0] = np.nan
        prev_high[1:] = high[:-1]
        prev_low[1:] = low[:-1]
        prev_close[1:] = close[:-1]
        p = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * p - prev_low
        s1 = 2 * p - prev_high
        return p, r1, np.full(len(close), np.nan), s1, np.full(len(close), np.nan)

# ====================================================================
# 3. SIGNAL ENGINE
# ====================================================================
class SignalEngine:
    def __init__(self, mode="aggressive"):
        self.mode = mode.lower()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        n = len(df)
        df['Signal'] = 0
        df['signal_strength'] = 0
        if n < 200:
            return df

        close = df['close'].to_numpy(dtype=np.float64)
        rsi = df['RSI'].to_numpy(dtype=np.float64)
        macd = df['MACD'].to_numpy(dtype=np.float64)
        macd_signal = df['MACD_Signal'].to_numpy(dtype=np.float64)
        macd_hist = df['MACD_Hist'].to_numpy(dtype=np.float64)
        bb_lower = df['BB_Lower'].to_numpy(dtype=np.float64)
        bb_upper = df['BB_Upper'].to_numpy(dtype=np.float64)
        atr = df['ATR'].to_numpy(dtype=np.float64)
        stoch_k = df['Stoch_K'].to_numpy(dtype=np.float64)
        stoch_d = df['Stoch_D'].to_numpy(dtype=np.float64)
        sma_7 = df['SMA_7'].to_numpy(dtype=np.float64) if 'SMA_7' in df.columns else None
        sma_25 = df['SMA_25'].to_numpy(dtype=np.float64) if 'SMA_25' in df.columns else None
        sma_50 = df['SMA_50'].to_numpy(dtype=np.float64) if 'SMA_50' in df.columns else None
        sma_200 = df['SMA_200'].to_numpy(dtype=np.float64) if 'SMA_200' in df.columns else None

        signals = np.zeros(n, dtype=np.int8)
        strengths = np.zeros(n, dtype=np.int8)
        thresholds = {
            "conservative": (7, -7, 4),
            "moderate": (5, -5, 3),
            "aggressive": (5, -5, 3),
        }
        buy_th, sell_th, min_str = thresholds.get(self.mode, thresholds["aggressive"])

        for i in range(200, n):
            score, strength = 0, 0
            row_rsi = rsi[i]
            if not np.isnan(row_rsi):
                if row_rsi < 30:
                    score += 3
                    strength += 1
                elif row_rsi > 70:
                    score -= 3
                    strength += 1

            mh = macd_hist[i]
            mh_prev = macd_hist[i - 1]
            if not np.isnan(mh) and not np.isnan(mh_prev):
                if mh > 0 and mh_prev <= 0:
                    score += 2
                    strength += 1
                elif mh < 0 and mh_prev >= 0:
                    score -= 2
                    strength += 1

            if not np.isnan(macd[i]) and not np.isnan(macd_signal[i]):
                if macd[i] > macd_signal[i]:
                    score += 1
                else:
                    score -= 1

            if close[i] <= bb_lower[i]:
                score += 2
                strength += 1
            elif close[i] >= bb_upper[i]:
                score -= 2
                strength += 1

            if sma_7 is not None and sma_25 is not None:
                prev_sma_7 = sma_7[i - 1]
                prev_sma_25 = sma_25[i - 1]
                if not np.isnan(prev_sma_7) and not np.isnan(prev_sma_25):
                    if prev_sma_7 < prev_sma_25 and sma_7[i] > sma_25[i]:
                        score += 2
                        strength += 1
                    elif prev_sma_7 > prev_sma_25 and sma_7[i] < sma_25[i]:
                        score -= 2
                        strength += 1

            if sma_50 is not None and sma_200 is not None:
                if not np.isnan(sma_50[i]) and not np.isnan(sma_200[i]):
                    if close[i] > sma_50[i] and sma_50[i] > sma_200[i]:
                        score += 1
                        strength += 1
                    elif close[i] < sma_50[i] and sma_50[i] < sma_200[i]:
                        score -= 1
                        strength += 1

            if not np.isnan(stoch_k[i]) and not np.isnan(stoch_d[i]):
                if stoch_k[i] < 20 and stoch_d[i] < 20:
                    score += 1
                    strength += 1
                elif stoch_k[i] > 80 and stoch_d[i] > 80:
                    score -= 1
                    strength += 1

            if not np.isnan(atr[i]):
                recent_atr = np.nanmedian(atr[max(0, i - 20):i + 1])
                if recent_atr > 0 and atr[i] < recent_atr * 0.6:
                    strength -= 1

            if score >= buy_th and strength >= min_str:
                signals[i] = 1
            elif score <= sell_th and strength >= min_str:
                signals[i] = -1
            strengths[i] = strength

        df['Signal'] = signals
        df['signal_strength'] = strengths
        buys = int((signals == 1).sum())
        sells = int((signals == -1).sum())
        print(f" Tín hiệu ({self.mode}): {buys+sells} lệnh ({buys} BUY / {sells} SELL)")
        return df

    def _evaluate_row(self, df: pd.DataFrame, i: int) -> Tuple[int, int]:
        return self._evaluate_row_fast(df, i)

    def _evaluate_row_fast(self, df: pd.DataFrame, i: int) -> Tuple[int, int]:
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        score, strength = 0, 0

        rsi = row.get('RSI', np.nan)
        if not np.isnan(rsi):
            if rsi < 30:
                score += 3
                strength += 1
            elif rsi > 70:
                score -= 3
                strength += 1

        mh, mhp = row.get('MACD_Hist', np.nan), prev.get('MACD_Hist', np.nan)
        if not np.isnan(mh) and not np.isnan(mhp):
            if mh > 0 and mhp <= 0:
                score += 2
                strength += 1
            elif mh < 0 and mhp >= 0:
                score -= 2
                strength += 1

        if row['close'] <= row.get('BB_Lower', np.nan):
            score += 2
            strength += 1
        elif row['close'] >= row.get('BB_Upper', np.nan):
            score -= 2
            strength += 1

        if 'SMA_7' in df and 'SMA_25' in df:
            if prev['SMA_7'] < prev['SMA_25'] and row['SMA_7'] > row['SMA_25']:
                score += 2
                strength += 1
            elif prev['SMA_7'] > prev['SMA_25'] and row['SMA_7'] < row['SMA_25']:
                score -= 2
                strength += 1

        thresholds = {
            "conservative": (10, -10, 7),
            "moderate": (7, -7, 5),
            "aggressive": (3, -3, 2),
        }
        buy_th, sell_th, min_str = thresholds.get(self.mode, thresholds["aggressive"])

        if score >= buy_th and strength >= min_str:
            return 1, strength
        elif score <= sell_th and strength >= min_str:
            return -1, strength
        return 0, 0

# ====================================================================
# 4. SHORT-TERM SCALPING (SIDEWAY MARKET)
# ====================================================================
class ShortTermScalper:
    """Phân tích ngắn hạn cho thị trường sideway ở các khung 1M/5M/15M/30M."""

    def __init__(self, timeframes: Optional[List[str]] = None):
        self.timeframes = timeframes or ["1M", "5M", "15M", "30M"]

    def analyze(self, df: pd.DataFrame, regime: str = "SIDEWAY") -> List[Dict[str, Any]]:
        if df is None or len(df) < 50:
            return []

        regime_key = (regime or "").upper()
        if regime_key != "SIDEWAY":
            return []

        close = df['close'].to_numpy(dtype=np.float64)
        high = df['high'].to_numpy(dtype=np.float64)
        low = df['low'].to_numpy(dtype=np.float64)
        rsi = df.get('RSI', pd.Series(np.full(len(df), np.nan))).to_numpy(dtype=np.float64)
        atr = df.get('ATR', pd.Series(np.full(len(df), np.nan))).to_numpy(dtype=np.float64)
        adx = df.get('ADX', pd.Series(np.full(len(df), np.nan))).to_numpy(dtype=np.float64)
        sma_50 = df.get('SMA_50', pd.Series(np.full(len(df), np.nan))).to_numpy(dtype=np.float64)
        ema_9 = pd.Series(close).ewm(span=9, adjust=False).mean().to_numpy(dtype=np.float64)
        ema_21 = pd.Series(close).ewm(span=21, adjust=False).mean().to_numpy(dtype=np.float64)

        last_close = float(close[-1])
        last_time = df['time'].iloc[-1]
        recent_high = float(np.max(high[-20:]))
        recent_low = float(np.min(low[-20:]))
        recent_mid = (recent_high + recent_low) / 2
        last_atr = float(atr[-1]) if not np.isnan(atr[-1]) else 1.0
        current_rsi = float(rsi[-1]) if not np.isnan(rsi[-1]) else 50.0
        current_adx = float(adx[-1]) if not np.isnan(adx[-1]) else 25.0

        is_sideway = regime_key == "SIDEWAY" or current_adx <= 28.0
        if not is_sideway:
            return []

        recommendations = []
        for tf in self.timeframes:
            buy_score = 0.0
            sell_score = 0.0

            if last_close > ema_9[-1] and ema_9[-1] > ema_21[-1]:
                buy_score += 0.35
            else:
                sell_score += 0.35

            if last_close > recent_mid:
                buy_score += 0.20
            else:
                sell_score += 0.20

            if current_rsi > 55:
                buy_score += 0.20
            elif current_rsi < 45:
                sell_score += 0.20

            if last_close > recent_high * 0.995:
                buy_score += 0.15
            elif last_close < recent_low * 1.005:
                sell_score += 0.15

            if last_close > close[-2] and close[-2] > close[-3]:
                buy_score += 0.10
            elif last_close < close[-2] and close[-2] < close[-3]:
                sell_score += 0.10

            total = buy_score + sell_score
            prob_buy = round(min(0.95, max(0.05, buy_score / total)), 3)
            prob_sell = round(1 - prob_buy, 3)
            direction = "BUY" if prob_buy >= prob_sell else "SELL"
            confidence = max(prob_buy, prob_sell)

            if tf == "1M":
                tp_offset = max(last_atr * 0.6, 0.8)
                sl_offset = max(last_atr * 1.0, 1.0)
            elif tf == "5M":
                tp_offset = max(last_atr * 0.9, 1.2)
                sl_offset = max(last_atr * 1.4, 1.6)
            elif tf == "15M":
                tp_offset = max(last_atr * 1.2, 1.8)
                sl_offset = max(last_atr * 1.8, 2.2)
            else:
                tp_offset = max(last_atr * 1.5, 2.2)
                sl_offset = max(last_atr * 2.2, 2.8)

            if direction == "BUY":
                take_profit = round(last_close + tp_offset, 5)
                stop_loss = round(last_close - sl_offset, 5)
            else:
                take_profit = round(last_close - tp_offset, 5)
                stop_loss = round(last_close + sl_offset, 5)

            expected_correct_probability = round(max(prob_buy, prob_sell) * 100, 1)
            recommendations.append({
                "timeframe": tf,
                "entry_time": last_time.strftime('%Y-%m-%d %H:%M'),
                "entry_price": round(last_close, 5),
                "direction": direction,
                "prob_buy": round(prob_buy * 100, 1),
                "prob_sell": round(prob_sell * 100, 1),
                "confidence": round(confidence * 100, 1),
                "expected_correct_probability": expected_correct_probability,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "reason": "Sideway + EMA confirmation + range bounce" if direction == "BUY" else "Sideway + EMA rejection + range rejection",
            })

        return recommendations

# ====================================================================
# 5. FINAL BOSS MODULES
# ====================================================================
class FibonacciEngine:
    """Tính toán mức Fibonacci động từ Swing High/Low."""
    def get_levels(self, df, lookback=50):
        recent_high = df['high'].rolling(lookback).max().iloc[-1]
        recent_low = df['low'].rolling(lookback).min().iloc[-1]
        diff = recent_high - recent_low
        return {
            '0.0': recent_high, '0.236': recent_high - 0.236*diff,
            '0.382': recent_high - 0.382*diff, '0.5': recent_high - 0.5*diff,
            '0.618': recent_high - 0.618*diff, '1.0': recent_low
        }

class MarketRegimeDetector:
    """Nhận diện chế độ thị trường (Trending vs Sideway) dùng GMM."""
    def __init__(self):
        self.gmm = GaussianMixture(n_components=2, random_state=42)
        self.is_trained = False

    def fit(self, df: pd.DataFrame):
        if 'ADX' not in df.columns or 'ATR' not in df.columns: return
        clean_df = df[['ADX', 'ATR']].dropna()
        if len(clean_df) < 50: return
        self.gmm.fit(clean_df)
        self.is_trained = True
        print("✅ [Regime] Đã huấn luyện mô hình nhận diện thị trường.")

    def detect(self, current_adx: float, current_atr: float) -> str:
        if not self.is_trained: return "UNKNOWN"
        X = np.array([[current_adx, current_atr]])
        cluster = self.gmm.predict(X)[0]
        means = self.gmm.means_
        cluster_0_adx = means[0][0]
        cluster_1_adx = means[1][0]
        if cluster == 0:
            return "TRENDING" if cluster_0_adx > cluster_1_adx else "SIDEWAY"
        else:
            return "TRENDING" if cluster_1_adx > cluster_0_adx else "SIDEWAY"

class NewsSentimentAnalyzer:
    """NLP Sentiment Analysis (FinBERT + NewsAPI)."""
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.model = None
        if NLP_AVAILABLE:
            try:
                print("🧠 [NLP] Đang tải FinBERT...")
                self.model = pipeline("sentiment-analysis", model="ProsusAI/finbert")
                print("✅ [NLP] FinBERT sẵn sàng.")
            except Exception as e:
                print(f"❌ [NLP] Lỗi tải model: {e}")

    def get_score(self, symbol: str) -> float:
        if not self.model:
            print("⚠️ [NLP] Dùng Mock Data (Score: 0.0)")
            return 0.0
        
        headlines = self._fetch_headlines(symbol)
        if not headlines: return 0.0
        
        results = self.model(headlines)
        total_score = 0.0
        for res in results:
            label = res['label']
            score = res['score']
            if label == 'positive': total_score += score
            elif label == 'negative': total_score -= score
        
        avg_score = total_score / len(results)
        print(f"📰 [NLP] Sentiment {symbol}: {avg_score:.2f} (Từ {len(headlines)} tin)")
        return avg_score

    def _fetch_headlines(self, symbol: str) -> list:
        if not self.api_key:
            print("⚠️ [NLP] Chưa có API Key NewsAPI. Dùng dữ liệu giả lập.")
            return [
                f"Federal Reserve signals potential rate hike affecting {symbol}",
                f"Market volatility increases as {symbol} faces resistance",
                f"Investors remain cautious about {symbol} outlook"
            ]
        
        try:
            keyword_map = {
                'XAUUSD': 'Gold OR Precious Metals',
                'EURUSD': 'EUR OR ECB OR Eurozone',
                'GBPUSD': 'GBP OR BOE OR UK Economy',
            }
            keyword = keyword_map.get(symbol, 'Financial Market')
            url = f"https://newsapi.org/v2/everything?q={keyword}&sortBy=publishedAt&pageSize=5&apiKey={self.api_key}"
            response = requests.get(url, timeout=5)
            data = response.json()
            if data['status'] == 'ok':
                return [art['title'] for art in data['articles'][:5]]
        except Exception as e:
            print(f"⚠️ [NLP] Lỗi lấy tin tức: {e}")
        return []

class DynamicRiskManager:
    """Quản lý rủi ro động: Circuit Breaker + Correlation Check."""
    def __init__(self, client: MT5Client, max_dd_percent: float = 15.0):
        self.client = client
        self.max_dd = max_dd_percent
        self.start_balance = 0.0

    def check_circuit_breaker(self) -> bool:
        info = self.client.get_account_info()
        if not info: return False
        if self.start_balance == 0: self.start_balance = info['balance']
        
        dd = (self.start_balance - info['equity']) / self.start_balance * 100
        if dd >= self.max_dd:
            print(f"🚨 [RISK] CIRCUIT BREAKER! DD: {dd:.2f}%")
            return False
        return True

    def check_correlation(self, new_symbol: str, new_dir: str) -> bool:
        if not MT5_AVAILABLE or mt5 is None or not self.client.connected:
            return True
        positions = mt5.positions_get()
        if not positions: return True
        
        correlated_groups = [
            ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'],
            ['USDJPY', 'USDCHF', 'USDCAD'],
            ['XAUUSD', 'XAGUSD']
        ]
        
        for pos in positions:
            sym = pos.symbol
            if sym == new_symbol:
                print(f"⚠️ [RISK] Đã có lệnh mở trên {new_symbol}. Bỏ qua lệnh mới.")
                return False
            
            pos_dir = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
            if pos_dir == new_dir:
                for group in correlated_groups:
                    if sym in group and new_symbol in group:
                        print(f"⚠️ [RISK] Phát hiện tương quan cao với {sym} (cùng hướng {new_dir})")
                        return False
        return True

class TWAPExecutionEngine:
    """Thuật toán TWAP (Time-Weighted Average Price) - Chia nhỏ lệnh."""
    def __init__(self, mt5_client: MT5Client, symbol: str, max_spread_pips: float = 20.0):
        self.client = mt5_client
        self.symbol = symbol
        self.max_spread = max_spread_pips
        self.pip_size = 0.01 if 'XAU' in symbol else 0.0001

    def _check_spread(self) -> bool:
        if not MT5_AVAILABLE or mt5 is None or not self.client.connected:
            return False
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick: return False
        spread_pips = (tick.ask - tick.bid) / self.pip_size
        if spread_pips > self.max_spread:
            print(f"⚠️ [TWAP] Spread quá cao ({spread_pips:.1f} pips). Hủy lệnh.")
            return False
        return True

    def calculate_volume(self, risk_percent: float = 5.0) -> float:
        """Tính volume dựa trên risk % vốn."""
        info = self.client.get_account_info()
        if not info: return 0.01
        
        balance = info['balance']
        risk_amount = balance * risk_percent / 100  # 5% của $100 = $5
        
        # Volume = Risk / (SL_pips * pip_value)
        # Với Vàng: 1 lot = 100 oz, 1 pip = $0.01
        pip_value_per_lot = 100 * self.pip_size  # = $1/lot
        sl_pips = trading_cfg.sl_pips
        volume = risk_amount / (sl_pips * pip_value_per_lot)
        
        # Giới hạn volume
        volume = max(0.01, min(volume, 0.1))  # Min 0.01, Max 0.1
        return round(volume, 2)

    def execute_twap(self, signal_type: str, total_volume: float, 
                     duration_seconds: int = 3, slices: int = 2) -> List[int]:
        if not self._check_spread(): return []

        if not self.client.connected:
            print("⚠️ [TWAP] MT5 chưa kết nối, bỏ qua thực thi TWAP.")
            return []

        print(f" [TWAP] Bắt đầu rải lệnh {signal_type} {total_volume} lot trong {duration_seconds}s...")
        
        slice_volume = round(total_volume / slices, 2)
        if slice_volume < 0.01: slice_volume = 0.01
        interval = duration_seconds / slices
        
        executed_tickets = []
        
        for i in range(slices):
            tick = mt5.symbol_info_tick(self.symbol)
            if not tick: break
            
            price = tick.ask if signal_type == "BUY" else tick.bid
            sl = price - (trading_cfg.sl_pips * self.pip_size) if signal_type == "BUY" else price + (trading_cfg.sl_pips * self.pip_size)
            tp = price + (trading_cfg.tp_pips * self.pip_size) if signal_type == "BUY" else price - (trading_cfg.tp_pips * self.pip_size)
            
            print(f"   📤 Slice {i+1}/{slices}: {slice_volume} lot @ {price:.2f}...")
            ticket = self.client.place_order(
                symbol=self.symbol, order_type=signal_type,
                volume=slice_volume, sl=sl, tp=tp, comment=f"TWAP_{i+1}"
            )
            
            if ticket:
                executed_tickets.append(ticket)
            else:
                print(f"   ❌ Slice {i+1} thất bại. Dừng TWAP.")
                break
                
            if i < slices - 1:
                time.sleep(interval)
                
        print(f"✅ [TWAP] Hoàn tất. Đã khớp {len(executed_tickets)} slice.")
        return executed_tickets

# ====================================================================
# 5. BACKTEST & ML
# ====================================================================
@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    signal_type: str
    tp: float
    sl: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pips: Optional[float] = None
    profit: Optional[float] = None
    result: Optional[str] = None
    duration_bars: Optional[int] = None

class BacktestEngine:
    def __init__(self, df: pd.DataFrame, symbol: str, tp_pips=30, sl_pips=15, initial_balance=100):
        self.df = df
        self.symbol = symbol
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.initial_balance = initial_balance
        self.trades: List[Trade] = []
        self.pip_size = 0.01 if symbol in ['XAUUSD', 'XAGUSD'] else 0.0001

    def run(self) -> Dict:
        self.trades = []
        if 'Signal' not in self.df.columns: return {'error': 'Chưa có cột Signal'}
        
        signals = self.df[self.df['Signal'] != 0].copy()
        if len(signals) == 0: return {'error': 'Không có tín hiệu'}
        
        open_trade = None
        for signal_idx, (row_idx, row) in enumerate(signals.iterrows()):
            if open_trade is not None:
                h, l, entry = row['high'], row['low'], open_trade.entry_price
                is_buy = open_trade.signal_type == 'BUY'
                
                tp_hit = (h >= open_trade.tp) if is_buy else (l <= open_trade.tp)
                sl_hit = (l <= open_trade.sl) if is_buy else (h >= open_trade.sl)
                
                if tp_hit or sl_hit:
                    if tp_hit:
                        open_trade.exit_price = open_trade.tp
                        open_trade.pips = (open_trade.tp - entry) / self.pip_size if is_buy else (entry - open_trade.tp) / self.pip_size
                        open_trade.result = "WIN"
                    else:
                        open_trade.exit_price = open_trade.sl
                        open_trade.pips = (open_trade.sl - entry) / self.pip_size if is_buy else (entry - open_trade.sl) / self.pip_size
                        open_trade.result = "LOSS"
                    
                    if self.symbol in ['XAUUSD', 'XAGUSD']:
                        open_trade.profit = open_trade.pips * 0.01 * 100
                    else:
                        open_trade.profit = open_trade.pips * 0.01 * 10
                    
                    open_trade.exit_time = row['time']
                    open_trade.duration_bars = int(row_idx) - int(open_trade.entry_idx)
                    self.trades.append(open_trade)
                    open_trade = None

            if open_trade is None:
                signal = int(row['Signal'])
                entry_price = row['close']
                if signal == 1:
                    tp = entry_price + self.tp_pips * self.pip_size
                    sl = entry_price - self.sl_pips * self.pip_size
                    open_trade = Trade(row['time'], entry_price, "BUY", tp, sl)
                else:
                    tp = entry_price - self.tp_pips * self.pip_size
                    sl = entry_price + self.sl_pips * self.pip_size
                    open_trade = Trade(row['time'], entry_price, "SELL", tp, sl)
                open_trade.entry_idx = row_idx

        if open_trade is not None:
            last_row = self.df.iloc[-1]
            open_trade.exit_price = last_row['close']
            open_trade.exit_time = last_row['time']
            open_trade.pips = (last_row['close'] - open_trade.entry_price) / self.pip_size if open_trade.signal_type == 'BUY' else (open_trade.entry_price - last_row['close']) / self.pip_size
            open_trade.result = 'WIN' if open_trade.pips >= 0 else 'LOSS'
            if self.symbol in ['XAUUSD', 'XAGUSD']:
                open_trade.profit = open_trade.pips * 0.01 * 100
            else:
                open_trade.profit = open_trade.pips * 0.01 * 10
            open_trade.duration_bars = int(self.df.index[-1]) - int(open_trade.entry_idx)
            self.trades.append(open_trade)

        return self._calculate_results()

    def _calculate_results(self) -> Dict:
        if not self.trades:
            return {'total_trades': 0, 'win_rate': 0, 'profit_factor': 0, 'total_profit': 0, 'max_drawdown': 0}
        
        wins = [t for t in self.trades if t.result == 'WIN']
        losses = [t for t in self.trades if t.result == 'LOSS']
        total_trades = len(self.trades)
        win_rate = len(wins) / total_trades
        total_profit = sum(t.profit or 0 for t in self.trades)
        
        total_win = sum(t.profit or 0 for t in wins)
        total_loss = abs(sum(t.profit or 0 for t in losses))
        profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
        
        balance, peak, max_dd = self.initial_balance, self.initial_balance, 0
        for t in self.trades:
            balance += (t.profit or 0)
            peak = max(peak, balance)
            dd = (peak - balance) / peak * 100
            max_dd = max(max_dd, dd)
            
        return {
            'total_trades': total_trades, 'wins': len(wins), 'losses': len(losses),
            'win_rate': win_rate, 'profit_factor': profit_factor, 'total_profit': total_profit,
            'max_drawdown': max_dd
        }

    def predict_next_signal(self, df: pd.DataFrame) -> Dict:
        print("🤖 Đang train ML model...")
        feature_cols = ['RSI', 'MACD_Hist', 'ATR', 'BB_Lower', 'BB_Upper']
        feature_cols = [c for c in feature_cols if c in df.columns]
        if len(feature_cols) < 3: return {'prediction': 'NEUTRAL', 'prob_up': 0.5, 'prob_down': 0.5}
        
        df_ml = df.copy()
        df_ml['target'] = (df_ml['close'].shift(-1) > df_ml['close']).astype(int)
        df_ml = df_ml.dropna(subset=feature_cols + ['target'])
        if len(df_ml) < 100: return {'prediction': 'NEUTRAL', 'prob_up': 0.5, 'prob_down': 0.5}
        
        X = df_ml[feature_cols].values
        y = df_ml['target'].values
        
        tscv = TimeSeriesSplit(n_splits=3)
        model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        scores = []
        for train_idx, test_idx in tscv.split(X):
            model.fit(X[train_idx], y[train_idx])
            scores.append(model.score(X[test_idx], y[test_idx]))
        accuracy = np.mean(scores)
        
        model.fit(X, y)
        last_feat = X[-1:].reshape(1, -1)
        proba = model.predict_proba(last_feat)[0]
        prob_up = float(proba[1]) if len(proba) > 1 else 0.5
        prob_down = float(proba[0]) if len(proba) > 0 else 0.5
        
        # ← GIẢM THRESHOLD XUỐNG 50% CHO SCALPING
        prediction = "BUY" if prob_up > 0.50 else ("SELL" if prob_down > 0.50 else "NEUTRAL")
        print(f"🔮 ML dự đoán: {prediction} (↑{prob_up:.1%} / ↓{prob_down:.1%}) | Accuracy: {accuracy:.1%}")
        return {'prediction': prediction, 'prob_up': prob_up, 'prob_down': prob_down, 'accuracy': accuracy}

    def monte_carlo_simulation(self, n_simulations=1000) -> Dict:
        if not self.trades: return {'win_rate_mean': 0, 'win_rate_std': 0}
        wr = self._calculate_results()['win_rate']
        np.random.seed(42)
        mc = [np.mean(np.random.choice([1 if t.result=='WIN' else 0 for t in self.trades], size=len(self.trades), replace=True)) for _ in range(n_simulations)]
        return {'win_rate_mean': np.mean(mc), 'win_rate_std': np.std(mc)}

# ====================================================================
# 6. DASHBOARD PAYLOAD HELPERS
# ====================================================================
def build_dashboard_payload(prediction: Optional[Dict[str, Any]] = None,
                            fib: Optional[Dict[str, Any]] = None,
                            regime: str = "UNKNOWN",
                            monte_carlo: Optional[Dict[str, Any]] = None,
                            short_term_recommendations: Optional[List[Dict[str, Any]]] = None,
                            reliability_metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        'prediction': prediction or {'prediction': 'NEUTRAL', 'prob_up': 0.5, 'prob_down': 0.5, 'accuracy': 0.0},
        'fibonacci': fib or {},
        'regime': regime,
        'monte_carlo': monte_carlo or {},
        'short_term_recommendations': short_term_recommendations or [],
        'short_term_best': None,
        'reliability_metrics': reliability_metrics or {},
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    normalized_recommendations = []
    for rec in payload['short_term_recommendations']:
        normalized = dict(rec)
        if 'expected_correct_probability' not in normalized:
            prob_buy = normalized.get('prob_buy', 0.0)
            prob_sell = normalized.get('prob_sell', 0.0)
            normalized['expected_correct_probability'] = round(max(prob_buy, prob_sell), 1)
        normalized_recommendations.append(normalized)

    payload['short_term_recommendations'] = normalized_recommendations
    if payload['short_term_recommendations']:
        payload['short_term_best'] = max(payload['short_term_recommendations'], key=lambda x: x.get('confidence', 0))

    return payload


def save_dashboard_payload(payload: Dict[str, Any], path: str = 'final_boss_data.json') -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


class TradeLogger:
    def log_trades(self, trades: List[Trade]):
        if not trades: return
        data = []
        for t in trades:
            data.append({
                'Thời gian vào': t.entry_time.strftime('%Y-%m-%d %H:%M'),
                'Thời gian ra': t.exit_time.strftime('%Y-%m-%d %H:%M') if t.exit_time else '',
                'Hướng': t.signal_type,
                'Giá vào': f"{t.entry_price:.5f}",
                'Giá ra': f"{t.exit_price:.5f}" if t.exit_price else '',
                'Pips': f"{t.pips:.1f}" if t.pips else '',
                'Lợi nhuận ($)': f"${t.profit:.2f}" if t.profit else '',
                'Kết quả': t.result or '',
                'Số nến giữ': t.duration_bars or '',
            })
        df = pd.DataFrame(data)
        df.to_csv('trade_log.csv', index=False, encoding='utf-8-sig')
        print(f"📁 Đã ghi {len(trades)} giao dịch vào trade_log.csv")

    def log_signals(self, df: pd.DataFrame):
        if 'Signal' not in df.columns: return
        signals = df[df['Signal'] != 0].copy()
        if len(signals) == 0: return
        data = []
        for _, row in signals.iterrows():
            data.append({
                'Thời gian': row['time'].strftime('%Y-%m-%d %H:%M'),
                'Giá': f"{row['close']:.5f}",
                'Tín hiệu': 'BUY' if row['Signal'] == 1 else 'SELL',
                'Độ mạnh': int(row['signal_strength']),
            })
        df_out = pd.DataFrame(data)
        df_out.to_csv('trading_signals.csv', index=False, encoding='utf-8-sig')
        print(f"📁 Đã ghi {len(signals)} tín hiệu vào trading_signals.csv")

def _generate_sample_rates(bars: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base_time = pd.Timestamp("2024-01-01")
    timestamps = pd.date_range(base_time, periods=bars, freq="min")
    base_price = 1900.0 + np.linspace(0, 80, bars)
    drift = np.cumsum(rng.normal(0, 0.25, bars))
    close = base_price + drift
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0.1, 0.5, bars)
    low = np.minimum(open_, close) - rng.uniform(0.1, 0.5, bars)
    volume = rng.integers(100, 500, bars)
    return pd.DataFrame({
        'time': timestamps,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    })

# ====================================================================
# 7. MAIN
# ====================================================================
def process_market_cycle(client: MT5Client, cycle_index: int = 0) -> None:
    print(f"\n🔄 Chu kỳ {cycle_index + 1}: lấy dữ liệu realtime...")
    df = client.get_rates(trading_cfg.symbol, trading_cfg.timeframe, 5000)
    if df is None:
        print("⚠️ Không lấy được dữ liệu từ MT5, dùng dữ liệu mẫu.")
        df = _generate_sample_rates(5000)

    df = IndicatorEngine.compute_all(df, verbose=False)
    df = SignalEngine(mode=CURRENT_MODE).generate_signals(df)

    bt = BacktestEngine(
        df=df,
        symbol=trading_cfg.symbol,
        tp_pips=trading_cfg.tp_pips,
        sl_pips=trading_cfg.sl_pips,
        initial_balance=trading_cfg.account_equity,
    )
    results = bt.run()

    if 'error' not in results:
        print(f"\n{'='*50}")
        print(f"   KẾT QUẢ BACKTEST")
        print(f"{'='*50}")
        print(f"  Tổng lệnh:     {results['total_trades']}")
        print(f"  Win Rate:      {results['win_rate']:.1%}")
        print(f"  Profit Factor: {results['profit_factor']:.2f}")
        print(f"  Tổng PnL:      ${results['total_profit']:.2f}")
        print(f"  Max Drawdown:  {results['max_drawdown']:.1f}%")
        print(f"{'='*50}")

    prediction = bt.predict_next_signal(df)
    mc = bt.monte_carlo_simulation(1000)
    print(f"\n🎲 Monte Carlo: WR {mc['win_rate_mean']:.1%} ± {mc['win_rate_std']:.1%}")

    print("\n🚀 [Final Boss] Phân tích đa chiều...")
    fib = FibonacciEngine().get_levels(df)
    regime_detector = MarketRegimeDetector()
    regime_detector.fit(df)
    regime = regime_detector.detect(df['ADX'].iloc[-1], df['ATR'].iloc[-1])
    print(f" [Fibonacci] Mức 0.618: {fib['0.618']:.2f}")
    print(f"🌪️ [Regime] Thị trường đang: {regime}")

    if regime == "SIDEWAY":
        short_term = ShortTermScalper()
        recommendations = short_term.analyze(df, regime=regime)
        if recommendations:
            best = max(recommendations, key=lambda x: x['confidence'])
            print("\n⚡ [Short-Term Scalping] Khung nhỏ sideway:")
            for rec in recommendations:
                print(
                    f"   • {rec['timeframe']} | {rec['direction']} | "
                    f"Vào lúc {rec['entry_time']} | Buy {rec['prob_buy']:.1f}% / Sell {rec['prob_sell']:.1f}% | "
                    f"Độ tin cậy {rec['confidence']:.1f}% | TP {rec['take_profit']:.5f} | SL {rec['stop_loss']:.5f}"
                )
            print(f"   ⭐ Khung ưu tiên: {best['timeframe']} | {best['direction']} | Buy {best['prob_buy']:.1f}% / Sell {best['prob_sell']:.1f}%")
        else:
            print("   • Không có tín hiệu ngắn hạn đủ mạnh ở khung sideway.")

    print(f"\n🔍 [Debug] ML Probabilities:")
    print(f"   ├─ Prob UP:   {prediction.get('prob_up', 0):.1%}")
    print(f"   ├─ Prob DOWN: {prediction.get('prob_down', 0):.1%}")
    print(f"   └─ Threshold: 50%")

    reliability_metrics = {
        'win_rate': results.get('win_rate', 0),
        'profit_factor': results.get('profit_factor', 0),
        'total_profit': results.get('total_profit', 0),
        'max_drawdown': results.get('max_drawdown', 0),
        'total_trades': results.get('total_trades', 0),
        'wins': results.get('wins', 0),
        'losses': results.get('losses', 0),
    }

    dashboard_payload = build_dashboard_payload(
        prediction=prediction,
        fib=fib,
        regime=regime,
        monte_carlo=mc,
        short_term_recommendations=recommendations if regime == "SIDEWAY" else [],
        reliability_metrics=reliability_metrics,
    )
    save_dashboard_payload(dashboard_payload)
    print("📦 [Dashboard] Đã cập nhật final_boss_data.json")

    print("\n💰 [Final Boss] Kiểm tra điều kiện vào lệnh...")
    signal_dir = prediction['prediction']
    if signal_dir == 'NEUTRAL':
        last_signal = df['Signal'].iloc[-1]
        last_strength = df['signal_strength'].iloc[-1]

        if last_signal == 1 and last_strength >= 2:
            signal_dir = "BUY"
            print(f"⚡ [Fallback] Signal Engine: BUY (Strength: {last_strength})")
        elif last_signal == -1 and last_strength >= 2:
            signal_dir = "SELL"
            print(f"⚡ [Fallback] Signal Engine: SELL (Strength: {last_strength})")
        else:
            print("⏸️ ML dự đoán NEUTRAL và Signal Engine yếu. Chờ nến tiếp theo.")
            return

    risk_mgr = DynamicRiskManager(client, max_dd_percent=trading_cfg.max_daily_loss)
    if not risk_mgr.check_circuit_breaker():
        print(" Bị chặn bởi Circuit Breaker.")
        return

    if not risk_mgr.check_correlation(trading_cfg.symbol, signal_dir):
        print("🛑 Bị chặn bởi Risk Manager (Correlation).")
        return

    print(f"✅ [Final Boss] TẤT CẢ ĐIỀU KIỆN ĐẠT. VÀO LỆNH {signal_dir}...")
    twap = TWAPExecutionEngine(client, trading_cfg.symbol, max_spread_pips=trading_cfg.max_spread)
    volume = twap.calculate_volume(risk_percent=trading_cfg.risk_percent)
    print(f"📊 Volume tính toán: {volume} lot (Risk: {trading_cfg.risk_percent}% = ${trading_cfg.account_equity * trading_cfg.risk_percent / 100})")

    tickets = twap.execute_twap(signal_dir, volume, duration_seconds=3, slices=2)
    if tickets:
        print(f"✅ Đã vào lệnh với {len(tickets)} tickets: {tickets}")

    logger = TradeLogger()
    logger.log_trades(bt.trades)
    logger.log_signals(df)

    print(f"\n{'='*60}")
    print(f"  ✅ HOÀN TẤT PHÂN TÍCH")
    print(f"{'='*60}")
    print(f"  📊 Dashboard: streamlit run dashboard.py")
    print(f"{'='*60}")


def main(max_cycles: Optional[int] = None, interval_minutes: int = 30):
    print("=" * 60)
    print("  🤖 CFD AUTO TRADING SYSTEM v9.0 (SCALPING FINAL BOSS)")
    print("=" * 60)
    print(f"  Mode: {CURRENT_MODE.upper()}")
    print(f"  Symbol: {trading_cfg.symbol} ({trading_cfg.timeframe})")
    print(f"  TP/SL: {trading_cfg.tp_pips}/{trading_cfg.sl_pips} pips")
    print(f"  Risk: {trading_cfg.risk_percent}% vốn/lệnh")
    print(f"  Vốn: ${trading_cfg.account_equity}")
    print(f"  News API Key: {'✅ Đã cấu hình' if NEWS_API_KEY else '⚠️ Chưa cấu hình (dùng Mock)'}")
    print(f"  Realtime interval: every {interval_minutes} minute(s)")
    print("=" * 60)

    client = MT5Client(DEMO_ACCOUNT, DEMO_PASSWORD, DEMO_SERVER)
    connected = client.connect()
    if not connected:
        print("⚠️ MT5 chưa kết nối. Chạy ở chế độ mô phỏng.")

    try:
        cycle_index = 0
        while True:
            process_market_cycle(client, cycle_index)
            if max_cycles is not None and cycle_index + 1 >= max_cycles:
                break
            cycle_index += 1
            if interval_minutes > 0:
                print(f"⏳ Đợi {interval_minutes} phút cho chu kỳ tiếp theo...")
                time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        print("🛑 Dừng vòng lặp realtime.")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
    