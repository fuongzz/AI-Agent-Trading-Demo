"""
agent.py — Agent loops
- run_agent:      Full agent dùng tool_use (Sonnet)
- run_agent_lite: Tiết kiệm cost, output JSON, có cache (Haiku)
"""

import anthropic
import json
import os
from datetime import datetime

from fetcher import fetch_ohlcv, fetch_realtime, fetch_company_info
from indicators import (
    calculate_rsi, calculate_moving_average, calculate_macd,
    calculate_bollinger, calculate_atr, analyze_volume, find_support_resistance
)
from tools import TOOLS, execute_tool

# Thư mục cache và output
_BASE      = os.path.dirname(__file__)
CACHE_DIR  = os.path.join(_BASE, "cache")
OUTPUT_DIR = os.path.join(_BASE, "output")
os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Full Agent (Sonnet + tool_use) ────────────────────────────────────────────

def run_agent(question: str):
    client = anthropic.Anthropic()

    print("\n" + "="*60)
    print(f"👤 {question}")
    print("="*60)

    messages = [{"role": "user", "content": question}]
    system = """Bạn là AI Agent phân tích cổ phiếu chuyên nghiệp, dùng dữ liệu thực từ Vnstock.
Khi phân tích một mã cổ phiếu, thực hiện đầy đủ theo thứ tự sau:
1. Lấy thông tin công ty (get_company_info)
2. Lấy dữ liệu OHLCV (get_ohlcv)
3. Thử lấy giá realtime (get_realtime_price)
4. Tính RSI 14 phiên (calculate_rsi)
5. Tính MA5 và MA20 (calculate_moving_average, gọi 2 lần)
6. Tính MACD (calculate_macd)
7. Tính Bollinger Bands (calculate_bollinger)
8. Tính ATR (calculate_atr)
9. Phân tích khối lượng (analyze_volume)
10. Tìm hỗ trợ/kháng cự (find_support_resistance)
11. Tổng hợp phân tích đầy đủ bằng tiếng Việt với khuyến nghị MUA/BÁN/CHỜ, SL, TP."""

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
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})
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


# ── Lite Agent (Haiku + JSON output + cache) ──────────────────────────────────

def run_agent_lite(symbol: str) -> dict:
    """
    Tiết kiệm cost:
    - Cache indicators theo ngày → cùng ngày không fetch lại Vnstock
    - Claude output JSON thay vì text → giảm ~70% output tokens
    - Kết quả lưu ra output/{symbol}_{date}.json để tái sử dụng
    """
    client = anthropic.Anthropic()
    symbol = symbol.upper()
    today  = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"[LITE] Phân tích {symbol} — {today}")
    print("="*60)

    # Kiểm tra output cache
    output_path = os.path.join(OUTPUT_DIR, f"{symbol}_{today}.json")
    if os.path.exists(output_path):
        print(f"[Cache] Load kết quả từ {output_path}")
        with open(output_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)
        _print_analysis(analysis)
        return analysis

    # Kiểm tra indicator cache
    cache_path = os.path.join(CACHE_DIR, f"{symbol}_{today}_indicators.json")
    if os.path.exists(cache_path):
        print(f"[Cache] Load indicators từ {cache_path}")
        with open(cache_path, "r", encoding="utf-8") as f:
            indicators = json.load(f)
    else:
        print("Đang lấy dữ liệu từ Vnstock...")
        ohlcv   = fetch_ohlcv(symbol)
        company = fetch_company_info(symbol)
        rt      = fetch_realtime(symbol)

        if "error" in ohlcv:
            print(f"Lỗi: {ohlcv['error']}")
            return {}

        closes  = ohlcv["closes"]
        highs   = ohlcv["highs"]
        lows    = ohlcv["lows"]
        volumes = ohlcv["volumes"]

        indicators = {
            "company":  company,
            "price_info": {
                "symbol":     symbol,
                "date":       ohlcv["date"],
                "latest":     ohlcv["latest_price"],
                "open":       ohlcv["open"],
                "high":       ohlcv["high"],
                "low":        ohlcv["low"],
                "volume":     ohlcv["volume"],
                "change":     ohlcv["change"],
                "change_pct": ohlcv["change_pct"],
            },
            "realtime":  rt,
            "rsi":       calculate_rsi(closes),
            "ma5":       calculate_moving_average(closes, 5),
            "ma20":      calculate_moving_average(closes, 20),
            "macd":      calculate_macd(closes),
            "bollinger": calculate_bollinger(closes),
            "atr":       calculate_atr(highs, lows, closes),
            "volume":    analyze_volume(closes, volumes),
            "support_resistance": find_support_resistance(closes, highs, lows),
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(indicators, f, ensure_ascii=False, indent=2)
        print(f"[Cache] Indicators đã lưu → {cache_path}")

    # Gọi Claude 1 lần, yêu cầu output JSON
    prompt = f"""Dưới đây là dữ liệu phân tích kỹ thuật cổ phiếu {symbol}:

{json.dumps(indicators, ensure_ascii=False, indent=2)}

Hãy trả về JSON hợp lệ (KHÔNG có markdown, KHÔNG có text ngoài JSON) theo đúng schema sau:
{{
  "symbol": "...",
  "date": "...",
  "company": "tên công ty",
  "exchange": "HOSE/HNX",
  "industry": "ngành",
  "price": {{
    "latest": 0.0,
    "change": "...",
    "change_pct": "..."
  }},
  "signals": {{
    "rsi":       {{"value": 0.0, "signal": "OVERSOLD/NEUTRAL/OVERBOUGHT"}},
    "ma":        {{"ma5": 0.0, "ma20": 0.0, "trend": "TĂNG/GIẢM", "cross": "GOLDEN/DEATH/NONE"}},
    "macd":      {{"macd": 0.0, "signal": 0.0, "histogram": 0.0, "signal_text": "..."}},
    "bollinger": {{"upper": 0.0, "middle": 0.0, "lower": 0.0, "percent_b": 0.0, "signal_text": "..."}},
    "atr":       {{"value": 0.0, "volatility": "THẤP/TRUNG BÌNH/CAO/RẤT CAO"}},
    "volume":    {{"ratio": 0.0, "signal": "..."}},
    "sr":        {{"support": 0.0, "resistance": 0.0, "zone_signal": "..."}}
  }},
  "recommendation": {{
    "action":     "MUA/BÁN/CHỜ",
    "entry":      0.0,
    "sl":         0.0,
    "tp":         0.0,
    "confidence": "CAO/TRUNG BÌNH/THẤP",
    "reason":     "lý do ngắn gọn 1-2 câu"
  }}
}}"""

    print("Gửi cho Claude phân tích (JSON mode)...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        start    = raw.find("{")
        end      = raw.rfind("}") + 1
        analysis = json.loads(raw[start:end]) if start != -1 else {"raw": raw}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"[Output] Kết quả đã lưu → {output_path}")

    _append_history(symbol, today, analysis)

    _print_analysis(analysis)

    usage = response.usage
    print(f"\n[Tokens] Input: {usage.input_tokens} | Output: {usage.output_tokens}")

    return analysis


def _append_history(symbol: str, date: str, analysis: dict):
    """
    Ghi thêm kết quả phiên mới vào file history của mã cổ phiếu.
    output/VNM_history.json — mảng JSON, mỗi phần tử là 1 phiên.
    Không bao giờ overwrite dữ liệu cũ.
    """
    history_path = os.path.join(OUTPUT_DIR, f"{symbol}_history.json")

    # Load history hiện tại hoặc tạo mới
    if os.path.exists(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []

    # Kiểm tra phiên này đã có chưa (tránh duplicate)
    existing_dates = {entry.get("date") for entry in history}
    if date in existing_dates:
        return

    # Chỉ lưu các trường cần thiết vào history (không lưu toàn bộ để tiết kiệm dung lượng)
    snapshot = {
        "date":           date,
        "price":          analysis.get("price", {}),
        "signals": {
            "rsi":    analysis.get("signals", {}).get("rsi", {}),
            "ma":     analysis.get("signals", {}).get("ma", {}),
            "macd":   analysis.get("signals", {}).get("macd", {}).get("signal_text", ""),
            "volume": analysis.get("signals", {}).get("volume", {}),
        },
        "recommendation": analysis.get("recommendation", {}),
    }

    history.append(snapshot)
    history.sort(key=lambda x: x.get("date", ""))  # Giữ thứ tự theo ngày

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"[History] Đã thêm phiên {date} → {history_path} ({len(history)} phiên)")


# ── Hiển thị kết quả ──────────────────────────────────────────────────────────

def _print_analysis(a: dict):
    """In kết quả phân tích JSON ra console dạng dễ đọc."""
    if "raw" in a:
        print(a["raw"])
        return

    p  = a.get("price", {})
    s  = a.get("signals", {})
    r  = a.get("recommendation", {})
    sr = s.get("sr", {})

    print(f"\n{'='*60}")
    print(f"  {a.get('symbol')} — {a.get('company')} ({a.get('exchange')}, {a.get('industry')})")
    print(f"  Ngày: {a.get('date')}")
    print(f"{'─'*60}")
    print(f"  Giá:       {p.get('latest')}  ({p.get('change_pct')})")
    print(f"  RSI:       {s.get('rsi', {}).get('value')}  → {s.get('rsi', {}).get('signal')}")
    print(f"  MA5/MA20:  {s.get('ma', {}).get('ma5')} / {s.get('ma', {}).get('ma20')}  → {s.get('ma', {}).get('trend')} ({s.get('ma', {}).get('cross')})")
    print(f"  MACD:      {s.get('macd', {}).get('signal_text')}")
    print(f"  Bollinger: {s.get('bollinger', {}).get('signal_text')}")
    print(f"  Volume:    {s.get('volume', {}).get('ratio')}x TB20  → {s.get('volume', {}).get('signal')}")
    print(f"  ATR:       {s.get('atr', {}).get('volatility')}")
    print(f"  S/R:       Hỗ trợ {sr.get('support')} | Kháng cự {sr.get('resistance')}")
    print(f"{'─'*60}")
    action = r.get("action", "")
    icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "")
    print(f"  KHUYẾN NGHỊ: {icon} {action}  (Độ tin cậy: {r.get('confidence')})")
    print(f"  Vào lệnh:  {r.get('entry')}  |  SL: {r.get('sl')}  |  TP: {r.get('tp')}")
    print(f"  Lý do:     {r.get('reason')}")
    print(f"{'='*60}")
