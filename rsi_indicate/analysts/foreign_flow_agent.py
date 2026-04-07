"""
analysts/foreign_flow_agent.py — Foreign Flow Agent
Nhiệm vụ: Phân tích hành vi khối ngoại + room nước ngoài — đặc thù thị trường VN.

Input:  symbol (str)
Output: ForeignFlowReport (dict) với accumulation signal, room risk, net flow trend

Đây là agent đặc thù VN nhất — không có trong bất kỳ paper quốc tế nào.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import anthropic
from fetcher import fetch_foreign_flow, fetch_macro

MODEL = "claude-haiku-4-5-20251001"


def _interpret_foreign_flow(ff: dict, macro: dict) -> dict:
    """
    Rule-based interpretation — deterministic, không dùng LLM.
    Trả về structured brief để feed vào Claude.
    """
    room_pct    = ff.get("room_usage_pct")
    net_vol     = ff.get("net_foreign_volume", 0) or 0
    net_signal  = ff.get("net_signal", "TRUNG LẬP")
    room_signal = ff.get("room_signal", "N/A")

    # VN-Index đang giảm không?
    vnindex_change = macro.get("vnindex", {}).get("change_1d", 0) or 0
    market_down    = vnindex_change < -1.0

    # Accumulation signal: khối ngoại MUA RÒNG khi thị trường giảm = tín hiệu mạnh
    accumulation_signal = (net_vol > 0 and market_down)

    # Room risk levels
    if room_pct is not None:
        if room_pct >= 95:
            room_risk = "CRITICAL"
        elif room_pct >= 90:
            room_risk = "HIGH"
        elif room_pct >= 80:
            room_risk = "MEDIUM"
        else:
            room_risk = "LOW"
    else:
        room_risk = "UNKNOWN"

    return {
        "accumulation_signal": accumulation_signal,
        "room_risk":           room_risk,
        "net_flow_direction":  net_signal,
        "market_context":      f"VN-Index {'+' if vnindex_change >= 0 else ''}{vnindex_change:.2f}% hôm nay",
    }


def run(symbol: str) -> dict:
    """
    Chạy Foreign Flow Agent cho một mã cổ phiếu.
    Trả về ForeignFlowReport — dict JSON chuẩn.
    """
    symbol = symbol.upper()
    print("\n" + "="*60)
    print(f"[FOREIGN FLOW AGENT] Phân tích khối ngoại: {symbol}")
    print("="*60)

    # ── Lấy dữ liệu ──────────────────────────────────────────────────────────
    ff    = fetch_foreign_flow(symbol)
    macro = fetch_macro()

    if "error" in ff:
        print(f"  Lỗi lấy foreign flow: {ff['error']}")
        return {"symbol": symbol, "error": ff["error"], "skipped": True}

    # ── Rule-based pre-interpretation ─────────────────────────────────────────
    interpretation = _interpret_foreign_flow(ff, macro)

    # ── Claude Haiku tổng hợp brief ───────────────────────────────────────────
    system = """Bạn là chuyên gia theo dõi HÀNH VI KHỐI NGOẠI trên thị trường Việt Nam.
Nhiệm vụ: Phân tích dữ liệu giao dịch khối ngoại và room nước ngoài, đưa ra nhận định về ý định của khối ngoại.
Đặc thù VN: Khối ngoại có ảnh hưởng rất lớn đến thanh khoản và xu hướng ngắn hạn.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    vnindex_change = macro.get("vnindex", {}).get("change_1d", 0)

    user = f"""Mã: {symbol}

Dữ liệu khối ngoại phiên hôm nay:
- Mua ròng/Bán ròng: {ff.get('net_signal')} ({ff.get('net_foreign_volume', 'N/A')} cp)
- Mua: {ff.get('foreign_buy_volume', 'N/A')} cp | Bán: {ff.get('foreign_sell_volume', 'N/A')} cp
- Net value: {ff.get('net_foreign_value', 'N/A')} VND

Room nước ngoài:
- Tỷ lệ sở hữu hiện tại: {ff.get('holding_ratio_pct', 'N/A')}% / tối đa {ff.get('max_holding_ratio_pct', 'N/A')}%
- Room còn lại: {ff.get('current_room', 'N/A')} cp
- Mức độ rủi ro room: {ff.get('room_signal')}

Bối cảnh thị trường:
- VN-Index hôm nay: {'+' if vnindex_change >= 0 else ''}{vnindex_change}%
- Accumulation signal (ngoại mua khi thị trường giảm): {'CÓ — tín hiệu MẠNH' if interpretation['accumulation_signal'] else 'KHÔNG'}

Trả về JSON:
{{
  "symbol": "{symbol}",
  "net_flow": "MUA RÒNG/BÁN RÒNG/TRUNG LẬP",
  "net_volume": {ff.get('net_foreign_volume', 0)},
  "room_usage_pct": {ff.get('room_usage_pct', 0)},
  "room_risk": "{interpretation['room_risk']}",
  "accumulation_signal": {'true' if interpretation['accumulation_signal'] else 'false'},
  "foreign_intent": "TÍCH LŨY/PHÂN PHỐI/TRUNG LẬP/KHÔNG_RÕ",
  "key_observation": "nhận xét ngắn 1-2 câu về hành vi khối ngoại",
  "short_term_impact": "TÍCH CỰC/TIÊU CỰC/TRUNG LẬP",
  "warning": "cảnh báo đặc biệt nếu có (room trap, dump risk...) hoặc null"
}}"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}]
    )

    raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    try:
        start  = raw.find("{")
        end    = raw.rfind("}") + 1
        report = json.loads(raw[start:end])
    except Exception:
        report = {
            "symbol":           symbol,
            "net_flow":         ff.get("net_signal", "TRUNG LẬP"),
            "room_usage_pct":   ff.get("room_usage_pct"),
            "room_risk":        interpretation["room_risk"],
            "accumulation_signal": interpretation["accumulation_signal"],
            "key_observation":  raw[:200],
            "raw":              True,
        }

    # Đính kèm raw data để risk_manager dùng
    report["raw_ff"] = {
        "room_usage_pct":   ff.get("room_usage_pct"),
        "net_foreign_volume": ff.get("net_foreign_volume"),
        "net_signal":       ff.get("net_signal"),
    }

    _print_ff(report)
    return report


def _print_ff(r: dict):
    net   = r.get("net_flow", "?")
    room  = r.get("room_usage_pct")
    risk  = r.get("room_risk", "?")
    icon  = {"MUA RÒNG": "🟢", "BÁN RÒNG": "🔴", "TRUNG LẬP": "🟡"}.get(net, "⚪")
    r_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk, "⚪")
    print(f"\n  {icon} Khối ngoại: {net}  |  {r_icon} Room: {room}% ({risk})")
    if r.get("accumulation_signal"):
        print("  ✨ ACCUMULATION SIGNAL: Khối ngoại mua khi thị trường giảm — tín hiệu mạnh")
    if r.get("warning"):
        print(f"  ⚠️  {r.get('warning')}")
    print(f"  Ý định: {r.get('foreign_intent', '?')}  |  Tác động: {r.get('short_term_impact', '?')}")
    print(f"  Nhận xét: {r.get('key_observation', '')}")
    print("="*60)
