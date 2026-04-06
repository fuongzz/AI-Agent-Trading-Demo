"""
screener.py — Phần 3: Domain Knowledge Screening
Screener tự động quét 100 cổ xuống 10-15 mã thay vì bắt AI xử lý hết gây tốn tiền.
"""

from fetcher import fetch_ohlcv
from indicators import detect_market_regime

def rule_accumulation(prices: list, volumes: list) -> bool:
    """
    Mẫu hình đặc thù VN: Tích lũy biên độ hẹp kèm volume cạn (rũ bỏ nhỏ lẻ).
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
    
    if avg_vol_last_10 >= avg_vol_first_10 * 0.8:
        return False
        
    return True

def run_quick_screener(symbols_list: list) -> list:
    """
    Quét list cổ phiếu và chỉ trả về những cổ phiếu lọt qua vòng sơ loại.
    VD: symbols_list là ['VNM', 'HPG', 'SSI', ...]
    """
    passed = []
    
    for sym in symbols_list:
        data = fetch_ohlcv(sym, days=30)
        if "error" in data:
            continue
            
        prices = data.get("closes", [])
        volumes = data.get("volumes", [])
        
        is_accum_zone = rule_accumulation(prices, volumes)
        regime = detect_market_regime(prices)
        
        if is_accum_zone and "RANGING" in regime:
            passed.append({
                "symbol": sym,
                "reason": "Mô hình Nền giá hẹp + Volume xẹp"
            })
            
    return passed
