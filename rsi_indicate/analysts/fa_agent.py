"""
analysts/fa_agent.py — Fundamental Analysis Agent
Nhiệm vụ: Phân tích sức khỏe tài chính doanh nghiệp từ BCTC vnstock.

Input:  symbol (str)
Output: FAReport (dict) — định giá, chất lượng lợi nhuận, anomaly flags

Không tranh luận, không quyết định — chỉ chuẩn bị brief FA để Debate đọc.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import anthropic
from fetcher import fetch_fundamentals, fetch_company_info

MODEL = "claude-haiku-4-5-20251001"

# Ngưỡng trung bình ngành VN (rough benchmark — cần tinh chỉnh theo từng ngành)
INDUSTRY_BENCHMARKS = {
    "default": {"pe": 15.0, "pb": 2.0, "roe": 15.0, "net_margin": 10.0},
    "ngân hàng": {"pe": 10.0, "pb": 1.5, "roe": 18.0, "net_margin": 25.0},
    "bất động sản": {"pe": 20.0, "pb": 2.5, "roe": 12.0, "net_margin": 15.0},
    "chứng khoán": {"pe": 12.0, "pb": 1.8, "roe": 15.0, "net_margin": 30.0},
    "thép": {"pe": 8.0,  "pb": 1.2, "roe": 12.0, "net_margin": 5.0},
    "tiêu dùng": {"pe": 18.0, "pb": 3.0, "roe": 20.0, "net_margin": 12.0},
}


def _get_benchmark(industry: str) -> dict:
    """Trả về benchmark theo ngành, fallback về default."""
    industry_lower = (industry or "").lower()
    for key in INDUSTRY_BENCHMARKS:
        if key in industry_lower:
            return INDUSTRY_BENCHMARKS[key]
    return INDUSTRY_BENCHMARKS["default"]


def _detect_anomalies(fa_data: dict) -> list:
    """
    Rule-based anomaly detection — không dùng LLM (deterministic).
    Trả về list các cảnh báo.
    """
    flags = []

    pe  = fa_data.get("pe")
    pb  = fa_data.get("pb")
    roe = fa_data.get("roe_pct")
    net_margin    = fa_data.get("net_profit_margin_pct")
    gross_margin  = fa_data.get("gross_profit_margin_pct")
    rev_yoy       = fa_data.get("revenue_yoy_pct")

    # P/E bất thường (âm hoặc quá cao)
    if pe is not None:
        if pe < 0:
            flags.append("P/E âm — công ty đang lỗ")
        elif pe > 50:
            flags.append(f"P/E={pe:.1f} rất cao — định giá premium hoặc kỳ vọng tăng trưởng lớn")

    # ROE thấp dưới mức lãi suất tiết kiệm
    if roe is not None and roe < 8.0:
        flags.append(f"ROE={roe:.1f}% thấp hơn lãi suất tiết kiệm — hiệu quả kém")

    # Chất lượng lợi nhuận: gross margin >> net margin → chi phí tài chính cao
    if gross_margin is not None and net_margin is not None:
        if gross_margin > 0 and net_margin < gross_margin * 0.3:
            flags.append(f"Gross margin {gross_margin:.1f}% vs Net margin {net_margin:.1f}% "
                         f"— chi phí tài chính/SG&A rất cao, cần kiểm tra nợ vay")

    # Doanh thu tăng trưởng âm
    if rev_yoy is not None and rev_yoy < -10.0:
        flags.append(f"Doanh thu YoY={rev_yoy:.1f}% — suy giảm đáng kể")

    # P/B thấp bất thường (có thể undervalue hoặc vấn đề tài sản)
    if pb is not None and pb < 0.5:
        flags.append(f"P/B={pb:.2f} rất thấp — có thể undervalue hoặc tài sản bị phá giá")

    return flags


def _interpret_valuation(fa_data: dict, benchmark: dict) -> dict:
    """So sánh định giá với benchmark ngành."""
    pe  = fa_data.get("pe")
    pb  = fa_data.get("pb")
    roe = fa_data.get("roe_pct")

    verdict = "KHÔNG RÕ"
    reasons = []

    signals_cheap   = 0
    signals_fair    = 0
    signals_expensive = 0

    if pe is not None and pe > 0:
        if pe < benchmark["pe"] * 0.8:
            signals_cheap += 1
            reasons.append(f"P/E={pe:.1f} thấp hơn TB ngành {benchmark['pe']:.0f}x")
        elif pe > benchmark["pe"] * 1.3:
            signals_expensive += 1
            reasons.append(f"P/E={pe:.1f} cao hơn TB ngành {benchmark['pe']:.0f}x")
        else:
            signals_fair += 1

    if pb is not None and pb > 0:
        if pb < benchmark["pb"] * 0.8:
            signals_cheap += 1
            reasons.append(f"P/B={pb:.2f} thấp hơn TB ngành {benchmark['pb']:.1f}x")
        elif pb > benchmark["pb"] * 1.3:
            signals_expensive += 1
        else:
            signals_fair += 1

    if roe is not None:
        if roe > benchmark["roe"] * 1.2:
            signals_cheap += 1
            reasons.append(f"ROE={roe:.1f}% cao hơn TB ngành {benchmark['roe']:.0f}%")
        elif roe < benchmark["roe"] * 0.7:
            signals_expensive += 1

    if signals_cheap > signals_expensive:
        verdict = "UNDERVALUED"
    elif signals_expensive > signals_cheap:
        verdict = "OVERVALUED"
    else:
        verdict = "FAIR VALUE"

    return {"verdict": verdict, "reasons": reasons}


def run(symbol: str) -> dict:
    """
    Chạy FA Agent cho một mã cổ phiếu.
    Trả về FAReport — dict JSON chuẩn.
    """
    symbol = symbol.upper()
    print("\n" + "="*60)
    print(f"[FA AGENT] Phân tích cơ bản: {symbol}")
    print("="*60)

    # ── Bước 1: Lấy dữ liệu ──────────────────────────────────────────────────
    fa_data  = fetch_fundamentals(symbol)
    company  = fetch_company_info(symbol)
    industry = company.get("industry", "")

    if "error" in fa_data:
        print(f"  Lỗi lấy dữ liệu FA: {fa_data['error']}")
        return {
            "symbol":   symbol,
            "error":    fa_data["error"],
            "verdict":  "KHÔNG RÕ",
            "skipped":  True,
        }

    # ── Bước 2: Rule-based analysis ───────────────────────────────────────────
    benchmark    = _get_benchmark(industry)
    valuation    = _interpret_valuation(fa_data, benchmark)
    anomaly_flags = _detect_anomalies(fa_data)

    # ── Bước 3: Claude Haiku tổng hợp brief ──────────────────────────────────
    system = """Bạn là chuyên gia phân tích CƠ BẢN doanh nghiệp Việt Nam (FA Analyst).
Nhiệm vụ: Đọc số liệu tài chính, đưa ra nhận xét ngắn gọn về sức khỏe tài chính và triển vọng.
Tập trung vào: chất lượng lợi nhuận, tăng trưởng bền vững, định giá tương đối.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    user = f"""Mã: {symbol} | Ngành: {industry}

Chỉ số tài chính:
- P/E: {fa_data.get('pe')} | P/B: {fa_data.get('pb')} | ROE: {fa_data.get('roe_pct')}%
- ROA: {fa_data.get('roa_pct')}% | EPS: {fa_data.get('eps')} VND
- Biên lợi nhuận gộp: {fa_data.get('gross_profit_margin_pct')}% | Ròng: {fa_data.get('net_profit_margin_pct')}%
- Tăng trưởng DT YoY: {fa_data.get('revenue_yoy_pct')}%
- EV/EBITDA: {fa_data.get('ev_ebitda')}

Benchmark ngành: P/E={benchmark['pe']} | P/B={benchmark['pb']} | ROE={benchmark['roe']}%
Nhận định định giá (rule-based): {valuation['verdict']}
Lý do: {'; '.join(valuation['reasons']) if valuation['reasons'] else 'Không đủ dữ liệu'}
Cảnh báo bất thường: {'; '.join(anomaly_flags) if anomaly_flags else 'Không có'}

Trả về JSON:
{{
  "symbol": "{symbol}",
  "industry": "{industry}",
  "valuation_verdict": "UNDERVALUED/FAIR_VALUE/OVERVALUED/KHÔNG_RÕ",
  "quality_score": 0-100,
  "growth_outlook": "TÍCH CỰC/TRUNG LẬP/TIÊU CỰC",
  "key_strengths": ["điểm mạnh 1", "điểm mạnh 2"],
  "key_risks": ["rủi ro 1", "rủi ro 2"],
  "anomaly_flags": {json.dumps(anomaly_flags, ensure_ascii=False)},
  "fa_summary": "tóm tắt sức khỏe tài chính 2-3 câu"
}}"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=700,
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
            "valuation_verdict": valuation["verdict"],
            "quality_score":    50,
            "anomaly_flags":    anomaly_flags,
            "fa_summary":       raw[:300],
            "raw":              True,
        }

    # Đính kèm raw numbers để Trader Agent có thể tham chiếu
    report["raw_metrics"] = fa_data

    _print_fa(report)
    return report


def _print_fa(r: dict):
    verdict = r.get("valuation_verdict", "?")
    icon = {"UNDERVALUED": "🟢", "OVERVALUED": "🔴", "FAIR_VALUE": "🟡"}.get(verdict, "⚪")
    print(f"\n  {icon} Định giá: {verdict}  |  Chất lượng: {r.get('quality_score', '?')}/100")
    print(f"  Triển vọng tăng trưởng: {r.get('growth_outlook', '?')}")
    flags = r.get("anomaly_flags", [])
    if flags:
        for f in flags:
            print(f"  ⚠️  {f}")
    print(f"  Tóm tắt: {r.get('fa_summary', '')}")
    print("="*60)
