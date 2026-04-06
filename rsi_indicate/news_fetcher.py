"""
news_fetcher.py — Crawl tin tức từ CafeF + VnExpress
Trả về list bài báo gần nhất liên quan đến mã cổ phiếu.
"""

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 10


def _crawl_cafef(symbol: str, max_articles: int = 5) -> list:
    """
    Crawl tin tức từ CafeF tìm kiếm theo mã cổ phiếu.
    URL: https://cafef.vn/tim-kiem.chn?keywords={symbol}
    """
    url = f"https://cafef.vn/tim-kiem.chn?keywords={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = []
        for item in soup.select(".item")[:max_articles]:
            title_el   = item.select_one("a.box-category-link-title") or item.select_one("h3 a")
            summary_el = item.select_one("p.sapo") or item.select_one("p")
            link_el    = item.select_one("a[href]")

            title   = title_el.get_text(strip=True)   if title_el   else ""
            summary = summary_el.get_text(strip=True)  if summary_el else ""
            href    = link_el["href"]                  if link_el    else ""

            if not title:
                continue

            # CafeF dùng relative URL
            if href and not href.startswith("http"):
                href = "https://cafef.vn" + href

            articles.append({
                "source":  "CafeF",
                "title":   title,
                "summary": summary[:200],
                "url":     href,
            })

        return articles

    except Exception as e:
        print(f"  [CafeF] Lỗi crawl: {e}")
        return []


def _crawl_vnexpress(symbol: str, max_articles: int = 5) -> list:
    """
    Crawl tin tức từ VnExpress — chuyên mục kinh doanh (cate_code=1017).
    URL: https://timkiem.vnexpress.net/?q={symbol}&cate_code=1017
    """
    url = f"https://timkiem.vnexpress.net/?q={symbol}&cate_code=1017"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        articles = []
        for item in soup.select(".item-news")[:max_articles]:
            title_el   = item.select_one("h3.title-news a") or item.select_one("h2 a")
            summary_el = item.select_one("p.description") or item.select_one("p")
            link_el    = title_el  # title_el đã là <a>

            title   = title_el.get_text(strip=True)   if title_el   else ""
            summary = summary_el.get_text(strip=True)  if summary_el else ""
            href    = link_el["href"]                  if link_el and link_el.get("href") else ""

            if not title:
                continue

            articles.append({
                "source":  "VnExpress",
                "title":   title,
                "summary": summary[:200],
                "url":     href,
            })

        return articles

    except Exception as e:
        print(f"  [VnExpress] Lỗi crawl: {e}")
        return []


def fetch_news(symbol: str, max_per_source: int = 5) -> list:
    """
    Lấy tin tức từ CafeF + VnExpress, gộp lại thành một list.
    Trả về list[dict] với keys: source, title, summary, url
    """
    symbol = symbol.upper()
    print(f"  Crawl CafeF...")
    cafef_articles = _crawl_cafef(symbol, max_per_source)
    print(f"  → {len(cafef_articles)} bài từ CafeF")

    print(f"  Crawl VnExpress...")
    vnex_articles = _crawl_vnexpress(symbol, max_per_source)
    print(f"  → {len(vnex_articles)} bài từ VnExpress")

    all_articles = cafef_articles + vnex_articles
    return all_articles
