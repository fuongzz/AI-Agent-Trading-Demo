import anthropic
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Patch pandas compatibility: applymap → map (pandas >= 2.0)
try:
    import pandas as pd
    if not hasattr(pd.DataFrame, "applymap"):
        pd.DataFrame.applymap = pd.DataFrame.map
except ImportError:
    pass

# Lấy dữ liệu từ Vnstock

def fetch_ohlcv(symbol: str, days: int = 90) -> dict:
    """Lấy dữ liệu giá lịch sử OHLCV từ vnstock"""
    try:
        from vnstock import Vnstock

        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        df = stock.quote.history(start=start, end=end, interval="1D")

        if df is None or df.empty:
            return {"error": f"Không có dữ liệu cho mã {symbol}"}

        closes  = df["close"].tolist()
        highs   = df["high"].tolist()
        lows    = df["low"].tolist()
        volumes = df["volume"].tolist()
        latest  = df.iloc[-1]
        prev    = df.iloc[-2] if len(df) > 1 else df.iloc[-1]

        change  = round(float(latest["close"]) - float(prev["close"]), 2)
        pct     = round((change / float(prev["close"])) * 100, 2)

        return {
            "symbol":         symbol.upper(),
            "latest_price":   float(latest["close"]),
            "open":           float(latest["open"]),
            "high":           float(latest["high"]),
            "low":            float(latest["low"]),
            "volume":         int(latest["volume"]),
            "change":         change,
            "change_pct":     f"{pct}%",
            "closes":         closes,
            "highs":          highs,
            "lows":           lows,
            "volumes":        volumes,
            "total_sessions": len(closes),
            "date":           str(latest.name)[:10] if hasattr(latest, "name") else end,
            "source":         "Vnstock / VCI"
        }

    except ImportError:
        return {"error": "Chưa cài vnstock. Chạy: pip install vnstock"}
    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu: {str(e)}"}


def fetch_realtime(symbol: str) -> dict:
    """Lấy giá realtime"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        df = stock.quote.intraday(symbol=symbol.upper(), show_log=False)

        if df is None or df.empty:
            return {
                "note": "Không có dữ liệu realtime — có thể ngoài giờ giao dịch (9:00–15:00)",
                "symbol": symbol.upper()
            }

        latest = df.iloc[-1]
        return {
            "symbol":         symbol.upper(),
            "realtime_price": float(latest.get("price", latest.get("close", 0))),
            "volume":         int(latest.get("volume", 0)),
            "time":           str(latest.get("time", "")),
            "source":         "Vnstock intraday"
        }

    except Exception as e:
        return {"error": f"Lỗi realtime: {str(e)} — Thử ngoài giờ giao dịch"}


def fetch_company_info(symbol: str) -> dict:
    """Lấy thông tin cơ bản công ty"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        info  = stock.company.overview()

        if info is None or (hasattr(info, "empty") and info.empty):
            return {"error": "Không lấy được thông tin công ty"}

        row = info.iloc[0] if hasattr(info, "iloc") else info
        return {
            "symbol":    symbol.upper(),
            "company":   str(row.get("short_name", row.get("company_name", "N/A"))),
            "industry":  str(row.get("industry_name", row.get("sector", "N/A"))),
            "exchange":  str(row.get("exchange", "N/A")),
            "source":    "Vnstock company info"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy thông tin công ty: {str(e)}"}


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
    """Tính MACD (Moving Average Convergence Divergence)"""
    min_required = slow + signal_period
    if len(prices) < min_required:
        return {"error": f"Cần ít nhất {min_required} phiên để tính MACD({fast},{slow},{signal_period}), hiện có {len(prices)}"}

    def ema(data: list, period: int) -> list:
        k = 2 / (period + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    fast_ema  = ema(prices, fast)
    slow_ema  = ema(prices, slow)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]

    # Bỏ các giá trị đầu chưa ổn định, chỉ lấy từ index slow-1 trở đi
    macd_stable   = macd_line[slow - 1:]
    signal_line   = ema(macd_stable, signal_period)
    histogram     = [m - s for m, s in zip(macd_stable, signal_line)]

    latest_macd   = round(macd_stable[-1], 4)
    latest_signal = round(signal_line[-1], 4)
    latest_hist   = round(histogram[-1], 4)
    prev_hist     = round(histogram[-2], 4) if len(histogram) >= 2 else 0

    # Xác định tín hiệu
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
        "macd":        latest_macd,
        "signal":      latest_signal,
        "histogram":   latest_hist,
        "signal_text": signal_text,
        "fast":        fast,
        "slow":        slow,
        "signal_period": signal_period
    }


def calculate_atr(highs: list, lows: list, closes: list, period: int = 14) -> dict:
    """Tính Average True Range (ATR) — đo biến động thực tế của thị trường"""
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên để tính ATR"}

    true_ranges = []
    for i in range(1, len(closes)):
        hl   = highs[i] - lows[i]
        hpc  = abs(highs[i] - closes[i - 1])
        lpc  = abs(lows[i]  - closes[i - 1])
        true_ranges.append(max(hl, hpc, lpc))

    atr    = round(sum(true_ranges[-period:]) / period, 2)
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

    # Gợi ý SL/TP dựa trên ATR
    sl_1x = round(latest - 1.5 * atr, 2)
    tp_2x = round(latest + 2.0 * atr, 2)

    return {
        "atr":            atr,
        "atr_pct":        f"{atr_pct}%",
        "latest_price":   latest,
        "volatility":     volatility,
        "sl_suggestion":  sl_1x,   # Dừng lỗ gợi ý: 1.5×ATR bên dưới
        "tp_suggestion":  tp_2x,   # Chốt lời gợi ý: 2×ATR bên trên
        "period":         period
    }


def analyze_volume(closes: list, volumes: list, period: int = 20) -> dict:
    """Phân tích khối lượng giao dịch — xác nhận xu hướng giá"""
    if len(volumes) < period:
        return {"error": f"Cần ít nhất {period} phiên để phân tích khối lượng"}

    avg_vol   = sum(volumes[-period:]) / period
    latest_vol = volumes[-1]
    vol_ratio  = round(latest_vol / avg_vol, 2) if avg_vol > 0 else 0

    # Xu hướng giá: so sánh 5 phiên gần nhất
    price_up = closes[-1] > closes[-5] if len(closes) >= 5 else None

    # Phân loại tín hiệu kết hợp giá-khối lượng
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

    # Kiểm tra volume bất thường 3 phiên gần nhất
    recent_avg = sum(volumes[-period:-3]) / (period - 3) if period > 3 else avg_vol
    spike_sessions = [i for i in range(-3, 0) if volumes[i] > 2.0 * recent_avg]

    return {
        "latest_volume":    int(latest_vol),
        "avg_volume_20":    int(avg_vol),
        "volume_ratio":     vol_ratio,
        "signal":           signal,
        "volume_spike":     len(spike_sessions) > 0,
        "spike_note":       f"Có {len(spike_sessions)} phiên đột biến volume trong 3 phiên gần nhất" if spike_sessions else "Không có đột biến volume"
    }


def find_support_resistance(closes: list, highs: list, lows: list, lookback: int = 30) -> dict:
    """Xác định vùng hỗ trợ và kháng cự dựa trên giá pivot"""
    if len(closes) < lookback:
        return {"error": f"Cần ít nhất {lookback} phiên để tìm S/R"}

    recent_highs  = highs[-lookback:]
    recent_lows   = lows[-lookback:]
    latest        = closes[-1]

    # Tìm các điểm pivot high (kháng cự) và pivot low (hỗ trợ)
    # Pivot high: đỉnh cục bộ (cao hơn 2 phiên trước và 2 phiên sau)
    resistance_levels = []
    support_levels    = []

    for i in range(2, len(recent_highs) - 2):
        if recent_highs[i] > max(recent_highs[i-2:i]) and recent_highs[i] > max(recent_highs[i+1:i+3]):
            resistance_levels.append(round(recent_highs[i], 2))

    for i in range(2, len(recent_lows) - 2):
        if recent_lows[i] < min(recent_lows[i-2:i]) and recent_lows[i] < min(recent_lows[i+1:i+3]):
            support_levels.append(round(recent_lows[i], 2))

    # Lấy mức gần giá hiện tại nhất
    resistances_above = sorted([r for r in resistance_levels if r > latest])
    supports_below    = sorted([s for s in support_levels   if s < latest], reverse=True)

    # Fallback: dùng high/low của vùng lookback nếu không đủ pivot
    if not resistances_above:
        resistances_above = [round(max(recent_highs), 2)]
    if not supports_below:
        supports_below = [round(min(recent_lows), 2)]

    nearest_resistance = resistances_above[0]
    nearest_support    = supports_below[0]

    dist_to_resist = round((nearest_resistance - latest) / latest * 100, 2)
    dist_to_support = round((latest - nearest_support) / latest * 100, 2)

    if dist_to_resist < 2.0:
        zone_signal = f"GIÁ SÁT KHÁNG CỰ ({nearest_resistance}) — Rủi ro bị chặn, cân nhắc chốt lời ⚠️"
    elif dist_to_support < 2.0:
        zone_signal = f"GIÁ SÁT HỖ TRỢ ({nearest_support}) — Vùng cầu mạnh, tiềm năng bounce 🟢"
    elif dist_to_resist < dist_to_support:
        zone_signal = f"Gần kháng cự hơn (+{dist_to_resist}%) — Upside hạn chế 🟡"
    else:
        zone_signal = f"Gần hỗ trợ hơn (-{dist_to_support}%) — Vùng an toàn để xem xét mua 🟢"

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


def calculate_bollinger(prices: list, period: int = 20, num_std: float = 2.0) -> dict:
    """Tính Bollinger Bands"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên, hiện có {len(prices)}"}

    recent  = prices[-period:]
    middle  = sum(recent) / period
    std     = (sum((p - middle) ** 2 for p in recent) / period) ** 0.5

    upper   = round(middle + num_std * std, 2)
    lower   = round(middle - num_std * std, 2)
    middle  = round(middle, 2)
    latest  = prices[-1]

    # %B: vị trí giá trong dải band (0% = band dưới, 100% = band trên)
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
        "upper":       upper,
        "middle":      middle,
        "lower":       lower,
        "latest_price": latest,
        "percent_b":   percent_b,
        "bandwidth":   bandwidth,
        "signal_text": signal_text,
        "period":      period
    }


# Định nghĩa Tools

TOOLS = [
    {
        "name": "get_ohlcv",
        "description": "Lấy dữ liệu giá cổ phiếu VN theo phiên (OHLCV) qua Vnstock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Mã cổ phiếu, VD: VNM, HPG, FPT, MSN, VIC"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_realtime_price",
        "description": "Lấy giá realtime trong giờ giao dịch (9:00–15:00)",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_company_info",
        "description": "Lấy thông tin cơ bản công ty: tên, ngành, sàn giao dịch",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "calculate_rsi",
        "description": "Tính chỉ số RSI từ danh sách giá đóng cửa",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices": {"type": "array", "items": {"type": "number"}},
                "period": {"type": "integer", "default": 14}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_moving_average",
        "description": "Tính đường trung bình động MA",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices": {"type": "array", "items": {"type": "number"}},
                "period": {"type": "integer"}
            },
            "required": ["prices", "period"]
        }
    },
    {
        "name": "calculate_macd",
        "description": "Tính MACD (Moving Average Convergence Divergence). Cần ít nhất 35 phiên giá. Trả về macd, signal, histogram và tín hiệu giao cắt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices":        {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá đóng cửa, cần ít nhất 35 phiên"},
                "fast":          {"type": "integer", "description": "EMA nhanh, mặc định 12"},
                "slow":          {"type": "integer", "description": "EMA chậm, mặc định 26"},
                "signal_period": {"type": "integer", "description": "Signal line EMA, mặc định 9"}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_bollinger",
        "description": "Tính Bollinger Bands (20 phiên, 2 độ lệch chuẩn). Trả về band trên/giữa/dưới, %B và tín hiệu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices":  {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá đóng cửa, cần ít nhất 20 phiên"},
                "period":  {"type": "integer", "description": "Số phiên tính MA, mặc định 20"},
                "num_std": {"type": "number",  "description": "Số độ lệch chuẩn, mặc định 2.0"}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_atr",
        "description": "Tính Average True Range (ATR) — đo biến động thực tế, gợi ý mức SL/TP dựa trên ATR. Cần highs, lows, closes từ get_ohlcv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "highs":  {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá cao nhất mỗi phiên"},
                "lows":   {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá thấp nhất mỗi phiên"},
                "closes": {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá đóng cửa"},
                "period": {"type": "integer", "description": "Số phiên tính ATR, mặc định 14"}
            },
            "required": ["highs", "lows", "closes"]
        }
    },
    {
        "name": "analyze_volume",
        "description": "Phân tích khối lượng giao dịch — xác nhận xu hướng giá, phát hiện đột biến volume. Cần closes và volumes từ get_ohlcv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "closes":  {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá đóng cửa"},
                "volumes": {"type": "array", "items": {"type": "number"}, "description": "Danh sách khối lượng giao dịch"},
                "period":  {"type": "integer", "description": "Số phiên tính khối lượng TB, mặc định 20"}
            },
            "required": ["closes", "volumes"]
        }
    },
    {
        "name": "find_support_resistance",
        "description": "Xác định vùng hỗ trợ (support) và kháng cự (resistance) gần giá hiện tại nhất từ các điểm pivot. Cần closes, highs, lows từ get_ohlcv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "closes":   {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá đóng cửa"},
                "highs":    {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá cao nhất mỗi phiên"},
                "lows":     {"type": "array", "items": {"type": "number"}, "description": "Danh sách giá thấp nhất mỗi phiên"},
                "lookback": {"type": "integer", "description": "Số phiên nhìn lại để tìm S/R, mặc định 30"}
            },
            "required": ["closes", "highs", "lows"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    print(f"\n  🔧 Tool: [{name}]  →  {json.dumps(inputs, ensure_ascii=False)}")

    if name == "get_ohlcv":
        result = fetch_ohlcv(**inputs)
    elif name == "get_realtime_price":
        result = fetch_realtime(**inputs)
    elif name == "get_company_info":
        result = fetch_company_info(**inputs)
    elif name == "calculate_rsi":
        result = calculate_rsi(**inputs)
    elif name == "calculate_moving_average":
        result = calculate_moving_average(**inputs)
    elif name == "calculate_macd":
        result = calculate_macd(**inputs)
    elif name == "calculate_bollinger":
        result = calculate_bollinger(**inputs)
    elif name == "calculate_atr":
        result = calculate_atr(**inputs)
    elif name == "analyze_volume":
        result = analyze_volume(**inputs)
    elif name == "find_support_resistance":
        result = find_support_resistance(**inputs)
    else:
        result = {"error": f"Tool '{name}' không tồn tại"}

    print(f"     ✅ {json.dumps(result, ensure_ascii=False)[:200]}...")
    return json.dumps(result, ensure_ascii=False)



# Agent Loop


def run_agent(question: str):
    client = anthropic.Anthropic()

    print("\n" + "="*60)
    print(f"👤 {question}")
    print("="*60)

    messages = [{"role": "user", "content": question}]
    system = """Bạn là AI Agent phân tích cổ phiếu chuyên nghiệp, dùng dữ liệu thực từ Vnstock.
Khi phân tích một mã cổ phiếu, thực hiện đầy đủ theo thứ tự sau:
1. Lấy thông tin công ty (get_company_info)
2. Lấy dữ liệu OHLCV — lưu lại các field "closes", "highs", "lows", "volumes" (get_ohlcv)
3. Thử lấy giá realtime (get_realtime_price)
4. Tính RSI 14 phiên từ "closes" (calculate_rsi)
5. Tính MA5 và MA20 từ "closes" (calculate_moving_average, gọi 2 lần)
6. Tính MACD từ "closes" — cần ít nhất 35 phiên (calculate_macd)
7. Tính Bollinger Bands từ "closes" (calculate_bollinger)
8. Tính ATR từ "highs", "lows", "closes" — đo biến động và gợi ý SL/TP (calculate_atr)
9. Phân tích khối lượng từ "closes" và "volumes" — xác nhận xu hướng (analyze_volume)
10. Tìm vùng hỗ trợ/kháng cự từ "closes", "highs", "lows" (find_support_resistance)
11. Tổng hợp phân tích kỹ thuật đầy đủ bằng tiếng Việt gồm:
   - Tên công ty, ngành, sàn
   - Giá hiện tại, thay đổi so với hôm qua
   - RSI: mức và ý nghĩa
   - MA5 vs MA20: golden/death cross, xu hướng
   - MACD: tín hiệu momentum, giao cắt
   - Bollinger Bands: giá ở vùng nào, %B, bandwidth
   - ATR: mức biến động, gợi ý SL/TP cụ thể (giá tuyệt đối)
   - Khối lượng: so với TB 20 phiên, tín hiệu xác nhận xu hướng
   - Hỗ trợ/Kháng cự: vùng S/R gần nhất, khoảng cách %
   - KHUYẾN NGHỊ: Mua/Bán/Chờ, điểm vào, SL, TP, lý do kỹ thuật tổng hợp"""

    step = 1
    while True:
        print(f"\nAgent suy nghĩ... (bước {step})")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            step += 1

        elif response.stop_reason == "end_turn":
            answer = "".join(b.text for b in response.content if hasattr(b, "text"))
            print("\n" + "="*60)
            print("KẾT QUẢ PHÂN TÍCH:")
            print("="*60)
            print(answer)
            print("="*60)
            break
        else:
            print(f"⚠️ Stop reason: {response.stop_reason}")
            break



# Run


if __name__ == "__main__":
    print("""
DEMO: AI AGENT - Phân tích mã cổ phiếu                        
Nhập bất kỳ mã HOSE/HNX: VNM, HPG, FPT, VIC, MSN...     
Agent sẽ tự động lấy dữ liệu thực, tính RSI, MA và đưa ra nhận định kỹ thuật.
    """)

    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    run_agent(
        f"Phân tích kỹ thuật cổ phiếu {symbol}. "
        f"Giá hiện tại bao nhiêu? RSI đang ở đâu? Xu hướng ngắn hạn thế nào?"
    )