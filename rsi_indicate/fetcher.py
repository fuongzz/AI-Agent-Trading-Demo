"""
fetcher.py — Lấy dữ liệu từ Vnstock API
"""

from datetime import datetime, timedelta

# Patch pandas compatibility
try:
    import pandas as pd
    if not hasattr(pd.DataFrame, "applymap"):
        pd.DataFrame.applymap = pd.DataFrame.map
except ImportError:
    pass


def fetch_ohlcv(symbol: str, days: int = 90) -> dict:
    """Lấy dữ liệu giá lịch sử OHLCV từ vnstock"""
    try:
        from vnstock import Vnstock

        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        df = stock.quote.history(start=start, end=end, interval="1D")

        if df is None or df.empty:
            return {"error": f"Không có dữ liệu cho mã {symbol}"}

        closes  = df["close"].tolist()
        highs   = df["high"].tolist()
        lows    = df["low"].tolist()
        volumes = df["volume"].tolist()
        latest  = df.iloc[-1]
        prev    = df.iloc[-2] if len(df) > 1 else df.iloc[-1]

        change = round(float(latest["close"]) - float(prev["close"]), 2)
        pct    = round((change / float(prev["close"])) * 100, 2)

        return {
            "symbol":         symbol.upper(),
            "latest_price":   float(latest["close"]),
            "open":           float(latest["open"]),
            "high":           float(latest["high"]),
            "low":            float(latest["low"]),
            "volume":         int(latest["volume"]),
            "change":         change,
            "change_pct":     f"{pct}%",
            "closes":         closes,
            "highs":          highs,
            "lows":           lows,
            "volumes":        volumes,
            "total_sessions": len(closes),
            "date":           str(latest.name)[:10] if hasattr(latest, "name") else end,
            "source":         "Vnstock / VCI"
        }

    except ImportError:
        return {"error": "Chưa cài vnstock. Chạy: pip install vnstock"}
    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu: {str(e)}"}


def fetch_realtime(symbol: str) -> dict:
    """Lấy giá realtime trong giờ giao dịch (9:00–15:00)"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        df = stock.quote.intraday(symbol=symbol.upper(), show_log=False)

        if df is None or df.empty:
            return {
                "note": "Không có dữ liệu realtime — có thể ngoài giờ giao dịch (9:00–15:00)",
                "symbol": symbol.upper()
            }

        latest = df.iloc[-1]
        return {
            "symbol":         symbol.upper(),
            "realtime_price": float(latest.get("price", latest.get("close", 0))),
            "volume":         int(latest.get("volume", 0)),
            "time":           str(latest.get("time", "")),
            "source":         "Vnstock intraday"
        }

    except Exception as e:
        return {"error": f"Lỗi realtime: {str(e)} — Thử ngoài giờ giao dịch"}


def fetch_company_info(symbol: str) -> dict:
    """Lấy thông tin cơ bản công ty"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")
        info  = stock.company.overview()

        if info is None or (hasattr(info, "empty") and info.empty):
            return {"error": "Không lấy được thông tin công ty"}

        row = info.iloc[0] if hasattr(info, "iloc") else info
        return {
            "symbol":   symbol.upper(),
            "company":  str(row.get("short_name", row.get("company_name", "N/A"))),
            "industry": str(row.get("industry_name", row.get("sector", "N/A"))),
            "exchange": str(row.get("exchange", "N/A")),
            "source":   "Vnstock company info"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy thông tin công ty: {str(e)}"}
