"""
memory/memory_system.py — Memory System 3 lớp theo FinMem
Phần 5 của System Design.

Lớp 1: Working Memory  — dữ liệu 5 phiên gần nhất + quyết định gần đây (luôn trong context)
Lớp 2: Mid-term Memory — pattern 3 tháng nén thành summary, retrieve theo relevance (ChromaDB)
Lớp 3: Long-term Memory — sự kiện quan trọng VN: COVID crash, bong bóng 2021, margin call 2022

ChromaDB optional: nếu chưa cài thì chỉ dùng Working + Long-term.
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

# SQLite path (dùng chung với database.py)
_BASE    = os.path.dirname(os.path.dirname(__file__))
DB_PATH  = os.path.join(_BASE, "trading_assistant.db")
MEM_DIR  = os.path.dirname(__file__)

# ChromaDB optional
try:
    import chromadb
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# LỚP 1: WORKING MEMORY
# Luôn load vào context — dữ liệu 5 phiên gần nhất của symbol hiện tại
# ══════════════════════════════════════════════════════════════════════════════

def get_working_memory(symbol: str, n_sessions: int = 5) -> dict:
    """
    Lấy Working Memory cho một mã: 5 quyết định gần nhất từ SQLite.
    Luôn được đưa vào context của Trader Agent.
    """
    symbol = symbol.upper()
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT date, action, confluence_score, raw_reasoning
        FROM agent_decisions
        WHERE symbol = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (symbol, n_sessions))

    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        date, action, score, raw = row
        try:
            reasoning = json.loads(raw) if raw else {}
        except Exception:
            reasoning = {}
        sessions.append({
            "date":             date,
            "action":           action,
            "confluence_score": score,
            "reason":           reasoning.get("reason", ""),
        })

    # Tính streak: chuỗi CHỜ liên tiếp (signal không rõ)
    streak_wait = sum(1 for s in sessions if s["action"] == "CHỜ")

    return {
        "symbol":        symbol,
        "recent_sessions": sessions,
        "n_sessions":    len(sessions),
        "last_action":   sessions[0]["action"] if sessions else None,
        "last_date":     sessions[0]["date"]   if sessions else None,
        "streak_wait":   streak_wait,
        "summary": _summarize_working(sessions),
    }


def _summarize_working(sessions: list) -> str:
    if not sessions:
        return "Chưa có lịch sử phân tích."
    actions = [s["action"] for s in sessions]
    buy_count  = actions.count("MUA")
    sell_count = actions.count("BÁN")
    wait_count = actions.count("CHỜ")
    last = sessions[0]
    return (f"{len(sessions)} phiên gần nhất: "
            f"MUA={buy_count}, BÁN={sell_count}, CHỜ={wait_count}. "
            f"Phiên cuối ({last['date']}): {last['action']} — {last['reason'][:80]}")


# ══════════════════════════════════════════════════════════════════════════════
# LỚP 2: MID-TERM MEMORY (ChromaDB vector store)
# Pattern 3 tháng, retrieve theo semantic similarity
# ══════════════════════════════════════════════════════════════════════════════

def _get_chroma_collection():
    """Khởi tạo ChromaDB collection cho mid-term memory."""
    if not _CHROMA_AVAILABLE:
        return None
    chroma_path = os.path.join(MEM_DIR, "chroma_db")
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_or_create_collection(
        name="mid_term_memory",
        metadata={"description": "Pattern và quyết định 3 tháng gần nhất"}
    )


def save_mid_term_memory(symbol: str, date: str, summary: str, metadata: dict = None):
    """
    Lưu một snapshot phân tích vào ChromaDB mid-term memory.
    Gọi sau mỗi phiên phân tích quan trọng.
    """
    col = _get_chroma_collection()
    if col is None:
        return  # ChromaDB chưa cài — bỏ qua silently

    doc_id = f"{symbol}_{date}"
    doc    = f"[{symbol}] {date}: {summary}"
    meta   = {"symbol": symbol, "date": date, **(metadata or {})}

    try:
        col.upsert(
            ids=[doc_id],
            documents=[doc],
            metadatas=[meta]
        )
    except Exception as e:
        print(f"[Memory] ChromaDB upsert lỗi: {e}")


def retrieve_mid_term_memory(query: str, symbol: str = None, n_results: int = 5) -> list:
    """
    Tìm kiếm semantic trong mid-term memory.
    Trả về list các snapshot liên quan nhất.
    """
    col = _get_chroma_collection()
    if col is None:
        return []

    where = {"symbol": symbol} if symbol else None
    try:
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )
        docs  = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]
    except Exception as e:
        print(f"[Memory] ChromaDB query lỗi: {e}")
        return []


def compress_to_mid_term(symbol: str, days: int = 90):
    """
    Nén các quyết định từ 3 tháng qua trong SQLite thành summary, lưu vào ChromaDB.
    Gọi định kỳ (VD: mỗi tuần) để cập nhật mid-term memory.
    """
    symbol = symbol.upper()
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    cursor.execute('''
        SELECT date, action, confluence_score, raw_reasoning
        FROM agent_decisions
        WHERE symbol = ? AND date >= ?
        ORDER BY date ASC
    ''', (symbol, cutoff))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return

    buy_dates  = [r[0] for r in rows if r[1] == "MUA"]
    sell_dates = [r[0] for r in rows if r[1] == "BÁN"]
    wait_dates = [r[0] for r in rows if r[1] == "CHỜ"]
    avg_score  = sum(r[2] for r in rows if r[2]) / len(rows)

    summary = (
        f"Tổng {len(rows)} phiên ({cutoff} → nay): "
        f"MUA {len(buy_dates)} lần ({', '.join(buy_dates[-3:])}), "
        f"BÁN {len(sell_dates)} lần, CHỜ {len(wait_dates)} lần. "
        f"Confluence score TB: {avg_score:.1f}."
    )

    save_mid_term_memory(
        symbol=symbol,
        date=datetime.now().strftime("%Y-%m-%d"),
        summary=summary,
        metadata={"days_covered": days, "n_sessions": len(rows), "avg_score": round(avg_score, 2)}
    )
    print(f"[Memory] Đã nén {len(rows)} phiên của {symbol} vào mid-term memory.")


# ══════════════════════════════════════════════════════════════════════════════
# LỚP 3: LONG-TERM MEMORY
# Sự kiện quan trọng lịch sử VN — hardcoded + có thể mở rộng
# ══════════════════════════════════════════════════════════════════════════════

LONG_TERM_EVENTS = [
    {
        "event":       "COVID Crash 2020",
        "period":      "2020-02 đến 2020-04",
        "description": "VN-Index giảm từ 1000 xuống 630 (-37%) trong 2 tháng. Circuit breaker kích hoạt. Sau đó phục hồi mạnh từ tháng 5.",
        "lesson":      "Panic sell đáy COVID là cơ hội mua tốt nhất thập kỷ. Chỉ số tốt nhất để detect đáy: RSI < 20 + volume spike bất thường.",
        "vn_specifics": "Room ngoại tăng mạnh khi ngoại mua vào đáy COVID.",
    },
    {
        "event":       "Bong bóng 2021",
        "period":      "2021-01 đến 2021-11",
        "description": "VN-Index từ 1000 lên đỉnh 1500 (+50%). Phần lớn cổ phiếu nhỏ tăng 3-5x. Nhỏ lẻ ào ạt vào thị trường.",
        "lesson":      "Dấu hiệu đỉnh bong bóng: margin debt tăng vọt, IPO ào ạt, P/E thị trường >25, truyền thông tích cực 100%. Thoát dần khi P/B ngành >3x.",
        "vn_specifics": "ATC manipulation phổ biến nhất giai đoạn này. Cần tránh cổ phiếu tăng >3x mà không có FA support.",
    },
    {
        "event":       "Margin Call Cascade 2022",
        "period":      "2022-04 đến 2022-11",
        "description": "VN-Index từ đỉnh 1500 về 900 (-40%). Lãi suất tăng, trái phiếu bất động sản vỡ, margin call dây chuyền.",
        "lesson":      "Khi margin call cascade: BẤT KỲ cổ phiếu nào cũng có thể bị kéo xuống bất kể FA tốt. Cash is king. Chỉ mua khi RSI < 25 + VN-Index chưa phục hồi trên MA20.",
        "vn_specifics": "Cổ phiếu BĐS, ngân hàng, chứng khoán bị ảnh hưởng nặng nhất. Room ngoại bán tháo.",
    },
    {
        "event":       "Phục hồi 2023",
        "period":      "2023-01 đến 2023-09",
        "description": "VN-Index phục hồi từ 900 lên 1250 (+39%). Dòng tiền quay lại nhóm Banking, Steel.",
        "lesson":      "Đầu chu kỳ phục hồi: ưu tiên cổ phiếu đầu ngành có FA tốt và đã điều chỉnh sâu. Tránh cổ phiếu nhỏ, kém thanh khoản.",
        "vn_specifics": "Khối ngoại mua ròng mạnh Banking Q1/2023 là tín hiệu dẫn đầu.",
    },
]


def get_long_term_memory(query: str = None) -> list:
    """
    Lấy Long-term Memory. Nếu có query, filter sự kiện liên quan.
    Luôn trả về toàn bộ nếu không có query.
    """
    if not query:
        return LONG_TERM_EVENTS

    query_lower = query.lower()
    relevant = []
    keywords = query_lower.split()

    for event in LONG_TERM_EVENTS:
        combined = (event["event"] + event["description"] + event["lesson"]).lower()
        if any(kw in combined for kw in keywords):
            relevant.append(event)

    return relevant if relevant else LONG_TERM_EVENTS  # fallback: trả tất cả


def add_long_term_event(event: str, period: str, description: str,
                        lesson: str, vn_specifics: str = ""):
    """
    Thêm sự kiện mới vào Long-term Memory (runtime, không persist sang file).
    Để persist, cần gọi hàm này và lưu vào JSON/DB riêng.
    """
    LONG_TERM_EVENTS.append({
        "event":       event,
        "period":      period,
        "description": description,
        "lesson":      lesson,
        "vn_specifics": vn_specifics,
    })


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API: get_full_context — dùng trong Trader Agent
# ══════════════════════════════════════════════════════════════════════════════

def get_full_context(symbol: str, query: str = None) -> dict:
    """
    Lấy đầy đủ memory context để đưa vào Trader Agent.
    Tự động combine cả 3 lớp, filter theo relevance.

    Returns dict với 3 sections: working, mid_term, long_term
    """
    working   = get_working_memory(symbol)
    mid_term  = retrieve_mid_term_memory(query or symbol, symbol=symbol) if _CHROMA_AVAILABLE else []
    long_term = get_long_term_memory(query)

    return {
        "working_memory":   working,
        "mid_term_memory":  mid_term,
        "long_term_events": long_term[:2],  # Chỉ lấy 2 sự kiện liên quan nhất để tiết kiệm token
        "chroma_available": _CHROMA_AVAILABLE,
    }


def format_context_for_prompt(ctx: dict) -> str:
    """Format memory context thành text ngắn để đưa vào prompt."""
    lines = []

    wm = ctx.get("working_memory", {})
    if wm.get("summary"):
        lines.append(f"[Lịch sử {wm['symbol']}] {wm['summary']}")

    for evt in ctx.get("long_term_events", []):
        lines.append(f"[Bài học lịch sử VN — {evt['event']}] {evt['lesson']}")

    for mt in ctx.get("mid_term_memory", [])[:2]:
        lines.append(f"[Pattern gần đây] {mt['text'][:150]}")

    return "\n".join(lines) if lines else ""
