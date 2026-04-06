"""
indicators.py — Tính toán các chỉ báo kỹ thuật
Dùng pandas_ta để tối ưu, bổ sung Market Regime và Confluence.
"""

import pandas as pd
import importlib.metadata  # FIX pandas-ta-openbb bug
import pandas_ta as ta
from datetime import datetime, timedelta, timezone


# ── Thời gian phiên giao dịch ─────────────────────────────────────────────────

def get_session_progress() -> float:
    """Trả về tỷ lệ phiên giao dịch đã trôi qua (0.0–1.0). 1.0 nếu phiên đã kết thúc."""
    vn_tz = timezone(timedelta(hours=7))
    now   = datetime.now(vn_tz)

    if now.weekday() >= 5:
        return 1.0

    market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    lunch_start  = now.replace(hour=11, minute=30, second=0, microsecond=0)
    lunch_end    = now.replace(hour=13, minute=0,  second=0, microsecond=0)
    market_close = now.replace(hour=14, minute=30, second=0, microsecond=0)

    total_minutes = 225  # sáng 135' + chiều 90'

    if now < market_open or now >= market_close:
        return 1.0
    if lunch_start <= now < lunch_end:
        elapsed = 135
    elif now >= lunch_end:
        elapsed = 135 + int((now - lunch_end).total_seconds() // 60)
    else:
        elapsed = int((now - market_open).total_seconds() // 60)

    return max(elapsed / total_minutes, 0.01)


# ── Chỉ báo kỹ thuật cơ bản (Tái cấu trúc dùng pandas_ta) ────────────────────

def calculate_rsi(prices: list, period: int = 14) -> dict:
    """Tính RSI bằng pandas_ta"""
    if len(prices) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên, hiện có {len(prices)}"}

    s = pd.Series(prices)
    rsi_s = ta.rsi(s, length=period)
    rsi = round(rsi_s.iloc[-1], 2)

    if rsi < 30:
        signal = "OVERSOLD (quá bán) → Có thể là cơ hội MUA"
    elif rsi > 70:
        signal = "OVERBOUGHT (quá mua) → Cân nhắc CHỐT LỜI"
    else:
        signal = "NEUTRAL (trung tính) → Chờ thêm tín hiệu"

    return {"rsi": rsi, "signal": signal, "period": period}


def calculate_moving_average(prices: list, period: int) -> dict:
    """Tính MA bằng pandas_ta"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên"}

    s = pd.Series(prices)
    ma_s = ta.sma(s, length=period)
    ma = round(ma_s.iloc[-1], 2)
    
    latest = prices[-1]
    trend  = "TRÊN MA → Xu hướng tăng ✅" if latest > ma else "DƯỚI MA → Xu hướng giảm ⚠️"

    return {"ma": ma, "latest_price": latest, "trend": trend, "period": period}


def calculate_macd(prices: list, fast: int = 12, slow: int = 26, signal_period: int = 9) -> dict:
    """Tính MACD bằng pandas_ta"""
    min_required = slow + signal_period
    if len(prices) < min_required:
        return {"error": f"Cần ít nhất {min_required} phiên để tính MACD, hiện có {len(prices)}"}

    s = pd.Series(prices)
    macd_df = ta.macd(s, fast=fast, slow=slow, signal=signal_period)
    
    latest_macd   = round(macd_df.iloc[-1, 0], 4)
    latest_hist   = round(macd_df.iloc[-1, 1], 4)
    latest_signal = round(macd_df.iloc[-1, 2], 4)
    prev_hist     = round(macd_df.iloc[-2, 1], 4) if len(macd_df) >= 2 else 0

    if latest_hist > 0 and prev_hist <= 0:
        signal_text = "GOLDEN CROSS → Tín hiệu MUA mạnh 🟢"
    elif latest_hist < 0 and prev_hist >= 0:
        signal_text = "DEATH CROSS → Tín hiệu BÁN mạnh 🔴"
    elif latest_hist > 0 and latest_hist > prev_hist:
        signal_text = "MACD tăng tốc → Đà tăng đang mạnh lên ✅"
    elif latest_hist > 0 and latest_hist < prev_hist:
        signal_text = "MACD giảm tốc → Đà tăng đang yếu dần ⚠️"
    elif latest_hist < 0 and latest_hist < prev_hist:
        signal_text = "MACD giảm tốc → Đà giảm đang mạnh lên 🔴"
    else:
        signal_text = "MACD âm nhưng đang phục hồi → Theo dõi thêm 🟡"

    return {
        "macd":          latest_macd,
        "signal":        latest_signal,
        "histogram":     latest_hist,
        "signal_text":   signal_text,
        "fast":          fast,
        "slow":          slow,
        "signal_period": signal_period
    }


def calculate_bollinger(prices: list, period: int = 20, num_std: float = 2.0) -> dict:
    """Tính Bollinger Bands bằng pandas_ta"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên, hiện có {len(prices)}"}

    s = pd.Series(prices)
    bb_df = ta.bbands(s, length=period, std=num_std)
    
    lower     = round(bb_df.iloc[-1, 0], 2)
    middle    = round(bb_df.iloc[-1, 1], 2)
    upper     = round(bb_df.iloc[-1, 2], 2)
    bandwidth = round(bb_df.iloc[-1, 3], 2)
    percent_b = round(bb_df.iloc[-1, 4] * 100, 2)
    
    latest = prices[-1]

    if latest > upper:
        signal_text = "GIÁ VƯỢT BAND TRÊN → Quá mua, rủi ro điều chỉnh 🔴"
    elif latest < lower:
        signal_text = "GIÁ PHÁ BAND DƯỚI → Quá bán, có thể phục hồi 🟢"
    elif percent_b > 80:
        signal_text = "GIÁ GẦN BAND TRÊN → Cẩn thận chốt lời ⚠️"
    elif percent_b < 20:
        signal_text = "GIÁ GẦN BAND DƯỚI → Vùng tích lũy tiềm năng 🟡"
    elif latest > middle:
        signal_text = "GIÁ TRÊN MIDDLE BAND → Xu hướng tăng ✅"
    else:
        signal_text = "GIÁ DƯỚI MIDDLE BAND → Xu hướng giảm ⚠️"

    return {
        "upper":        upper,
        "middle":       middle,
        "lower":        lower,
        "latest_price": latest,
        "percent_b":    percent_b,
        "bandwidth":    bandwidth,
        "signal_text":  signal_text,
        "period":       period
    }


def calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> dict:
    """Tính ATR bằng pandas_ta"""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên để tính ATR"}

    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
    atr_s = ta.atr(df['high'], df['low'], df['close'], length=period)
    atr = round(atr_s.iloc[-1], 2)
    latest = closes[-1]
    atr_pct = round(atr / latest * 100, 2)

    if atr_pct < 1.5:
        volatility = "THẤP — Thị trường đang đi ngang, biên độ hẹp 😴"
    elif atr_pct < 3.0:
        volatility = "TRUNG BÌNH — Biến động bình thường, phù hợp giao dịch 🟡"
    elif atr_pct < 5.0:
        volatility = "CAO — Biến động mạnh, cần SL rộng hơn ⚠️"
    else:
        volatility = "RẤT CAO — Rủi ro lớn, nên giảm khối lượng giao dịch 🔴"

    return {
        "atr":           atr,
        "atr_pct":       f"{atr_pct}%",
        "latest_price":  latest,
        "volatility":    volatility,
        "sl_suggestion": round(latest - 1.5 * atr, 2),
        "tp_suggestion": round(latest + 2.0 * atr, 2),
        "period":        period
    }

# (Phân tích Khối lượng và S/R dùng loop giữ nguyên vì tính đặc thù cao, ít dùng tool chung)
def analyze_volume(closes: list, volumes: list, period: int = 20) -> dict:
    if len(volumes) < period: return {"error": "Thiếu dữ liệu"}
    avg_vol = sum(volumes[-period:]) / period
    latest_vol = volumes[-1]
    progress = get_session_progress()
    projected_vol = latest_vol if progress >= 1.0 else latest_vol / progress
    
    vol_ratio = round(projected_vol / avg_vol, 2) if avg_vol > 0 else 0
    price_up  = closes[-1] > closes[-5] if len(closes) >= 5 else None

    if vol_ratio >= 1.5 and price_up: signal = "VOLUME TĂNG + GIÁ TĂNG → Xu hướng tăng mạnh 🟢"
    elif vol_ratio >= 1.5 and not price_up: signal = "VOLUME TĂNG + GIÁ GIẢM → Lực bán lớn 🔴"
    elif vol_ratio < 0.7 and price_up: signal = "VOLUME YẾU + GIÁ TĂNG → Dễ đảo chiều ⚠️"
    elif vol_ratio < 0.7 and not price_up: signal = "VOLUME YẾU + GIÁ GIẢM → Giảm kiệt lực 🟡"
    else: signal = "BÌNH THƯỜNG 😐"

    return {
        "latest_volume": int(latest_vol),
        "projected_volume": int(projected_vol),
        "avg_volume_20": int(avg_vol),
        "volume_ratio": vol_ratio,
        "signal": signal
    }

def find_support_resistance(closes: list, highs: list, lows: list, lookback: int = 30) -> dict:
    if len(closes) < lookback: return {"error": "Thiếu dữ liệu"}
    latest = closes[-1]
    sr_levels = {"support": min(lows[-lookback:]), "resistance": max(highs[-lookback:])}
    return sr_levels

# ── LOGIC MỚI BỔ SUNG THEO SYSTEM DESIGN ──────────────────────────────────────────

def detect_market_regime(closes: list) -> str:
    """Xác định trạng thái (regime) của cổ phiếu: Uptrend / Downtrend / Ranging"""
    if len(closes) < 50:
         return "KHÔNG RÕ (Thiếu dữ liệu)"
         
    s = pd.Series(closes)
    ma20 = ta.sma(s, length=20).iloc[-1]
    ma50 = ta.sma(s, length=50).iloc[-1]
    latest = closes[-1]
    
    if latest > ma20 and ma20 > ma50:
        return "UPTREND MẠNH 🚀"
    elif latest < ma20 and ma20 < ma50:
        return "DOWNTREND 💥"
    else:
        return "RANGING (Đi ngang tích lũy) ⚖️"

def calculate_confluence(rsi_data, ma_data, macd_data, bb_data) -> dict:
    """Tính điểm đồng thuận của nhiều chỉ báo, phục vụ cho AI Agent quyết định"""
    score = 0
    signals = []
    
    if "quá bán" in rsi_data.get("signal", ""):
        score += 1
        signals.append("RSI Quá Bán (Hỗ trợ)")
    elif "quá mua" in rsi_data.get("signal", ""):
        score -= 1
        
    if "Xu hướng tăng" in ma_data.get("trend", ""):
        score += 1
        signals.append("Giá trên MA")
    else:
        score -= 1
        
    if "MUA mạnh" in macd_data.get("signal_text", "") or "mạnh lên" in macd_data.get("signal_text", "") and "tăng" in macd_data.get("signal_text", ""):
        score += 1
        signals.append("MACD Ủng hộ Tăng")
    elif "BÁN mạnh" in macd_data.get("signal_text", "") or "giảm tốc" in macd_data.get("signal_text", ""):
        score -= 1
        
    if "PHÁ BAND DƯỚI" in bb_data.get("signal_text", "") or "tích lũy" in bb_data.get("signal_text", ""):
        score += 1
        
    if score >= 3:
        status = "HIGH CONVICTION MUA 🟢"
    elif score <= -3:
        status = "HIGH CONVICTION BÁN 🔴"
    else:
        status = "MIXED (Trộn lẫn) 🟡"
        
    return {
        "score": score,
        "confluence_status": status,
        "buy_signals_detected": signals
    }
