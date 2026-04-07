"""
screener.py — Phần 3: Domain Knowledge Screening
Encode tư duy trader VN thành criteria định lượng.
Screener tự động quét 100 cổ xuống 10-15 mã thay vì bắt AI xử lý hết gây tốn tiền.

6 patterns đặc thù thị trường VN:
  1. Accumulation  — giá sideway + volume teo + phiên hấp thụ lực bán
  2. Real breakout  — volume >1.5x + thân nến to (không phải ATC spike)
  3. Distribution   — volume cao nhưng giá không tăng + bóng trên dài
  4. ATC manipulation — giá tăng mạnh chỉ ATC, không phải demand thật
  5. Foreign room trap — room >95%, khối ngoại bán ra = dump risk
  6. Margin call cascade — thị trường giảm >5%/tuần + giảm thẳng + vol spike
"""

from fetcher import fetch_ohlcv
from indicators import detect_market_regime


# ── Pattern 1: Accumulation ────────────────────────────────────────────────────

def rule_accumulation(prices: list, volumes: list) -> bool:
    """
    Tích lũy biên độ hẹp kèm volume cạn (rũ bỏ nhỏ lẻ).
    - Biên độ 20 phiên cực hẹp (<8%)
    - Volume trung bình 10 phiên sau thấp hơn 10 phiên đầu ít nhất 20%
    """
    if len(prices) < 20 or len(volumes) < 20:
        return False

    recent_prices = prices[-20:]
    amplitude = (max(recent_prices) - min(recent_prices)) / min(recent_prices) * 100
    if amplitude > 8.0:
        return False

    avg_vol_first_10 = sum(volumes[-20:-10]) / 10
    avg_vol_last_10  = sum(volumes[-10:]) / 10

    return avg_vol_last_10 < avg_vol_first_10 * 0.8


# ── Pattern 2: Real Breakout vs Fake Breakout ──────────────────────────────────

def rule_real_breakout(prices: list, volumes: list, highs: list) -> bool:
    """
    Breakout thật: giá vượt đỉnh 20 phiên + volume >1.5x TB20 + KHÔNG phải ATC spike.
    ATC spike: volume cuối phiên cao bất thường so với trung bình nội ngày — không detect được
    từ daily data, nên dùng proxy: giá đóng cửa phải cách đỉnh ngày <0.5% (thân nến to).
    """
    if len(prices) < 21 or len(volumes) < 21 or len(highs) < 21:
        return False

    latest_close = prices[-1]
    latest_high  = highs[-1]
    prev_high_20 = max(highs[-21:-1])  # Đỉnh 20 phiên trước

    # Điều kiện 1: Vượt đỉnh 20 phiên
    if latest_close <= prev_high_20:
        return False

    # Điều kiện 2: Volume > 1.5x TB20
    avg_vol_20 = sum(volumes[-21:-1]) / 20
    if volumes[-1] < avg_vol_20 * 1.5:
        return False

    # Điều kiện 3: Thân nến to (close gần high — không phải ATC dump)
    if latest_high > 0:
        candle_body_pct = (latest_close / latest_high) * 100
        if candle_body_pct < 98.0:  # Close < 98% của High → bóng trên dài → nghi ngờ
            return False

    return True


def rule_fake_breakout_risk(prices: list, volumes: list) -> bool:
    """
    Cảnh báo nguy cơ breakout giả: giá vượt đỉnh ngắn hạn nhưng volume yếu.
    - Giá tăng >3% trong 3 phiên gần nhất
    - Volume trung bình 3 phiên < 0.8x TB20 (breakout không có support volume)
    """
    if len(prices) < 23 or len(volumes) < 23:
        return False

    price_change_3d = (prices[-1] - prices[-4]) / prices[-4] * 100
    if price_change_3d < 3.0:
        return False

    avg_vol_20  = sum(volumes[-23:-3]) / 20
    avg_vol_3   = sum(volumes[-3:]) / 3
    return avg_vol_3 < avg_vol_20 * 0.8


# ── Pattern 3: Distribution ────────────────────────────────────────────────────

def rule_distribution(prices: list, volumes: list, highs: list) -> bool:
    """
    Phân phối đỉnh: volume cao nhưng giá không tăng + nhiều bóng trên dài.
    - Volume 5 phiên gần > 1.3x TB20
    - Giá không tăng (close[−1] <= close[−6])
    - Bóng trên trung bình > 1.5% (high - close)/close
    """
    if len(prices) < 25 or len(volumes) < 25 or len(highs) < 25:
        return False

    avg_vol_20   = sum(volumes[-25:-5]) / 20
    avg_vol_5    = sum(volumes[-5:]) / 5

    # Điều kiện 1: Volume cao
    if avg_vol_5 < avg_vol_20 * 1.3:
        return False

    # Điều kiện 2: Giá không tăng
    if prices[-1] > prices[-6]:
        return False

    # Điều kiện 3: Bóng trên dài (upper shadow)
    upper_shadows = []
    for i in range(-5, 0):
        if highs[i] > 0 and prices[i] > 0:
            shadow_pct = (highs[i] - prices[i]) / prices[i] * 100
            upper_shadows.append(shadow_pct)

    if not upper_shadows:
        return False

    avg_shadow = sum(upper_shadows) / len(upper_shadows)
    return avg_shadow > 1.5


# ── Pattern 4: ATC Manipulation ───────────────────────────────────────────────

def rule_atc_manipulation(prices: list, volumes: list) -> bool:
    """
    ATC manipulation proxy từ daily data:
    - Giá tăng mạnh >2% trong phiên (high-to-close thấp = tăng đột biến rồi xả)
    - Volume ngày đó cao (>1.5x TB20) nhưng 3 phiên tiếp theo volume sụt <0.7x
    Pattern: smart money bơm giá ATC để thoát hàng, nhỏ lẻ ôm đỉnh.
    """
    if len(prices) < 24 or len(volumes) < 24:
        return False

    # Kiểm tra phiên 4 ngày trước (t-4): giá tăng mạnh + volume cao
    spike_idx = -4
    price_change = (prices[spike_idx] - prices[spike_idx - 1]) / prices[spike_idx - 1] * 100
    if price_change < 2.0:
        return False

    avg_vol_20 = sum(volumes[-24:-4]) / 20
    if volumes[spike_idx] < avg_vol_20 * 1.5:
        return False

    # Kiểm tra 3 phiên sau: volume sụt (nhỏ lẻ không theo được)
    avg_vol_post3 = sum(volumes[-3:]) / 3
    return avg_vol_post3 < avg_vol_20 * 0.7


# ── Pattern 5: Foreign Room Trap ──────────────────────────────────────────────

def rule_foreign_room_trap(room_usage_pct: float) -> bool:
    """
    Room nước ngoài >95% → nguy cơ khối ngoại xả hàng (không mua vào được nữa).
    Trả về True = CÓ rủi ro.
    """
    if room_usage_pct is None:
        return False
    return room_usage_pct >= 95.0


# ── Pattern 6: Margin Call Cascade ────────────────────────────────────────────

def rule_margin_call_risk(prices: list) -> bool:
    """
    Thị trường giảm liên tục >5% trong 5 phiên + giảm thẳng (không có nhịp hồi).
    Trong môi trường này, các lệnh margin call có thể kéo mọi cổ xuống.
    """
    if len(prices) < 6:
        return False

    change_5d = (prices[-1] - prices[-6]) / prices[-6] * 100
    if change_5d > -5.0:
        return False

    # Kiểm tra giảm thẳng: không có ngày nào trong 5 phiên tăng >1%
    sustained_drop = True
    for i in range(-5, 0):
        day_change = (prices[i] - prices[i - 1]) / prices[i - 1] * 100
        if day_change > 1.0:
            sustained_drop = False
            break

    return sustained_drop


# ── Quick Pass: dùng trong orchestrator ───────────────────────────────────────

def quick_pass_single(symbol: str, foreign_room_pct: float = None) -> dict:
    """
    Kiểm tra nhanh 1 mã cổ phiếu — dùng để screener trong orchestrator.
    Trả về {"pass": bool, "reason": str, "score": int, "regime": str, "patterns": list}

    Scoring:
      +2 = Accumulation (tín hiệu mua mạnh)
      +1 = Real breakout (tín hiệu mua)
      -1 = Fake breakout risk / Distribution / ATC manipulation
      -2 = Foreign room trap / Margin call cascade (nguy hiểm)

    Threshold: pass nếu score >= -1 (không có tín hiệu nguy hiểm áp đảo).
    """
    data = fetch_ohlcv(symbol, days=60)
    if "error" in data:
        return {"pass": True, "reason": "Không lấy được dữ liệu — cho qua mặc định",
                "score": 0, "regime": "N/A", "patterns": []}

    prices  = data.get("closes", [])
    volumes = data.get("volumes", [])
    highs   = data.get("highs", [])
    lows    = data.get("lows", [])
    regime  = detect_market_regime(prices)

    score    = 0
    patterns = []

    # ── Tín hiệu tích cực ─────────────────────────────────────────────────────
    if rule_accumulation(prices, volumes):
        score += 2
        patterns.append("ACCUMULATION: Nền giá hẹp + volume xẹp")

    if rule_real_breakout(prices, volumes, highs):
        score += 1
        patterns.append("REAL BREAKOUT: Vượt đỉnh + volume xác nhận")

    # ── Cảnh báo rủi ro ───────────────────────────────────────────────────────
    if rule_fake_breakout_risk(prices, volumes):
        score -= 1
        patterns.append("FAKE BREAKOUT RISK: Giá tăng nhưng volume yếu")

    if rule_distribution(prices, volumes, highs):
        score -= 1
        patterns.append("DISTRIBUTION: Volume cao + giá không tăng + bóng trên")

    if rule_atc_manipulation(prices, volumes):
        score -= 1
        patterns.append("ATC MANIPULATION: Spike rồi xả, volume sụt sau đó")

    if rule_foreign_room_trap(foreign_room_pct):
        score -= 2
        patterns.append(f"FOREIGN ROOM TRAP: Room {foreign_room_pct:.0f}% — dump risk cao")

    if rule_margin_call_risk(prices):
        score -= 2
        patterns.append("MARGIN CALL CASCADE: Giảm thẳng >5% trong 5 phiên")

    passed  = score >= -1
    summary = " | ".join(patterns) if patterns else "Không có pattern đặc biệt"
    return {"pass": passed, "reason": summary, "score": score,
            "regime": regime, "patterns": patterns}


# ── Batch Screener: quét toàn bộ VN100 ────────────────────────────────────────

def run_quick_screener(symbols_list: list) -> list:
    """
    Quét list cổ phiếu và trả về những cổ phiếu lọt qua vòng sơ loại.
    Kèm theo score và patterns để người dùng review.
    """
    passed  = []
    skipped = []

    for sym in symbols_list:
        result = quick_pass_single(sym)
        if result["pass"]:
            passed.append({
                "symbol":   sym,
                "score":    result["score"],
                "regime":   result["regime"],
                "patterns": result["patterns"],
                "reason":   result["reason"],
            })
        else:
            skipped.append(sym)

    print(f"\n[Screener] {len(passed)}/{len(symbols_list)} mã lọt qua "
          f"| {len(skipped)} bị loại: {skipped}")
    return passed
