"""
orchestrator.py — Pipeline điều phối Multi-Agent bằng LangGraph
Chạy: python orchestrator.py

Luồng:
  [Input: mã CK]
       ↓
  [Tầng I - Multi-Agent] Chạy SONG SONG các Agent (TA, Sentiment, Market Context)
       ↓
  [Tầng II - Debate] Bull vs Bear Debate Agent
       ↓
  [Tầng III - Trader] Trader Agent ra quyết định thô
       ↓
  [Tầng IV - Risk] Risk Manager chốt kiểm duyệt cuối (Rule-based)
       ↓
  [Output] Lưu DB + In báo cáo.
"""

import sys, os, json
from typing import TypedDict
from datetime import datetime
from dotenv import load_dotenv

# Thêm thư mục gốc vào path để import được các module
sys.path.insert(0, os.path.dirname(__file__))

# Import LangGraph
from langgraph.graph import StateGraph, START, END

# Import các components cũ
from analysts.ptkt_agent          import run as run_ptkt
from analysts.fa_agent            import run as run_fa
from analysts.foreign_flow_agent  import run as run_foreign_flow
from research.debate_agent        import run as run_debate
from research.sentiment_agent     import run as run_sentiment
from trader.trader_agent          import run as run_trader
from fetcher                      import fetch_realtime, fetch_macro, fetch_foreign_flow
from indicators               import get_session_progress
from database                 import save_agent_decision
from risk_manager             import evaluate_risk
from screener                 import quick_pass_single

load_dotenv()

# =====================================================================
# 1. STATE BẢNG TRẮNG LANGGRAPH
# =====================================================================
class PipelineState(TypedDict):
    symbol: str
    screen_result: dict        # Kết quả từ screener
    ptkt_report: dict          # TA Agent output
    fa_report: dict            # FA Agent output
    sentiment: dict            # Sentiment Agent output
    foreign_flow_report: dict  # Foreign Flow Agent output (LLM-based)
    macro: dict                # Macro data (VN-Index, circuit breaker)
    debate: dict               # Bull/Bear Debate output
    decision: dict             # Trader + Risk Manager output

# =====================================================================
# 2. ĐỊNH NGHĨA CÁC NODE (AGENTS & MANAGERS)
# =====================================================================

def _run_screener(symbol: str) -> dict:
    """Helper: chạy screener cho 1 mã, trả về screen_result dict."""
    result = quick_pass_single(symbol)
    icon = "✅" if result["pass"] else "❌"
    print(f"    {icon} score={result['score']} | {result['reason']}")
    return result


def ta_agent_node(state: PipelineState) -> dict:
    print(">>> 🧠 [TA Agent] Phân tích Kỹ thuật...")
    report = run_ptkt(state["symbol"])
    return {"ptkt_report": report or {}}

def fa_agent_node(state: PipelineState) -> dict:
    print(">>> 📊 [FA Agent] Phân tích Cơ bản (BCTC)...")
    report = run_fa(state["symbol"])
    return {"fa_report": report or {}}

def sentiment_agent_node(state: PipelineState) -> dict:
    print(">>> 📰 [Sentiment Agent] Phân tích Tin tức (CafeF/VnExpress)...")
    sent = run_sentiment(state["symbol"])
    return {"sentiment": sent or {}}

def macro_agent_node(state: PipelineState) -> dict:
    print(">>> 🌐 [Macro Agent] Đo lường Vĩ mô (VN-Index, circuit breaker)...")
    macro = fetch_macro()
    return {"macro": macro}

def foreign_flow_agent_node(state: PipelineState) -> dict:
    print(">>> 🏦 [Foreign Flow Agent] Phân tích hành vi khối ngoại...")
    report = run_foreign_flow(state["symbol"])
    return {"foreign_flow_report": report or {}}

def debate_agent_node(state: PipelineState) -> dict:
    print(">>> ⚔️ [Debate Agent] Tổ chức tranh luận Bull vs Bear...")
    debate_res = run_debate(state["ptkt_report"], state.get("fa_report", {}),
                            state.get("foreign_flow_report", {}))
    return {"debate": debate_res or {}}

def trader_agent_node(state: PipelineState) -> dict:
    print(">>> 🧑‍💼 [Trader Agent] Xem xét chiến lược và ra quyết định...")
    dec = run_trader(state["ptkt_report"], state["debate"], state["sentiment"],
                     state.get("fa_report", {}), state.get("foreign_flow_report", {}))
    return {"decision": dec or {}}

def risk_manager_node(state: PipelineState) -> dict:
    print(">>> 🛡️ [Risk Manager] Rà soát quy tắc an toàn cuối cùng...")
    decision = state.get("decision", {})
    action   = decision.get("action", "CHỜ")

    # Lấy thông số môi trường
    macro      = state.get("macro", {})
    ff_report  = state.get("foreign_flow_report", {})
    vnindex_change = macro.get("vnindex", {}).get("change_1d", 0)

    # Ưu tiên lấy room_usage từ foreign_flow_report (LLM agent), fallback về raw
    foreign_room = (ff_report.get("room_usage_pct")
                    or ff_report.get("raw_ff", {}).get("room_usage_pct")
                    or 0)

    # Evaluate Risk với đầy đủ rules
    risk_assessment = evaluate_risk(
        symbol=state["symbol"],
        ai_decision=action,
        vnindex_change_pct=vnindex_change,
        foreign_room_pct=foreign_room,
        intraday_amplitude_pct=0,  # TODO: lấy từ intraday data khi có
        recent_buys=[],            # TODO: lấy từ database khi có portfolio tracking
        check_trading_window=True,
    )

    # Đè quyết định nếu rủi ro vi phạm
    decision["action"]          = risk_assessment["final_action"]
    decision["risk_override"]   = risk_assessment["override_reason"]
    decision["risk_warnings"]   = risk_assessment.get("warnings", [])
    decision["sizing_modifier"] = risk_assessment.get("sizing_modifier", 1.0)

    # In warnings nếu có
    for w in risk_assessment.get("warnings", []):
        print(f"    ⚠️  {w}")

    # Ghi nhận vào SQLite DB
    today = datetime.now().strftime("%Y-%m-%d")
    score = state.get("ptkt_report", {}).get("signals", {}).get("confluence", {}).get("score", 0)
    save_agent_decision(state["symbol"], today, decision["action"], float(score), decision)

    return {"decision": decision}

# =====================================================================
# 3. KẾT NỐI SƠ ĐỒ (ORCHESTRATOR)
# =====================================================================

workflow = StateGraph(PipelineState)

# Add Nodes
workflow.add_node("TA",          ta_agent_node)
workflow.add_node("FA",          fa_agent_node)
workflow.add_node("Sentiment",   sentiment_agent_node)
workflow.add_node("Macro",       macro_agent_node)
workflow.add_node("ForeignFlow", foreign_flow_agent_node)
workflow.add_node("Debate",      debate_agent_node)
workflow.add_node("Trader",      trader_agent_node)
workflow.add_node("Risk",        risk_manager_node)

# Flow Song Song: 5 agents chạy cùng lúc (Tầng I theo system design).
workflow.add_edge(START, "TA")
workflow.add_edge(START, "FA")
workflow.add_edge(START, "Sentiment")
workflow.add_edge(START, "Macro")
workflow.add_edge(START, "ForeignFlow")

# Sau khi cả 5 chạy xong → Debate
workflow.add_edge(["TA", "FA", "Sentiment", "Macro", "ForeignFlow"], "Debate")

workflow.add_edge("Debate", "Trader")
workflow.add_edge("Trader", "Risk")
workflow.add_edge("Risk",   END)

app = workflow.compile()


# =====================================================================
# 4. CHẠY THỰC TẾ & HIỂN THỊ
# =====================================================================

def run_pipeline(symbol: str, force: bool = False, skip_screener: bool = False) -> dict:
    symbol = symbol.upper()
    start = datetime.now()

    print("\n" + "█"*60)
    print(f"  LANGGRAPH MULTI-AGENT PIPELINE — {symbol}")
    print(f"  {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)

    # ── Domain Knowledge Screener (chạy TRƯỚC LangGraph để tiết kiệm API cost) ──
    screen_result = {"pass": True, "reason": "Screener bị bỏ qua (skip_screener=True)", "score": 0}
    if not skip_screener:
        print("\n>>> 🔍 [Screener] Kiểm tra sơ loại Domain Knowledge...")
        screen_result = _run_screener(symbol)
        icon = "✅" if screen_result["pass"] else "❌"
        print(f"    {icon} score={screen_result['score']} | {screen_result['reason']}")

        if not screen_result["pass"]:
            print(f"\n[Screener] {symbol} KHÔNG qua vòng sơ loại → Skip toàn bộ agent pipeline.")
            decision = {
                "action":        "CHỜ",
                "reason":        f"[Screener] {screen_result['reason']}",
                "confidence":    "CAO",
                "entry": None, "sl": None, "tp": None,
                "risk_override": None,
                "skipped_by_screener": True,
            }
            today = datetime.now().strftime("%Y-%m-%d")
            save_agent_decision(symbol, today, "CHỜ", 0.0, decision)
            elapsed = round((datetime.now() - start).total_seconds(), 1)
            return {
                "symbol": symbol,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_sec": elapsed,
                "screen_result": screen_result,
                "ptkt_report": {}, "sentiment": {}, "debate": {},
                "decision": decision,
            }

    # ── Chạy LangGraph (chỉ khi pass screener) ──
    initial_state = {"symbol": symbol, "screen_result": screen_result}
    final_state = app.invoke(initial_state)
    
    elapsed = round((datetime.now() - start).total_seconds(), 1)
    
    # Gộp thành Result dict tương thích hàm hiển thị
    result = {
        "symbol":              symbol,
        "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec":         elapsed,
        "screen_result":       screen_result,
        "ptkt_report":         final_state.get("ptkt_report", {}),
        "fa_report":           final_state.get("fa_report", {}),
        "foreign_flow_report": final_state.get("foreign_flow_report", {}),
        "sentiment":           final_state.get("sentiment", {}),
        "debate":              final_state.get("debate", {}),
        "decision":            final_state.get("decision", {})
    }
    
    print(f"\n[Pipeline hoàn thành] {elapsed}s")
    _print_full_result(result)
    return result


def _print_full_result(result: dict):
    """In báo cáo đầy đủ cho người dùng tự phân tích và quyết định."""
    ptkt   = result.get("ptkt_report", {})
    p      = ptkt.get("price", {})
    s      = ptkt.get("signals", {})
    sr     = s.get("sr", {})
    ma     = s.get("ma", {})
    rsi    = s.get("rsi", {})
    mac    = s.get("macd", {})
    vol    = s.get("volume", {})
    fa     = result.get("fa_report", {})
    dbt    = result.get("debate", {})
    bull   = dbt.get("bull", {})
    bear   = dbt.get("bear", {})
    syn    = dbt.get("summary", {})
    snt    = result.get("sentiment", {})
    d      = result.get("decision", {})
    
    action = d.get("action", "?")
    icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "")
    W      = 62

    print(f"\n{'█'*W}")
    print(f"  BÁO CÁO PHÂN TÍCH — {result.get('symbol')}")
    print(f"{'█'*W}")

    print(f"\n  ▌ TÍN HIỆU ĐỒNG THUẬN (CONFLUENCE)")
    print(f"  {'─'*58}")
    print(f"  RSI: {rsi.get('signal')}")
    print(f"  MA:  {ma.get('trend')} | MACD: {mac.get('signal_text')}")
    print(f"  Vol: {vol.get('ratio')}x TB20 → {vol.get('signal')}")

    print(f"\n  ▌ PHÂN TÍCH CƠ BẢN (FA)")
    print(f"  {'─'*58}")
    if fa and not fa.get("skipped"):
        fa_icon = {"UNDERVALUED": "🟢", "OVERVALUED": "🔴", "FAIR_VALUE": "🟡"}.get(fa.get("valuation_verdict"), "⚪")
        print(f"  {fa_icon} Định giá: {fa.get('valuation_verdict')}  |  Chất lượng: {fa.get('quality_score', '?')}/100")
        print(f"  Triển vọng: {fa.get('growth_outlook', '?')}")
        for flag in fa.get("anomaly_flags", [])[:2]:
            print(f"  ⚠️  {flag}")
        print(f"  Tóm tắt: {str(fa.get('fa_summary', ''))[:100]}...")
    else:
        print("  Không khả dụng.")

    print(f"\n  ▌ TÔNG TIN TỨC (SENTIMENT)")
    print(f"  {'─'*58}")
    if snt and not snt.get("error"):
        print(f"  Tâm lý: {snt.get('overall_sentiment')} ({snt.get('sentiment_score')}/100)")
        print(f"  Tóm tắt: {snt.get('sentiment_summary', '')[:100]}...")
    else:
        print("  Không khả dụng.")

    print(f"\n  ▌ DEBATE (BULL VS BEAR)")
    print(f"  {'─'*58}")
    if dbt:
        print(f"  Bull ({bull.get('score', 0)}/100): {bull.get('top_reasons', [''])[0]}")
        print(f"  Bear ({bear.get('score', 0)}/100): {bear.get('top_risks', [''])[0]}")
        print(f"  Chốt: {syn.get('market_context', '')}")
    else:
        print("  Không khả dụng.")

    print(f"\n  ▌ KHUYẾN NGHỊ CUỐI CÙNG TỪ HỆ THỐNG")
    print(f"  {'─'*58}")
    print(f"  {icon} Hành động : {action}")
    if d.get("risk_override"):
        print(f"  🛡️ CHẶN RỦI RO: {d.get('risk_override')}")
    else:
        print(f"  Vào lệnh: {d.get('entry')} | SL: {d.get('sl')} | TP: {d.get('tp')}")
        if d.get("sizing_modifier") and d["sizing_modifier"] < 1.0:
            print(f"  ⚠️  Sizing giảm còn {d['sizing_modifier']*100:.0f}% do risk warnings")
        print(f"  Lý do: {d.get('reason')}")
    for w in d.get("risk_warnings", []):
        print(f"  ⚠️  {w}")

    print(f"{'█'*W}\n")


if __name__ == "__main__":
    print("""
MULTI-AGENT TRADING SYSTEM (LANGGRAPH ENABLED)
Tầng I: Parallel Agents → Tầng II: Debate → Tầng III: Trader → Tầng IV: Risk
    """)
    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    run_pipeline(symbol)
