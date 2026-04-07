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

# System design: Bull/Bear debate + final synthesis → Sonnet (cần reasoning sâu)
# Rebuttal → Haiku (ngắn, nhanh)
MODEL_DEBATE = "claude-sonnet-4-6"
MODEL_REBUTTAL = "claude-haiku-4-5-20251001"


def _call_claude(system: str, user: str, max_tokens: int = 600,
                 model: str = None) -> str:
    """Helper: gọi Claude 1 lần với system + user prompt."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model or MODEL_DEBATE,
        max_tokens=max_tokens,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return response.content[0].text.strip()


def _run_bull(ptkt_report: dict, fa_report: dict = None, ff_report: dict = None) -> dict:
    """
    Bull Agent: lập luận tại sao nên MUA.
    Chỉ nhìn thấy dữ liệu kỹ thuật + FA — không biết Bear nghĩ gì.
    """
    print("\n  [BULL AGENT] Đang lập luận...")

    system = """Bạn là chuyên gia phân tích CỔ PHẦN TĂNG TRƯỞNG (Bull Analyst).
Nhiệm vụ: Dựa trên dữ liệu kỹ thuật và cơ bản, tìm và lập luận các lý do TÍCH CỰC để MUA cổ phiếu.
Hãy tìm các tín hiệu hỗ trợ xu hướng tăng, vùng tích lũy, momentum phục hồi, định giá hấp dẫn.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    fa_block = ""
    if fa_report and not fa_report.get("skipped"):
        fa_block = f"""
Dữ liệu cơ bản (FA):
- Định giá: {fa_report.get('valuation_verdict')} | Chất lượng LN: {fa_report.get('quality_score')}/100
- Triển vọng: {fa_report.get('growth_outlook')}
- Điểm mạnh: {'; '.join(fa_report.get('key_strengths', [])[:2])}
- Tóm tắt: {fa_report.get('fa_summary', '')}"""

    ff_block = ""
    if ff_report and not ff_report.get("skipped"):
        ff_block = f"""
Khối ngoại:
- Hành vi: {ff_report.get('net_flow')} | Room: {ff_report.get('room_usage_pct')}% ({ff_report.get('room_risk')})
- Ý định: {ff_report.get('foreign_intent')} | Accumulation: {'CÓ' if ff_report.get('accumulation_signal') else 'KHÔNG'}"""

    user = f"""Dữ liệu kỹ thuật cổ phiếu:
{json.dumps(ptkt_report.get("signals", {}), ensure_ascii=False, indent=2)}

Giá hiện tại: {ptkt_report.get("price", {}).get("latest")}
Hỗ trợ gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("support")}
Kháng cự gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("resistance")}
{fa_block}{ff_block}

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


def _run_bear(ptkt_report: dict, fa_report: dict = None, ff_report: dict = None) -> dict:
    """
    Bear Agent: lập luận tại sao nên BÁN hoặc TRÁNH.
    Chạy độc lập — không biết Bull đã nói gì.
    """
    print("  [BEAR AGENT] Đang lập luận...")

    system = """Bạn là chuyên gia phân tích RỦI RO (Bear Analyst).
Nhiệm vụ: Dựa trên dữ liệu kỹ thuật và cơ bản, tìm và lập luận các lý do TIÊU CỰC, cảnh báo rủi ro.
Hãy tìm các tín hiệu yếu, divergence, vùng kháng cự mạnh, khả năng đảo chiều giảm, rủi ro tài chính.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    fa_block = ""
    if fa_report and not fa_report.get("skipped"):
        fa_block = f"""
Dữ liệu cơ bản (FA):
- Định giá: {fa_report.get('valuation_verdict')} | Chất lượng LN: {fa_report.get('quality_score')}/100
- Rủi ro FA: {'; '.join(fa_report.get('key_risks', [])[:2])}
- Cảnh báo: {'; '.join(fa_report.get('anomaly_flags', [])[:2])}"""

    ff_block = ""
    if ff_report and not ff_report.get("skipped"):
        ff_block = f"""
Khối ngoại (rủi ro):
- Hành vi: {ff_report.get('net_flow')} | Room: {ff_report.get('room_usage_pct')}% ({ff_report.get('room_risk')})
- Cảnh báo: {ff_report.get('warning') or 'Không có'}"""

    user = f"""Dữ liệu kỹ thuật cổ phiếu:
{json.dumps(ptkt_report.get("signals", {}), ensure_ascii=False, indent=2)}

Giá hiện tại: {ptkt_report.get("price", {}).get("latest")}
Hỗ trợ gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("support")}
Kháng cự gần nhất: {ptkt_report.get("signals", {}).get("sr", {}).get("resistance")}
{fa_block}{ff_block}

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


def _run_rebuttal(bull: dict, bear: dict, ptkt_report: dict) -> dict:
    """
    Vòng 2: Rebuttal — mỗi bên phản bác case của đối phương.
    Bull đọc Bear case → phản bác. Bear đọc Bull case → phản bác.
    Synthesizer tổng hợp cả 2 vòng.
    """
    print("  [REBUTTAL] Vòng 2 — Phản bác...")

    # Bull rebuttal: phản bác Bear
    bull_rebuttal_raw = _call_claude(
        system="""Bạn là Bull Analyst. Đọc luận điểm Bear và phản bác từng điểm yếu.
Trả về JSON: {"rebuttal_points": ["phản bác 1", "phản bác 2"], "bull_score_revised": 0-100}""",
        user=f"""Luận điểm Bear cần phản bác:
{json.dumps(bear.get('top_risks', []), ensure_ascii=False)}
Main flaw theo Bear: {bear.get('main_bull_flaw', '')}
Giá: {ptkt_report.get("price", {}).get("latest")}

Phản bác ngắn gọn, thực chất. Trả về JSON.""",
        max_tokens=300,
        model=MODEL_REBUTTAL
    ).replace("```json", "").replace("```", "").strip()

    # Bear rebuttal: phản bác Bull
    bear_rebuttal_raw = _call_claude(
        system="""Bạn là Bear Analyst. Đọc luận điểm Bull và phản bác từng điểm yếu.
Trả về JSON: {"rebuttal_points": ["phản bác 1", "phản bác 2"], "bear_score_revised": 0-100}""",
        user=f"""Luận điểm Bull cần phản bác:
{json.dumps(bull.get('top_reasons', []), ensure_ascii=False)}
Main risk theo Bull: {bull.get('main_risk', '')}
Giá: {ptkt_report.get("price", {}).get("latest")}

Phản bác ngắn gọn, thực chất. Trả về JSON.""",
        max_tokens=300,
        model=MODEL_REBUTTAL
    ).replace("```json", "").replace("```", "").strip()

    def _parse(raw):
        try:
            s = raw.find("{"); e = raw.rfind("}") + 1
            return json.loads(raw[s:e])
        except Exception:
            return {}

    bull_reb = _parse(bull_rebuttal_raw)
    bear_reb = _parse(bear_rebuttal_raw)

    return {
        "bull_rebuttal": bull_reb.get("rebuttal_points", []),
        "bull_score_revised": bull_reb.get("bull_score_revised", bull.get("score", 50)),
        "bear_rebuttal": bear_reb.get("rebuttal_points", []),
        "bear_score_revised": bear_reb.get("bear_score_revised", bear.get("score", 50)),
    }


def run(ptkt_report: dict, fa_report: dict = None, ff_report: dict = None) -> dict:
    """
    Chạy toàn bộ Debate 2 vòng:
    Vòng 1: Bull → Bear (độc lập)
    Vòng 2: Rebuttal (mỗi bên phản bác bên kia)
    Synthesize: tổng hợp cả 2 vòng.
    """
    symbol = ptkt_report.get("symbol", "N/A")
    print("\n" + "="*60)
    print(f"[DEBATE AGENT] Bull vs Bear 2 vòng: {symbol}")
    print("="*60)

    # Vòng 1: Case độc lập
    print("  Vòng 1: Lập luận độc lập...")
    bull    = _run_bull(ptkt_report, fa_report or {}, ff_report or {})
    bear    = _run_bear(ptkt_report, fa_report or {}, ff_report or {})

    # Vòng 2: Rebuttal
    print("  Vòng 2: Phản bác...")
    rebuttal = _run_rebuttal(bull, bear, ptkt_report)

    # Dùng score revised từ rebuttal nếu có
    bull["score"] = rebuttal.get("bull_score_revised", bull.get("score", 50))
    bear["score"] = rebuttal.get("bear_score_revised", bear.get("score", 50))

    summary = _synthesize(ptkt_report, bull, bear)

    print(f"\n  Bull score: {bull.get('score', '?')} | Bear score: {bear.get('score', '?')}")
    print(f"  Dominant: {summary.get('dominant_side', '?')} | Uncertainty: {summary.get('uncertainty_level', '?')}")

    return {
        "symbol":    symbol,
        "bull":      bull,
        "bear":      bear,
        "rebuttal":  rebuttal,
        "summary":   summary
    }
