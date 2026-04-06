"""
research/sentiment_agent.py — Sentiment Agent (Tầng I, song song với PTKT)
Nhiệm vụ: Crawl tin tức CafeF + VnExpress → Claude Haiku đánh giá sentiment.

Luồng:
  [Symbol] → news_fetcher (crawl 10 bài) → Claude Haiku đọc + đánh giá
           → SentimentReport (JSON)

Output được đưa thẳng vào Trader Agent (Tầng III) như một nguồn thông tin độc lập.
"""

import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import anthropic
from news_fetcher import fetch_news

MODEL = "claude-haiku-4-5-20251001"


def run(symbol: str) -> dict:
    """
    Chạy Sentiment Agent cho một mã cổ phiếu.
    Trả về SentimentReport — dict JSON đánh giá tâm lý qua tin tức.
    """
    symbol = symbol.upper()
    print("\n" + "="*60)
    print(f"[SENTIMENT AGENT] Crawl & phân tích tin tức: {symbol}")
    print("="*60)

    # ── Bước 1: Crawl tin tức ─────────────────────────────────────
    articles = fetch_news(symbol, max_per_source=5)

    if not articles:
        print("  Không lấy được bài báo nào → Bỏ qua Sentiment Agent")
        return {
            "symbol":            symbol,
            "overall_sentiment": "TRUNG LẬP",
            "sentiment_score":   50,
            "news_count":        0,
            "sentiment_summary": "Không crawl được tin tức.",
            "skipped":           True,
        }

    print(f"\n  Tổng: {len(articles)} bài báo → gửi Claude Haiku phân tích...")

    # ── Bước 2: Format tin tức để gửi Claude ─────────────────────
    news_text = ""
    for i, a in enumerate(articles, 1):
        news_text += f"\n[{i}] [{a['source']}] {a['title']}\n    {a['summary']}\n"

    # ── Bước 3: Claude Haiku đánh giá sentiment ──────────────────
    system = """Bạn là chuyên gia phân tích TÂM LÝ THỊ TRƯỜNG dựa trên tin tức (News Sentiment Analyst).
Nhiệm vụ: Đọc các bài báo về cổ phiếu, đánh giá tâm lý nhà đầu tư và xu hướng sentiment.
Chú ý: Lọc bỏ tin không liên quan đến cổ phiếu, chỉ phân tích tin về công ty/ngành/vĩ mô ảnh hưởng.
Trả về JSON hợp lệ, KHÔNG có markdown."""

    user = f"""Mã cổ phiếu cần phân tích: {symbol}

CÁC BÀI BÁO GẦN ĐÂY:
{news_text}

Dựa trên các bài báo trên, đánh giá sentiment thị trường với cổ phiếu {symbol}.

Trả về JSON theo schema:
{{
  "symbol": "{symbol}",
  "overall_sentiment": "TÍCH CỰC/TIÊU CỰC/TRUNG LẬP",
  "sentiment_score": 0-100,
  "news_count": {len(articles)},
  "relevant_news_count": số bài thực sự liên quan đến {symbol},
  "key_topics": ["chủ đề chính 1", "chủ đề chính 2", "chủ đề chính 3"],
  "positive_signals": ["tín hiệu tích cực từ tin tức"],
  "negative_signals": ["tín hiệu tiêu cực từ tin tức"],
  "catalyst": "sự kiện/yếu tố chính đang ảnh hưởng đến cổ phiếu (nếu có)",
  "short_term_impact": "TĂNG ĐIỂM/GIẢM ĐIỂM/KHÔNG RÕ",
  "sentiment_summary": "tóm tắt tâm lý tin tức 2-3 câu"
}}"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=900,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown code blocks nếu model vẫn wrap
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        start  = raw.find("{")
        end    = raw.rfind("}") + 1
        report = json.loads(raw[start:end])
    except Exception:
        report = {
            "symbol":            symbol,
            "overall_sentiment": "TRUNG LẬP",
            "sentiment_score":   50,
            "news_count":        len(articles),
            "sentiment_summary": raw[:300],
            "raw":               True,
        }

    # Gắn danh sách bài đã crawl vào report
    report["articles"] = [
        {"source": a["source"], "title": a["title"], "url": a["url"]}
        for a in articles
    ]

    _print_sentiment(report)
    return report


def _print_sentiment(r: dict):
    sentiment = r.get("overall_sentiment", "?")
    icon = {"TÍCH CỰC": "🟢", "TIÊU CỰC": "🔴", "TRUNG LẬP": "🟡"}.get(sentiment, "")
    print(f"\n  {icon} Sentiment: {sentiment}  (Điểm: {r.get('sentiment_score', '?')}/100)")
    print(f"  Tin liên quan: {r.get('relevant_news_count', '?')}/{r.get('news_count', '?')} bài")
    print(f"  Tác động ngắn hạn: {r.get('short_term_impact', '?')}")

    topics = r.get("key_topics", [])
    if topics:
        print(f"  Chủ đề: {' | '.join(topics)}")

    pos = r.get("positive_signals", [])
    neg = r.get("negative_signals", [])
    if pos:
        print(f"  Tích cực: {pos[0]}")
    if neg:
        print(f"  Tiêu cực: {neg[0]}")

    print(f"  Tóm tắt: {r.get('sentiment_summary', '')}")
    print("="*60)
