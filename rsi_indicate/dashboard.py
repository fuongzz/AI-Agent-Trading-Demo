"""
dashboard.py — Streamlit Dashboard 4 tab
Phần 6 của System Design.

Tab 1: Today's Analysis — danh sách cổ phiếu, signal, reasoning
Tab 2: Performance       — cumulative return vs VN-Index, win rate
Tab 3: Portfolio         — vị thế, P&L unrealized, risk exposure
Tab 4: System Health     — trạng thái pipeline, API cost

Chạy: streamlit run rsi_indicate/dashboard.py
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

sys.path.insert(0, os.path.dirname(__file__))

DB_PATH    = os.path.join(os.path.dirname(__file__), "trading_assistant.db")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VN100 AI Trading Assistant",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 VN100 AI Trading")
    st.caption("AI-Augmented Trading Assistant")
    st.divider()

    # Quick analysis
    st.subheader("Phân tích nhanh")
    quick_symbol = st.text_input("Mã cổ phiếu", placeholder="VD: VNM").upper()
    if st.button("Phân tích", type="primary"):
        st.session_state["run_symbol"] = quick_symbol

    st.divider()
    st.caption(f"Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")
    if st.button("🔄 Refresh"):
        st.rerun()


# ── Helpers ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_decisions(days: int = 30) -> pd.DataFrame:
    """Load agent decisions từ SQLite."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn   = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = pd.read_sql_query(
        "SELECT symbol, date, action, confluence_score, raw_reasoning, created_at "
        "FROM agent_decisions WHERE date >= ? ORDER BY created_at DESC",
        conn, params=(cutoff,)
    )
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_output_files() -> dict:
    """Load các file output JSON gần nhất."""
    results = {}
    if not os.path.exists(OUTPUT_DIR):
        return results
    for fname in sorted(os.listdir(OUTPUT_DIR), reverse=True):
        if fname.endswith(".json") and "_history" not in fname:
            sym_date = fname.replace(".json", "")
            parts    = sym_date.rsplit("_", 1)
            if len(parts) == 2:
                sym, date = parts
                if sym not in results:
                    fpath = os.path.join(OUTPUT_DIR, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            results[sym] = json.load(f)
                    except Exception:
                        pass
    return results


def action_badge(action: str) -> str:
    return {"MUA": "🟢 MUA", "BÁN": "🔴 BÁN", "CHỜ": "🟡 CHỜ"}.get(action, f"⚪ {action}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: TODAY'S ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def tab_today():
    st.header("Today's Analysis")
    st.caption("Kết quả phân tích các mã cổ phiếu hôm nay")

    df = load_decisions(days=1)
    outputs = load_output_files()

    if df.empty and not outputs:
        st.info("Chưa có dữ liệu phân tích hôm nay. Chạy `orchestrator.py` để bắt đầu.")
        return

    # Quick run nếu user nhập symbol ở sidebar
    if st.session_state.get("run_symbol"):
        sym = st.session_state["run_symbol"]
        with st.spinner(f"Đang phân tích {sym}..."):
            try:
                from orchestrator import run_pipeline
                result = run_pipeline(sym)
                st.session_state[f"result_{sym}"] = result
                st.session_state.pop("run_symbol", None)
                st.success(f"Phân tích {sym} hoàn thành!")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi: {e}")
                st.session_state.pop("run_symbol", None)

    # Bảng tổng hợp
    if not df.empty:
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_df  = df[df["date"] == today_str].copy()

        if not today_df.empty:
            st.subheader(f"Phân tích ngày {today_str}")

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Tổng phân tích", len(today_df))
            col2.metric("Tín hiệu MUA",   (today_df["action"] == "MUA").sum())
            col3.metric("Tín hiệu BÁN",   (today_df["action"] == "BÁN").sum())
            col4.metric("CHỜ",             (today_df["action"] == "CHỜ").sum())

            st.divider()

            # Bảng chi tiết
            for _, row in today_df.iterrows():
                sym    = row["symbol"]
                action = row["action"]
                score  = row["confluence_score"]

                try:
                    reasoning = json.loads(row["raw_reasoning"]) if row["raw_reasoning"] else {}
                except Exception:
                    reasoning = {}

                badge = action_badge(action)

                with st.expander(f"{badge} — **{sym}** | Confluence: {score:.1f}", expanded=action == "MUA"):
                    col_left, col_right = st.columns([2, 1])

                    with col_left:
                        st.write("**Lý do:**", reasoning.get("reason", "N/A"))
                        if reasoning.get("invalidation"):
                            st.write("**Vô hiệu khi:**", reasoning.get("invalidation"))
                        if reasoning.get("risk_override"):
                            st.warning(f"🛡️ Risk Override: {reasoning.get('risk_override')}")
                        for w in reasoning.get("risk_warnings", []):
                            st.warning(f"⚠️ {w}")

                    with col_right:
                        if action == "MUA":
                            st.metric("Entry", reasoning.get("entry", "?"))
                            st.metric("SL",    reasoning.get("sl", "?"))
                            st.metric("TP",    reasoning.get("tp", "?"))
                        elif action == "BÁN":
                            st.metric("Exit Price", reasoning.get("exit_price", "?"))

    # Output files (TA lite results)
    if outputs:
        st.divider()
        st.subheader("Kết quả TA Lite (cache)")
        for sym, data in list(outputs.items())[:10]:
            r = data.get("recommendation", {})
            s = data.get("signals", {})
            action = r.get("action", "?")
            badge  = action_badge(action)
            with st.expander(f"{badge} — **{sym}** | RSI: {s.get('rsi', {}).get('value', '?')}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**MA:**", s.get("ma", {}).get("trend", "?"))
                    st.write("**MACD:**", s.get("macd", {}).get("signal_text", "?")[:60])
                    st.write("**Volume:**", s.get("volume", {}).get("signal", "?")[:60])
                with col2:
                    st.write("**Confidence:**", r.get("confidence", "?"))
                    st.write("**Entry:**", r.get("entry", "?"))
                    st.write("**Reason:**", str(r.get("reason", ""))[:100])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

def tab_performance():
    st.header("Performance")
    st.caption("Hiệu quả hệ thống theo thời gian")

    df = load_decisions(days=90)
    if df.empty:
        st.info("Chưa có đủ dữ liệu để tính performance. Cần ít nhất 1 tháng dữ liệu.")
        return

    # Win rate theo symbol
    st.subheader("Win Rate theo mã")

    # Giả lập P&L đơn giản: MUA trước BÁN sau
    # (Backtest thật nằm trong backtest.py)
    symbol_stats = []
    for sym in df["symbol"].unique():
        sym_df   = df[df["symbol"] == sym].sort_values("date")
        total    = len(sym_df)
        buy_cnt  = (sym_df["action"] == "MUA").sum()
        sell_cnt = (sym_df["action"] == "BÁN").sum()
        avg_sc   = sym_df["confluence_score"].mean()
        symbol_stats.append({
            "Mã": sym,
            "Tổng phân tích": total,
            "Tín hiệu MUA": buy_cnt,
            "Tín hiệu BÁN": sell_cnt,
            "Avg Confluence": round(avg_sc, 2),
        })

    stats_df = pd.DataFrame(symbol_stats).sort_values("Tổng phân tích", ascending=False)
    st.dataframe(stats_df, use_container_width=True)

    st.divider()

    # Action distribution chart
    st.subheader("Phân phối tín hiệu (30 ngày)")
    action_counts = df.groupby(["date", "action"]).size().reset_index(name="count")

    fig = px.bar(
        action_counts, x="date", y="count", color="action",
        color_discrete_map={"MUA": "#00C853", "BÁN": "#D50000", "CHỜ": "#FFD600"},
        title="Tín hiệu theo ngày"
    )
    fig.update_layout(height=300, xaxis_title="Ngày", yaxis_title="Số tín hiệu")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Backtest runner
    st.subheader("Backtest nhanh")
    col1, col2, col3 = st.columns([2, 1, 1])
    bt_symbol = col1.text_input("Mã backtest", "VNM").upper()
    bt_days   = col2.number_input("Số ngày", min_value=60, max_value=500, value=365)

    if col3.button("Chạy Backtest", type="primary"):
        with st.spinner(f"Đang backtest {bt_symbol}..."):
            try:
                from backtest import run_backtest
                results = run_backtest(bt_symbol, days=bt_days)
                if results:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Lợi nhuận CL",  results["total_return_pct"])
                    c2.metric("Buy & Hold",     results["buy_hold_return"])
                    c3.metric("Alpha",          results["alpha"])
                    c4.metric("Max Drawdown",   results["max_drawdown"])

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Số giao dịch",  results["n_trades"])
                    c2.metric("Tỷ lệ thắng",   results["win_rate"])
                    c3.metric("Profit Factor",  results["profit_factor"])
            except Exception as e:
                st.error(f"Backtest lỗi: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

def tab_portfolio():
    st.header("Portfolio")
    st.caption("Vị thế đang nắm giữ và risk exposure")
    st.info("📌 Tính năng này cần tích hợp với dữ liệu giao dịch thực tế của bạn. "
            "Hiện tại hiển thị template để bạn fill vào.")

    # Template portfolio input
    st.subheader("Nhập vị thế hiện tại")
    portfolio_data = []

    col_sym, col_qty, col_avg, col_cur = st.columns(4)
    col_sym.write("**Mã**")
    col_qty.write("**Số CP**")
    col_avg.write("**Giá vốn**")
    col_cur.write("**Giá hiện tại**")

    # Dummy rows (user có thể mở rộng sau)
    if "portfolio" not in st.session_state:
        st.session_state["portfolio"] = [
            {"sym": "VNM", "qty": 1000, "avg": 75.0},
            {"sym": "HPG", "qty": 2000, "avg": 28.0},
        ]

    total_pnl     = 0
    total_invested = 0

    for item in st.session_state["portfolio"]:
        try:
            from fetcher import fetch_ohlcv
            ohlcv   = fetch_ohlcv(item["sym"], days=5)
            cur_price = ohlcv.get("latest_price", item["avg"])
        except Exception:
            cur_price = item["avg"]

        pnl     = (cur_price - item["avg"]) * item["qty"]
        pnl_pct = (cur_price - item["avg"]) / item["avg"] * 100
        invested = item["avg"] * item["qty"]
        total_pnl      += pnl
        total_invested += invested

        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 2])
        col1.write(f"**{item['sym']}**")
        col2.write(f"{item['qty']:,}")
        col3.write(f"{item['avg']:.1f}")
        col4.write(f"{cur_price:.1f}")
        icon = "🟢" if pnl >= 0 else "🔴"
        col5.write(f"{icon} {'+' if pnl >= 0 else ''}{pnl:,.0f} VND ({pnl_pct:+.1f}%)")

    st.divider()

    # Summary
    if total_invested > 0:
        col1, col2, col3 = st.columns(3)
        col1.metric("Tổng đầu tư",     f"{total_invested:,.0f} VND")
        col2.metric("P&L Unrealized",  f"{'+' if total_pnl >= 0 else ''}{total_pnl:,.0f} VND")
        col3.metric("Return",          f"{total_pnl / total_invested * 100:+.2f}%")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: SYSTEM HEALTH
# ══════════════════════════════════════════════════════════════════════════════

def tab_system_health():
    st.header("System Health")
    st.caption("Trạng thái các pipeline và thống kê hệ thống")

    # Database status
    st.subheader("Database")
    col1, col2 = st.columns(2)

    if os.path.exists(DB_PATH):
        db_size = os.path.getsize(DB_PATH) / 1024
        conn    = sqlite3.connect(DB_PATH)
        n_decisions = pd.read_sql_query("SELECT COUNT(*) as n FROM agent_decisions", conn).iloc[0]["n"]
        n_prices    = pd.read_sql_query("SELECT COUNT(*) as n FROM daily_prices", conn).iloc[0]["n"]
        conn.close()

        col1.metric("DB Size",          f"{db_size:.1f} KB")
        col2.metric("Agent Decisions",  n_decisions)
        col1.metric("Daily Prices",     n_prices)
        col2.metric("DB Status",        "✅ Online")
    else:
        st.error("Database chưa được khởi tạo.")

    st.divider()

    # Output files
    st.subheader("Cache files")
    outputs = load_output_files()
    cache_dir = os.path.join(os.path.dirname(__file__), "cache")
    n_cache   = len(os.listdir(cache_dir)) if os.path.exists(cache_dir) else 0

    col1, col2 = st.columns(2)
    col1.metric("Output JSONs", len(outputs))
    col2.metric("Indicator Caches", n_cache)

    if outputs:
        symbols_analyzed = list(outputs.keys())
        st.write("Đã phân tích:", ", ".join(symbols_analyzed))

    st.divider()

    # Environment check
    st.subheader("Environment")
    checks = {
        "ANTHROPIC_API_KEY":   bool(os.getenv("ANTHROPIC_API_KEY")),
        "DISCORD_BOT_TOKEN":   bool(os.getenv("DISCORD_BOT_TOKEN")),
        "DISCORD_WEBHOOK_URL": bool(os.getenv("DISCORD_WEBHOOK_URL")),
        "ChromaDB":            False,
        "discord.py":          False,
        "pandas_ta":           False,
        "vnstock":             False,
    }

    try:
        import chromadb;  checks["ChromaDB"]  = True
    except ImportError:   pass
    try:
        import discord;   checks["discord.py"] = True
    except ImportError:   pass
    try:
        import pandas_ta; checks["pandas_ta"]  = True
    except ImportError:   pass
    try:
        import vnstock;   checks["vnstock"]    = True
    except ImportError:   pass

    for name, ok in checks.items():
        icon = "✅" if ok else "❌"
        st.write(f"{icon} {name}")

    st.divider()

    # Recent decisions log
    st.subheader("Log quyết định gần nhất (20 dòng)")
    df = load_decisions(days=7)
    if not df.empty:
        display_df = df[["symbol", "date", "action", "confluence_score", "created_at"]].head(20)
        display_df.columns = ["Mã", "Ngày", "Quyết định", "Confluence", "Thời gian"]
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("Chưa có log.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    st.title("🤖 VN100 AI Trading Assistant")
    st.caption("AI-Augmented | AI hỗ trợ, người ra quyết định cuối")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Today's Analysis",
        "📈 Performance",
        "💼 Portfolio",
        "🔧 System Health"
    ])

    with tab1:
        tab_today()
    with tab2:
        tab_performance()
    with tab3:
        tab_portfolio()
    with tab4:
        tab_system_health()


if __name__ == "__main__":
    main()
