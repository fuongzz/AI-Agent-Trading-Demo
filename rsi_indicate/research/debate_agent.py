"""
research/debate_agent.py — Tầng II: Bull vs Bear Debate
Nhiệm vụ: Hai agent đọc PTKTReport, tranh luận đa chiều, tổng hợp DebateSummary.

Luồng:
  PTKTReport → [Bull Agent] → bull_view (JSON)
             → [Bear Agent] → bear_view (JSON)
             → [Synthesizer] → DebateSummary (JSON)

Mỗi agent là một lần gọi Claude độc lập với system prompt và vai trò khác nhau.
Đây là cốt lõi của cơ chế "debate" từ TradingAgents paper.
"""

import json
import anthropic

MODEL = "claude-haiku-4-5-20251001"


def _call_claude(system: str, user: str, max_tokens: int = 600) -> str:
    """Helper: gọi Claude 1 lần với system + user prompt."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return response.content[0].text.strip()


def _run_bull(ptkt_report: dict) -> dict:
    """
    Bull Agent: lập luận tại sao nên MUA.
    Chỉ nhìn thấy dữ liệu kỹ thuật — không biết Bear nghĩ gì.
    """
    print("\n  [BULL AGENT] Đang lập luận...")

    system = """Bạn là chuyên gia phân tích CỔ PHẦN TĂNG TRƯỞNG (Bull Analyst).
Nhiệm vụ: Dựa trên dữ liệu kỹ thuật, tìm và lập luận các lý do TÍCH CỰC để MUA cổ phiếu.
Hãy tìm các tín hiệu hỗ trợ xu hướng tăng, vùng tích lũy, momentum phục hồi.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    user = f"""Dữ liệu kỹ thuật cổ phiếu:
{json.dumps(ptkt_report.get("signals", {}), ensure_ascii=False, indent=2)}

Giá hiện tại: {ptkt_report.get("price", {}).get("latest")}
Hỗ trợ gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("support")}
Kháng cự gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("resistance")}

Trả về JSON theo schema:
{{
  "stance": "BULL",
  "score": 0-100,
  "top_reasons": ["lý do 1", "lý do 2", "lý do 3"],
  "entry_suggestion": 0.0,
  "tp_target": 0.0,
  "main_risk": "rủi ro chính nếu luận điểm sai"
}}"""

    raw = _call_claude(system, user).replace("```json", "").replace("```", "").strip()
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"stance": "BULL", "score": 50, "top_reasons": [raw[:200]], "raw": True}


def _run_bear(ptkt_report: dict) -> dict:
    """
    Bear Agent: lập luận tại sao nên BÁN hoặc TRÁNH.
    Chạy độc lập — không biết Bull đã nói gì.
    """
    print("  [BEAR AGENT] Đang lập luận...")

    system = """Bạn là chuyên gia phân tích RỦI RO (Bear Analyst).
Nhiệm vụ: Dựa trên dữ liệu kỹ thuật, tìm và lập luận các lý do TIÊU CỰC, cảnh báo rủi ro.
Hãy tìm các tín hiệu yếu, divergence, vùng kháng cự mạnh, khả năng đảo chiều giảm.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    user = f"""Dữ liệu kỹ thuật cổ phiếu:
{json.dumps(ptkt_report.get("signals", {}), ensure_ascii=False, indent=2)}

Giá hiện tại: {ptkt_report.get("price", {}).get("latest")}
Hỗ trợ gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("support")}
Kháng cự gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("resistance")}

Trả về JSON theo schema:
{{
  "stance": "BEAR",
  "score": 0-100,
  "top_risks": ["rủi ro 1", "rủi ro 2", "rủi ro 3"],
  "sl_suggestion": 0.0,
  "downside_target": 0.0,
  "main_bull_flaw": "điểm yếu lớn nhất trong luận điểm tăng"
}}"""

    raw = _call_claude(system, user).replace("```json", "").replace("```", "").strip()
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"stance": "BEAR", "score": 50, "top_risks": [raw[:200]], "raw": True}


def _synthesize(ptkt_report: dict, bull: dict, bear: dict) -> dict:
    """
    Synthesizer: đọc cả 2 góc nhìn, tổng hợp thành DebateSummary trung lập.
    Không thiên về bên nào — chỉ cân bằng và kết luận độ thuyết phục.
    """
    print("  [SYNTHESIZER] Tổng hợp debate...")

    system = """Bạn là trọng tài phân tích trung lập (Debate Synthesizer).
Nhiệm vụ: Đọc luận điểm Bull và Bear, đánh giá trọng lượng của từng bên, tổng hợp kết luận khách quan.
KHÔNG tự đưa ra khuyến nghị MUA/BÁN — chỉ tổng hợp sức mạnh của mỗi luận điểm.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    user = f"""Cổ phiếu: {ptkt_report.get("symbol")} — Giá: {ptkt_report.get("price", {}).get("latest")}

LUẬN ĐIỂM BULL:
{json.dumps(bull, ensure_ascii=False, indent=2)}

LUẬN ĐIỂM BEAR:
{json.dumps(bear, ensure_ascii=False, indent=2)}

Trả về JSON theo schema:
{{
  "bull_score": 0-100,
  "bear_score": 0-100,
  "dominant_side": "BULL/BEAR/NEUTRAL",
  "key_agreement": "điểm 2 bên đồng ý",
  "key_disagreement": "điểm tranh cãi chính",
  "bull_strongest_point": "...",
  "bear_strongest_point": "...",
  "market_context": "tóm tắt bức tranh tổng thể 1-2 câu",
  "uncertainty_level": "THẤP/TRUNG BÌNH/CAO"
}}"""

    raw = _call_claude(system, user, max_tokens=700).replace("```json", "").replace("```", "").strip()
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {"dominant_side": "NEUTRAL", "raw": raw[:300]}


def run(ptkt_report: dict) -> dict:
    """
    Chạy toàn bộ Debate: Bull → Bear → Synthesize.
    Trả về DebateSummary để Trader Agent đọc.
    """
    symbol = ptkt_report.get("symbol", "N/A")
    print("\n" + "="*60)
    print(f"[DEBATE AGENT] Bull vs Bear: {symbol}")
    print("="*60)

    bull    = _run_bull(ptkt_report)
    bear    = _run_bear(ptkt_report)
    summary = _synthesize(ptkt_report, bull, bear)

    print(f"\n  Bull score: {bull.get('score', '?')} | Bear score: {bear.get('score', '?')}")
    print(f"  Dominant: {summary.get('dominant_side', '?')} | Uncertainty: {summary.get('uncertainty_level', '?')}")

    return {
        "symbol":   symbol,
        "bull":     bull,
        "bear":     bear,
        "summary":  summary
    }
