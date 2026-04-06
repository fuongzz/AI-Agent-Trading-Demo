"""
orchestrator.py — Pipeline điều phối Multi-Agent
Chạy: python orchestrator.py

Luồng:
  [Input: mã CK]
       ↓
  [Tầng I]  PTKT Agent      → PTKTReport (JSON)
       ↓
  [Tầng II] Debate Agent    → DebateSummary (Bull + Bear + Synthesize)
       ↓
  [Tầng III] Trader Agent   → TraderDecision (MUA/BÁN/CHỜ + SL/TP + NAV%)
       ↓
  [Output: in ra console + lưu file]
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os, json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# Thêm thư mục gốc vào path để import được các module
sys.path.insert(0, os.path.dirname(__file__))

from analysts.ptkt_agent   import run as run_ptkt
from research.debate_agent import run as run_debate
from trader.trader_agent   import run as run_trader
from fetcher               import fetch_realtime
from indicators            import get_session_progress


def run_pipeline(symbol: str, force: bool = False) -> dict:
    symbol   = symbol.upper()
    today    = datetime.now().strftime("%Y-%m-%d")
    out_dir  = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{symbol}_{today}_pipeline.json")

    print("\n" + "█"*60)
    print(f"  MULTI-AGENT PIPELINE — {symbol}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*60)

    # ── Kiểm tra pipeline cache ───────────────────────────────────
    if not force and os.path.exists(out_path):
        print(f"\n[Cache] Pipeline đã chạy hôm nay → Load từ {out_path}")
        with open(out_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        _print_cached_result(result)
        return result

    start = datetime.now()

    # ── Tầng I: PTKT Agent ────────────────────────────────────────
    print("\n>>> TẦNG I: PTKT AGENT")
    ptkt_report = run_ptkt(symbol)
    if not ptkt_report:
        print("Pipeline dừng: PTKT Agent không trả được dữ liệu.")
        return {}

    # ── Tầng II: Debate Agent ─────────────────────────────────────
    print("\n>>> TẦNG II: DEBATE AGENT (Bull vs Bear)")
    debate = run_debate(ptkt_report)

    # ── Tầng III: Trader Agent ────────────────────────────────────
    print("\n>>> TẦNG III: TRADER AGENT")
    decision = run_trader(ptkt_report, debate)

    # ── Lưu kết quả ──────────────────────────────────────────────
    elapsed = round((datetime.now() - start).total_seconds(), 1)
    result  = {
        "symbol":      symbol,
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": elapsed,
        "ptkt_report": ptkt_report,
        "debate":      debate,
        "decision":    decision,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[Pipeline hoàn thành] {elapsed}s | Lưu → {out_path}")
    _print_full_result(result)
    return result


def _print_full_result(result: dict):
    """In đầy đủ: giá, PTKT, debate, quyết định cuối."""
    ptkt = result.get("ptkt_report", {})
    p    = ptkt.get("price", {})
    s    = ptkt.get("signals", {})
    sr   = s.get("sr", {})
    dbt  = result.get("debate", {})
    bull = dbt.get("bull", {})
    bear = dbt.get("bear", {})
    syn  = dbt.get("summary", {})
    d    = result.get("decision", {})
    action = d.get("action", "?")
    icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "")

    print(f"\n{'█'*60}")
    print(f"  KẾT QUẢ PHÂN TÍCH — {result.get('symbol')}  ({result.get('timestamp')})")
    print(f"{'█'*60}")

    # ── Giá ──────────────────────────────────────────────────────
    print(f"\n  [ GIÁ ]")
    print(f"  Công ty  : {ptkt.get('company')} ({ptkt.get('exchange')}, {ptkt.get('industry')})")
    print(f"  Giá đóng : {p.get('latest')}  ({p.get('change_pct')}  |  {p.get('change')})")

    # ── Phân tích kỹ thuật ────────────────────────────────────────
    ma  = s.get("ma", {})
    rsi = s.get("rsi", {})
    mac = s.get("macd", {})
    bol = s.get("bollinger", {})
    vol = s.get("volume", {})
    atr = s.get("atr", {})

    print(f"\n  [ PHÂN TÍCH KỸ THUẬT ]")
    print(f"  RSI      : {rsi.get('value')}  → {rsi.get('signal')}")
    print(f"  MA5/MA20 : {ma.get('ma5')} / {ma.get('ma20')}  → {ma.get('trend')}  ({ma.get('cross')})")
    print(f"  MACD     : {mac.get('signal_text')}")
    print(f"  Bollinger: {bol.get('signal_text')}")
    print(f"  Volume   : {vol.get('ratio')}x TB20  → {vol.get('signal')}")
    print(f"  ATR      : {atr.get('volatility')}")
    print(f"  Hỗ trợ  : {sr.get('support')}  |  Kháng cự: {sr.get('resistance')}")
    print(f"  Vùng S/R : {sr.get('zone_signal')}")

    # ── Debate ────────────────────────────────────────────────────
    print(f"\n  [ DEBATE BULL vs BEAR ]")
    print(f"  Bull (điểm {bull.get('score', '?')}) : {bull.get('thesis', bull.get('summary', ''))}")
    print(f"  Bear (điểm {bear.get('score', '?')}) : {bear.get('thesis', bear.get('summary', ''))}")
    print(f"  Dominant : {syn.get('dominant_side', '?')}  — {syn.get('consensus', '')}")

    # ── Quyết định ────────────────────────────────────────────────
    print(f"\n  [ QUYẾT ĐỊNH TRADER ]")
    print(f"  {icon}  {action}  (Tin cậy: {d.get('confidence')})")
    print(f"  Entry : {d.get('entry')}  |  SL: {d.get('sl')}  |  TP: {d.get('tp')}  |  NAV: {d.get('nav_pct')}%")
    print(f"  Lý do : {d.get('reason')}")
    print(f"{'█'*60}\n")


def _realtime_check(symbol: str, result: dict):
    """
    Trong giờ giao dịch: fetch giá realtime, so sánh với SL/TP từ cache.
    Không gọi lại LLM — chỉ kiểm tra giá có vi phạm ngưỡng không.
    """
    progress = get_session_progress()
    if progress >= 1.0:
        return  # Ngoài giờ giao dịch → bỏ qua

    print("\n[Realtime Check] Đang trong giờ giao dịch, kiểm tra giá hiện tại...")
    rt = fetch_realtime(symbol)

    if "error" in rt or "note" in rt:
        print(f"  Không lấy được giá realtime: {rt.get('error') or rt.get('note')}")
        return

    current = rt.get("realtime_price", 0)
    d       = result.get("decision", {})
    action  = d.get("action")
    sl      = d.get("sl")
    tp      = d.get("tp")
    entry   = d.get("entry")

    cached_price = result.get("ptkt_report", {}).get("price", {}).get("latest", 0)
    change_pct   = round((current - cached_price) / cached_price * 100, 2) if cached_price else 0

    print(f"  Giá cached: {cached_price} → Giá hiện tại: {current} ({'+' if change_pct >= 0 else ''}{change_pct}%)")

    # Cảnh báo theo action
    if action == "MUA" and sl and current <= sl:
        print(f"  🔴 CẢNH BÁO: Giá ({current}) đã chạm/phá SL ({sl}) → Khuyến nghị MUA KHÔNG CÒN HIỆU LỰC")
    elif action == "MUA" and tp and current >= tp:
        print(f"  🎯 TP ĐẠT: Giá ({current}) đã chạm TP ({tp}) → Cân nhắc chốt lời")
    elif action == "BÁN" and tp and current <= tp:
        print(f"  🎯 TP ĐẠT: Giá ({current}) đã chạm TP ({tp}) → Cân nhắc chốt lời")
    elif action == "BÁN" and sl and current >= sl:
        print(f"  🔴 CẢNH BÁO: Giá ({current}) đã chạm/phá SL ({sl}) → Khuyến nghị BÁN KHÔNG CÒN HIỆU LỰC")
    elif entry and abs(change_pct) >= 3.0:
        print(f"  ⚠️  Giá biến động mạnh ({change_pct}%) so với lúc phân tích → Nên chạy lại pipeline")
    else:
        print(f"  ✅ Giá trong vùng bình thường — Khuyến nghị vẫn còn hiệu lực")

    print(f"  Thời điểm: {rt.get('time')} | Volume realtime: {rt.get('volume', 0):,}")


def _print_cached_result(result: dict):
    """In lại kết quả từ cache, sau đó chạy realtime check nếu trong giờ GD."""
    d      = result.get("decision", {})
    action = d.get("action", "?")
    icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "")
    debate = result.get("debate", {}).get("summary", {})
    print(f"\n{'='*60}")
    print(f"  KẾT QUẢ (từ cache — {result.get('timestamp')})")
    print(f"  Bull: {result.get('debate', {}).get('bull', {}).get('score')} | Bear: {result.get('debate', {}).get('bear', {}).get('score')} | Dominant: {debate.get('dominant_side')}")
    print(f"  QUYẾT ĐỊNH: {icon} {action}  (Tin cậy: {d.get('confidence')})")
    print(f"  Entry: {d.get('entry')} | SL: {d.get('sl')} | TP: {d.get('tp')} | NAV: {d.get('nav_pct')}%")
    print(f"  Lý do: {d.get('reason')}")
    print(f"{'='*60}")
    _realtime_check(result.get("symbol", ""), result)


if __name__ == "__main__":
    print("""
MULTI-AGENT TRADING SYSTEM — VN100
Tầng I: PTKT Agent → Tầng II: Bull/Bear Debate → Tầng III: Trader Decision
    """)
    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    force  = input("Chạy lại (bỏ qua cache)? (y/N): ").strip().lower() == "y"
    run_pipeline(symbol, force=force)
