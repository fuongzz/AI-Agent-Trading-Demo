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


def run(ptkt_report: dict, debate: dict, sentiment: dict = None) -> dict:
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
Nhiệm vụ: Đọc báo cáo kỹ thuật, kết quả tranh luận Bull/Bear, và sentiment tin tức để đưa ra quyết định giao dịch cuối cùng.

ĐẶC THÙ THỊ TRƯỜNG CHỨNG KHOÁN VIỆT NAM — BẮT BUỘC PHẢI HIỂU:
- KHÔNG CÓ SHORT SELLING (bán khống) trên HOSE/HNX. Tuyệt đối không đề xuất short.
- Chỉ có 3 trạng thái: MUA vào / BÁN cổ phiếu đang nắm giữ / CHỜ quan sát
- MUA: dành cho nhà đầu tư chưa nắm giữ, muốn mua vào
- BÁN: dành cho nhà đầu tư ĐANG NẮM GIỮ cổ phiếu, muốn thoát ra
- CHỜ: không hành động — chưa đủ tín hiệu để MUA hoặc BÁN
- Biên độ dao động ±7%/phiên, thanh toán T+3, không có công cụ phái sinh phổ thông

NGUYÊN TẮC ĐẶT GIÁ:
- MUA → entry < giá hiện tại hoặc bằng (mua ở giá hợp lý), SL thấp hơn entry, TP cao hơn entry
- BÁN → exit_price là giá nên thoát (gần giá hiện tại), KHÔNG có SL/TP kiểu short
         Thay vào đó: nêu "dấu hiệu nên giữ lại" nếu thị trường hồi phục
- CHỜ → nêu điều kiện cụ thể để MUA hoặc để BÁN (nếu đang nắm giữ)
- % NAV: tối đa 20% cho 1 lệnh, phụ thuộc độ tin cậy
- Trả về JSON hợp lệ, KHÔNG có markdown"""

    # Phần sentiment — chỉ thêm nếu có dữ liệu
    sentiment_block = ""
    if sentiment and not sentiment.get("skipped"):
        sentiment_block = f"""
=== SENTIMENT TIN TỨC (Sentiment Agent) ===
Tâm lý tổng thể: {sentiment.get("overall_sentiment")} (Điểm: {sentiment.get("sentiment_score")}/100)
Tác động ngắn hạn: {sentiment.get("short_term_impact")}
Chủ đề chính: {", ".join(sentiment.get("key_topics", []))}
Tích cực: {"; ".join(sentiment.get("positive_signals", [])[:2])}
Tiêu cực: {"; ".join(sentiment.get("negative_signals", [])[:2])}
Catalyst: {sentiment.get("catalyst", "Không có")}
Tóm tắt: {sentiment.get("sentiment_summary")}
"""

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
{sentiment_block}
=== YÊU CẦU ===
Đưa ra quyết định giao dịch phù hợp thị trường Việt Nam. Trả về JSON:

Nếu action = "MUA" (chưa nắm giữ, muốn mua vào):
{{
  "symbol": "...", "action": "MUA",
  "entry": giá mua vào hợp lý,
  "sl": giá cắt lỗ (THẤP HƠN entry),
  "tp": giá chốt lời (CAO HƠN entry),
  "risk_reward": (tp - entry) / (entry - sl),
  "nav_pct": 0-20,
  "holding_period": "ngắn hạn (1-5 phiên)/trung hạn (1-4 tuần)/dài hạn",
  "confidence": "CAO/TRUNG BÌNH/THẤP",
  "reason": "lý do mua — kỹ thuật + debate + sentiment",
  "invalidation": "dấu hiệu cho thấy quyết định mua là sai"
}}

Nếu action = "BÁN" (đang nắm giữ, nên thoát ra):
{{
  "symbol": "...", "action": "BÁN",
  "exit_price": giá nên thoát ra (gần giá hiện tại),
  "sl": null, "tp": null, "risk_reward": null, "nav_pct": null,
  "holding_period": null,
  "confidence": "CAO/TRUNG BÌNH/THẤP",
  "reason": "lý do nên bán — rủi ro cụ thể từ kỹ thuật + debate + sentiment",
  "invalidation": "dấu hiệu thị trường hồi phục — nếu xuất hiện thì cân nhắc giữ lại"
}}

Nếu action = "CHỜ":
{{
  "symbol": "...", "action": "CHỜ",
  "entry": null, "sl": null, "tp": null, "risk_reward": null, "nav_pct": null,
  "holding_period": null,
  "confidence": "CAO/TRUNG BÌNH/THẤP",
  "reason": "lý do chưa hành động",
  "invalidation": "điều kiện cụ thể để chuyển sang MUA hoặc BÁN (nếu đang nắm giữ)"
}}"""

    print("  Đang phân tích PTKTReport + DebateSummary...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}]
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
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

    if action == "MUA":
        print(f"  Vào lệnh: {d.get('entry')}  |  SL: {d.get('sl')}  |  TP: {d.get('tp')}")
        print(f"  R/R: 1:{d.get('risk_reward')}  |  % NAV: {d.get('nav_pct')}%  |  Kỳ hạn: {d.get('holding_period')}")
    elif action == "BÁN":
        print(f"  Giá thoát đề xuất: {d.get('exit_price')}  (dành cho người ĐANG nắm giữ)")
    # CHỜ: không in giá

    print(f"  Lý do: {d.get('reason')}")
    print(f"  {'Dấu hiệu giữ lại' if action == 'BÁN' else 'Điều kiện hành động' if action == 'CHỜ' else 'Vô hiệu khi'}: {d.get('invalidation')}")
    print("="*60)
