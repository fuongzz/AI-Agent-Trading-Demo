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
from analysts.ptkt_agent      import run as run_ptkt
from research.debate_agent    import run as run_debate
from research.sentiment_agent import run as run_sentiment
from trader.trader_agent      import run as run_trader
from fetcher                  import fetch_realtime, fetch_macro, fetch_foreign_flow
from indicators               import get_session_progress
from database                 import save_agent_decision
from risk_manager             import evaluate_risk

load_dotenv()

# =====================================================================
# 1. STATE BẢNG TRẮNG LANGGRAPH
# =====================================================================
class PipelineState(TypedDict):
    symbol: str
    ptkt_report: dict
    sentiment: dict
    macro: dict
    foreign: dict
    debate: dict
    decision: dict

# =====================================================================
# 2. ĐỊNH NGHĨA CÁC NODE (AGENTS & MANAGERS)
# =====================================================================

def ta_agent_node(state: PipelineState) -> dict:
    print(">>> 🧠 [TA Agent] Phân tích Kỹ thuật...")
    report = run_ptkt(state["symbol"])
    return {"ptkt_report": report or {}}

def sentiment_agent_node(state: PipelineState) -> dict:
    print(">>> 📰 [Sentiment Agent] Phân tích Tin tức (CafeF/VnExpress)...")
    sent = run_sentiment(state["symbol"])
    return {"sentiment": sent or {}}

def market_agent_node(state: PipelineState) -> dict:
    print(">>> 🌐 [Market Agent] Đo lường Vĩ mô và khối Ngoại...")
    macro = fetch_macro()
    foreign = fetch_foreign_flow(state["symbol"])
    return {"macro": macro, "foreign": foreign}

def debate_agent_node(state: PipelineState) -> dict:
    print(">>> ⚔️ [Debate Agent] Tổ chức tranh luận Bull vs Bear...")
    debate_res = run_debate(state["ptkt_report"])
    return {"debate": debate_res or {}}

def trader_agent_node(state: PipelineState) -> dict:
    print(">>> 🧑‍💼 [Trader Agent] Xem xét chiến lược và ra quyết định...")
    dec = run_trader(state["ptkt_report"], state["debate"], state["sentiment"])
    return {"decision": dec or {}}

def risk_manager_node(state: PipelineState) -> dict:
    print(">>> 🛡️ [Risk Manager] Rà soát quy tắc an toàn cuối cùng...")
    decision = state.get("decision", {})
    action = decision.get("action", "CHỜ")
    
    # Lấy thông số môi trường
    macro = state.get("macro", {})
    foreign = state.get("foreign", {})
    vnindex_change = macro.get("vnindex", {}).get("change_1d", 0)
    foreign_room = foreign.get("room_usage_pct", 0)
    
    # Evaluate Risk
    risk_assessment = evaluate_risk(
        state["symbol"], 
        action, 
        vnindex_change, 
        foreign_room, 
        intraday_amplitude_pct=0 # Giả định demo
    )
    
    # Đè quyết định nếu rủi ro vi phạm
    decision["action"] = risk_assessment["final_action"]
    decision["risk_override"] = risk_assessment["override_reason"]
    
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
workflow.add_node("TA", ta_agent_node)
workflow.add_node("Sentiment", sentiment_agent_node)
workflow.add_node("Market", market_agent_node)
workflow.add_node("Debate", debate_agent_node)
workflow.add_node("Trader", trader_agent_node)
workflow.add_node("Risk", risk_manager_node)

# Flow Song Song: TA, Sentiment, Market chạy cùng lúc.
workflow.add_edge(START, "TA")
workflow.add_edge(START, "Sentiment")
workflow.add_edge(START, "Market")

# Sau khi cả 3 chạy xong sẽ cùng đổ vào Debate
workflow.add_edge(["TA", "Sentiment", "Market"], "Debate")

workflow.add_edge("Debate", "Trader")
workflow.add_edge("Trader", "Risk")
workflow.add_edge("Risk", END)

app = workflow.compile()


# =====================================================================
# 4. CHẠY THỰC TẾ & HIỂN THỊ
# =====================================================================

def run_pipeline(symbol: str, force: bool = False) -> dict:
    symbol = symbol.upper()
    start = datetime.now()
    
    print("\n" + "█"*60)
    print(f"  LANGGRAPH MULTI-AGENT PIPELINE — {symbol}")
    print(f"  {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)
    
    # Chạy LangGraph
    initial_state = {"symbol": symbol}
    final_state = app.invoke(initial_state)
    
    elapsed = round((datetime.now() - start).total_seconds(), 1)
    
    # Gộp thành Result dict tương thích hàm hiển thị
    result = {
        "symbol": symbol,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "ptkt_report": final_state.get("ptkt_report", {}),
        "sentiment": final_state.get("sentiment", {}),
        "debate": final_state.get("debate", {}),
        "decision": final_state.get("decision", {})
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
         print(f"  Lý do: {d.get('reason')}")

    print(f"{'█'*W}\n")


if __name__ == "__main__":
    print("""
MULTI-AGENT TRADING SYSTEM (LANGGRAPH ENABLED)
Tầng I: Parallel Agents → Tầng II: Debate → Tầng III: Trader → Tầng IV: Risk
    """)
    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    run_pipeline(symbol)
