"""
indicators.py — Tính toán các chỉ báo kỹ thuật
RSI, MA, MACD, Bollinger Bands, ATR, Volume, Support/Resistance
"""

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


# ── Chỉ báo kỹ thuật ──────────────────────────────────────────────────────────

def calculate_rsi(prices: list, period: int = 14) -> dict:
    """Tính RSI"""
    if len(prices) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên, hiện có {len(prices)}"}

    gains, losses = [], []
    for i in range(1, len(prices)):
        chg = prices[i] - prices[i-1]
        gains.append(max(chg, 0))
        losses.append(abs(min(chg, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    rsi = 100 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    if rsi < 30:
        signal = "OVERSOLD (quá bán) → Có thể là cơ hội MUA"
    elif rsi > 70:
        signal = "OVERBOUGHT (quá mua) → Cân nhắc CHỐT LỜI"
    else:
        signal = "NEUTRAL (trung tính) → Chờ thêm tín hiệu"

    return {"rsi": rsi, "signal": signal, "period": period}


def calculate_moving_average(prices: list, period: int) -> dict:
    """Tính MA"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên"}

    ma     = round(sum(prices[-period:]) / period, 2)
    latest = prices[-1]
    trend  = "TRÊN MA → Xu hướng tăng ✅" if latest > ma else "DƯỚI MA → Xu hướng giảm ⚠️"

    return {"ma": ma, "latest_price": latest, "trend": trend, "period": period}


def calculate_macd(prices: list, fast: int = 12, slow: int = 26, signal_period: int = 9) -> dict:
    """Tính MACD"""
    min_required = slow + signal_period
    if len(prices) < min_required:
        return {"error": f"Cần ít nhất {min_required} phiên để tính MACD, hiện có {len(prices)}"}

    def ema(data: list, period: int) -> list:
        k = 2 / (period + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    fast_ema    = ema(prices, fast)
    slow_ema    = ema(prices, slow)
    macd_line   = [f - s for f, s in zip(fast_ema, slow_ema)]
    macd_stable = macd_line[slow - 1:]
    signal_line = ema(macd_stable, signal_period)
    histogram   = [m - s for m, s in zip(macd_stable, signal_line)]

    latest_macd   = round(macd_stable[-1], 4)
    latest_signal = round(signal_line[-1], 4)
    latest_hist   = round(histogram[-1], 4)
    prev_hist     = round(histogram[-2], 4) if len(histogram) >= 2 else 0

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
    """Tính Bollinger Bands"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên, hiện có {len(prices)}"}

    recent    = prices[-period:]
    middle    = sum(recent) / period
    std       = (sum((p - middle) ** 2 for p in recent) / period) ** 0.5
    upper     = round(middle + num_std * std, 2)
    lower     = round(middle - num_std * std, 2)
    middle    = round(middle, 2)
    latest    = prices[-1]
    percent_b = round((latest - lower) / (upper - lower) * 100, 2) if upper != lower else 50.0
    bandwidth = round((upper - lower) / middle * 100, 2)

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
    """Tính ATR — đo biến động thực tế, gợi ý SL/TP"""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên để tính ATR"}

    true_ranges = []
    for i in range(1, len(closes)):
        hl  = highs[i] - lows[i]
        hpc = abs(highs[i] - closes[i - 1])
        lpc = abs(lows[i]  - closes[i - 1])
        true_ranges.append(max(hl, hpc, lpc))

    atr     = round(sum(true_ranges[-period:]) / period, 2)
    latest  = closes[-1]
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


def analyze_volume(closes: list, volumes: list, period: int = 20) -> dict:
    """Phân tích khối lượng giao dịch — xác nhận xu hướng giá"""
    if len(volumes) < period:
        return {"error": f"Cần ít nhất {period} phiên để phân tích khối lượng"}

    avg_vol    = sum(volumes[-period:]) / period
    latest_vol = volumes[-1]

    progress      = get_session_progress()
    intraday_note = ""
    projected_vol = latest_vol
    if progress < 1.0:
        projected_vol = latest_vol / progress
        intraday_note = (
            f"⚠️ Phiên chưa kết thúc ({round(progress*100)}% thời gian đã qua). "
            f"Volume thực tế: {int(latest_vol):,} — Ước tính cả phiên: {int(projected_vol):,}."
        )

    vol_ratio = round(projected_vol / avg_vol, 2) if avg_vol > 0 else 0
    price_up  = closes[-1] > closes[-5] if len(closes) >= 5 else None

    if vol_ratio >= 1.5 and price_up:
        signal = "VOLUME TĂNG + GIÁ TĂNG → Xu hướng tăng được xác nhận mạnh 🟢"
    elif vol_ratio >= 1.5 and price_up is False:
        signal = "VOLUME TĂNG + GIÁ GIẢM → Áp lực bán lớn, xu hướng giảm mạnh 🔴"
    elif vol_ratio < 0.7 and price_up:
        signal = "VOLUME YẾU + GIÁ TĂNG → Tăng không có xác nhận, dễ đảo chiều ⚠️"
    elif vol_ratio < 0.7 and price_up is False:
        signal = "VOLUME YẾU + GIÁ GIẢM → Giảm kiệt lực, có thể sắp phục hồi 🟡"
    else:
        signal = "VOLUME BÌNH THƯỜNG → Không có tín hiệu đặc biệt 😐"

    recent_avg     = sum(volumes[-period:-3]) / (period - 3) if period > 3 else avg_vol
    spike_sessions = [i for i in range(-3, 0) if volumes[i] > 2.0 * recent_avg]

    return {
        "latest_volume":    int(latest_vol),
        "projected_volume": int(projected_vol),
        "avg_volume_20":    int(avg_vol),
        "volume_ratio":     vol_ratio,
        "signal":           signal,
        "volume_spike":     len(spike_sessions) > 0,
        "spike_note":       f"Có {len(spike_sessions)} phiên đột biến trong 3 phiên gần nhất" if spike_sessions else "Không có đột biến volume",
        "intraday_note":    intraday_note,
    }


def find_support_resistance(closes: list, highs: list, lows: list, lookback: int = 30) -> dict:
    """Xác định vùng hỗ trợ và kháng cự từ các điểm pivot"""
    if len(closes) < lookback:
        return {"error": f"Cần ít nhất {lookback} phiên để tìm S/R"}

    recent_highs      = highs[-lookback:]
    recent_lows       = lows[-lookback:]
    latest            = closes[-1]
    resistance_levels = []
    support_levels    = []

    for i in range(2, len(recent_highs) - 2):
        if recent_highs[i] > max(recent_highs[i-2:i]) and recent_highs[i] > max(recent_highs[i+1:i+3]):
            resistance_levels.append(round(recent_highs[i], 2))

    for i in range(2, len(recent_lows) - 2):
        if recent_lows[i] < min(recent_lows[i-2:i]) and recent_lows[i] < min(recent_lows[i+1:i+3]):
            support_levels.append(round(recent_lows[i], 2))

    resistances_above = sorted([r for r in resistance_levels if r > latest])
    supports_below    = sorted([s for s in support_levels   if s < latest], reverse=True)

    if not resistances_above:
        resistances_above = [round(max(recent_highs), 2)]
    if not supports_below:
        supports_below = [round(min(recent_lows), 2)]

    nearest_resistance = resistances_above[0]
    nearest_support    = supports_below[0]
    dist_to_resist     = round((nearest_resistance - latest) / latest * 100, 2)
    dist_to_support    = round((latest - nearest_support)   / latest * 100, 2)

    if dist_to_resist < 2.0:
        zone_signal = f"GIÁ SÁT KHÁNG CỰ ({nearest_resistance}) — Rủi ro bị chặn ⚠️"
    elif dist_to_support < 2.0:
        zone_signal = f"GIÁ SÁT HỖ TRỢ ({nearest_support}) — Tiềm năng bounce 🟢"
    elif dist_to_resist < dist_to_support:
        zone_signal = f"Gần kháng cự hơn (+{dist_to_resist}%) — Upside hạn chế 🟡"
    else:
        zone_signal = f"Gần hỗ trợ hơn (-{dist_to_support}%) — Vùng an toàn xem xét mua 🟢"

    return {
        "latest_price":       latest,
        "nearest_resistance": nearest_resistance,
        "nearest_support":    nearest_support,
        "dist_to_resistance": f"+{dist_to_resist}%",
        "dist_to_support":    f"-{dist_to_support}%",
        "all_resistances":    resistances_above[:3],
        "all_supports":       supports_below[:3],
        "zone_signal":        zone_signal
    }
