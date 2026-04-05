"""
trader/trader_agent.py — Tầng III: Trader Agent
Nhiệm vụ: Đọc PTKTReport + DebateSummary → đưa ra quyết định giao dịch cuối cùng.

Trader Agent là người ra quyết định, không phải người tranh luận.
Input:  PTKTReport (số liệu kỹ thuật) + DebateSummary (góc nhìn Bull/Bear)
Output: TraderDecision — MUA/BÁN/CHỜ với entry, SL, TP, % NAV, lý do đầy đủ.
"""

import json
import anthropic

MODEL = "claude-haiku-4-5-20251001"


def run(ptkt_report: dict, debate: dict) -> dict:
    """
    Chạy Trader Agent.
    Trả về TraderDecision — quyết định giao dịch cuối cùng.
    """
    symbol = ptkt_report.get("symbol", "N/A")
    print("\n" + "="*60)
    print(f"[TRADER AGENT] Ra quyết định: {symbol}")
    print("="*60)

    client = anthropic.Anthropic()

    system = """Bạn là Trader chuyên nghiệp tại một quỹ đầu tư Việt Nam.
Nhiệm vụ: Đọc báo cáo kỹ thuật và kết quả tranh luận Bull/Bear, đưa ra quyết định giao dịch cuối cùng.

Nguyên tắc bắt buộc:
- Luôn đặt SL (stop loss) để bảo vệ vốn
- Tỷ lệ Risk/Reward tối thiểu 1:1.5
- % NAV: tối đa 20% cho 1 lệnh, phụ thuộc độ tin cậy
- Xem xét đặc thù VN: biên độ ±7%/phiên, thanh khoản, T+3
- Trả về JSON hợp lệ, KHÔNG có markdown"""

    user = f"""=== BÁO CÁO KỸ THUẬT (PTKT Agent) ===
Mã: {ptkt_report.get("symbol")} | Giá: {ptkt_report.get("price", {}).get("latest")} | Ngày: {ptkt_report.get("date")}
Công ty: {ptkt_report.get("company")} ({ptkt_report.get("exchange")})

Tín hiệu:
- RSI: {ptkt_report.get("signals", {}).get("rsi", {}).get("value")} → {ptkt_report.get("signals", {}).get("rsi", {}).get("signal")}
- MA: {ptkt_report.get("signals", {}).get("ma", {}).get("trend")} ({ptkt_report.get("signals", {}).get("ma", {}).get("cross")})
- MACD: {ptkt_report.get("signals", {}).get("macd", {}).get("signal_text")}
- Bollinger: {ptkt_report.get("signals", {}).get("bollinger", {}).get("signal_text")}
- Volume: {ptkt_report.get("signals", {}).get("volume", {}).get("signal")}
- ATR: {ptkt_report.get("signals", {}).get("atr", {}).get("volatility")}
- S/R: Hỗ trợ {ptkt_report.get("signals", {}).get("sr", {}).get("support")} | Kháng cự {ptkt_report.get("signals", {}).get("sr", {}).get("resistance")}

=== KẾT QUẢ TRANH LUẬN (Debate) ===
Bull score: {debate.get("bull", {}).get("score")} | Bear score: {debate.get("bear", {}).get("score")}
Dominant: {debate.get("summary", {}).get("dominant_side")} | Uncertainty: {debate.get("summary", {}).get("uncertainty_level")}

Luận điểm Bull mạnh nhất: {debate.get("summary", {}).get("bull_strongest_point")}
Luận điểm Bear mạnh nhất: {debate.get("summary", {}).get("bear_strongest_point")}
Bức tranh thị trường: {debate.get("summary", {}).get("market_context")}

=== YÊU CẦU ===
Đưa ra quyết định giao dịch. Trả về JSON:
{{
  "symbol": "...",
  "action": "MUA/BÁN/CHỜ",
  "entry": 0.0,
  "sl": 0.0,
  "tp": 0.0,
  "risk_reward": 0.0,
  "nav_pct": 0-20,
  "holding_period": "ngắn hạn (1-5 phiên)/trung hạn (1-4 tuần)/dài hạn",
  "confidence": "CAO/TRUNG BÌNH/THẤP",
  "reason": "lý do tổng hợp 2-3 câu kết hợp kỹ thuật + debate",
  "invalidation": "điều kiện nào khiến quyết định này sai (vd: giá phá SL, volume sụt)"
}}"""

    print("  Đang phân tích PTKTReport + DebateSummary...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": user}]
    )

    raw = response.content[0].text.strip()
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        decision = json.loads(raw[start:end])
    except Exception:
        decision = {"action": "CHỜ", "reason": raw[:300], "raw": True}

    _print_decision(decision)
    return decision


def _print_decision(d: dict):
    action = d.get("action", "?")
    icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "")
    print(f"\n{'='*60}")
    print(f"  QUYẾT ĐỊNH CUỐI: {icon} {action}  (Tin cậy: {d.get('confidence', '?')})")
    print(f"  Vào lệnh: {d.get('entry')}  |  SL: {d.get('sl')}  |  TP: {d.get('tp')}")
    print(f"  R/R: 1:{d.get('risk_reward')}  |  % NAV: {d.get('nav_pct')}%  |  Kỳ hạn: {d.get('holding_period')}")
    print(f"  Lý do: {d.get('reason')}")
    print(f"  Vô hiệu khi: {d.get('invalidation')}")
    print("="*60)
