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


def fetch_fundamentals(symbol: str) -> dict:
    """Lấy chỉ số tài chính cơ bản: P/E, P/B, ROE, biên lợi nhuận, tăng trưởng doanh thu"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")

        # Financial ratios (MultiIndex columns)
        ratio_df = stock.finance.ratio(period="quarter", lang="en", dropna=True)

        def _get(df, keyword):
            """Tìm cột theo keyword trong MultiIndex."""
            for col in df.columns:
                if keyword.lower() in str(col).lower():
                    val = df[col].iloc[-1]
                    return float(val) if val is not None and str(val) != "nan" else None
            return None

        pe            = _get(ratio_df, "P/E")
        pb            = _get(ratio_df, "P/B")
        roe           = _get(ratio_df, "ROE")
        roa           = _get(ratio_df, "ROA")
        net_margin    = _get(ratio_df, "Net Profit Margin")
        gross_margin  = _get(ratio_df, "Gross Profit Margin")
        eps           = _get(ratio_df, "EPS (VND)")
        ev_ebitda     = _get(ratio_df, "EV/EBITDA")

        # Revenue YoY growth from income statement
        rev_yoy = None
        try:
            inc_df  = stock.finance.income_statement(period="quarter", lang="en")
            if "Revenue YoY (%)" in inc_df.columns and len(inc_df) > 0:
                rev_yoy = float(inc_df["Revenue YoY (%)"].iloc[-1])
        except Exception:
            pass

        return {
            "symbol":                  symbol.upper(),
            "pe":                      round(pe, 2)           if pe           is not None else None,
            "pb":                      round(pb, 2)           if pb           is not None else None,
            "roe_pct":                 round(roe, 2)          if roe          is not None else None,
            "roa_pct":                 round(roa, 2)          if roa          is not None else None,
            "net_profit_margin_pct":   round(net_margin, 2)   if net_margin   is not None else None,
            "gross_profit_margin_pct": round(gross_margin, 2) if gross_margin is not None else None,
            "eps":                     round(eps, 0)          if eps          is not None else None,
            "ev_ebitda":               round(ev_ebitda, 2)    if ev_ebitda    is not None else None,
            "revenue_yoy_pct":         round(rev_yoy, 2)      if rev_yoy      is not None else None,
            "source":                  "Vnstock finance (quarterly)"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu cơ bản: {str(e)}"}


def fetch_foreign_flow(symbol: str) -> dict:
    """Lấy dữ liệu giao dịch khối ngoại và room nước ngoài (phiên hiện tại)"""
    try:
        from vnstock import Vnstock

        stock = Vnstock().stock(symbol=symbol.upper(), source="VCI")

        # Flatten MultiIndex columns từ price_board
        pb = stock.trading.price_board(symbols_list=[symbol.upper()])
        pb.columns = ["_".join(str(c) for c in col).strip("_") for col in pb.columns]

        def _pb(col):
            return int(pb[col].iloc[0]) if col in pb.columns and pb[col].iloc[0] is not None else None

        foreign_buy  = _pb("match_foreign_buy_volume")
        foreign_sell = _pb("match_foreign_sell_volume")
        buy_value    = _pb("match_foreign_buy_value")
        sell_value   = _pb("match_foreign_sell_value")
        current_room = _pb("match_current_room")
        total_room   = _pb("match_total_room")

        net_vol   = (foreign_buy - foreign_sell) if (foreign_buy is not None and foreign_sell is not None) else None
        net_value = (buy_value  - sell_value)    if (buy_value   is not None and sell_value   is not None) else None

        # Room ratio từ trading_stats
        ts              = stock.company.trading_stats()
        current_ratio   = float(ts["current_holding_ratio"].iloc[0]) if not ts.empty else None
        max_ratio       = float(ts["max_holding_ratio"].iloc[0])      if not ts.empty else None
        room_usage_pct  = round(current_ratio / max_ratio * 100, 1)   if (current_ratio and max_ratio and max_ratio > 0) else None

        # Room risk signal theo system design
        if room_usage_pct is not None:
            if room_usage_pct >= 95:
                room_signal = "CRITICAL — Room >95%, khối ngoại bán ra = dump risk cao"
            elif room_usage_pct >= 90:
                room_signal = "HIGH — Room >90%, cộng thêm premium risk"
            elif room_usage_pct >= 80:
                room_signal = "MEDIUM — Room >80%, theo dõi"
            else:
                room_signal = "NORMAL — Room còn nhiều"
        else:
            room_signal = "N/A"

        net_signal = "MUA RÒNG" if (net_vol and net_vol > 0) else "BÁN RÒNG" if (net_vol and net_vol < 0) else "TRUNG LẬP"

        return {
            "symbol":               symbol.upper(),
            "foreign_buy_volume":   foreign_buy,
            "foreign_sell_volume":  foreign_sell,
            "net_foreign_volume":   net_vol,
            "net_foreign_value":    net_value,
            "current_room":         current_room,
            "total_room":           total_room,
            "holding_ratio_pct":    round(current_ratio * 100, 2) if current_ratio else None,
            "max_holding_ratio_pct": round(max_ratio * 100, 2)   if max_ratio     else None,
            "room_usage_pct":       room_usage_pct,
            "room_signal":          room_signal,
            "net_signal":           net_signal,
            "source":               "Vnstock price_board + trading_stats"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu khối ngoại: {str(e)}"}


def fetch_macro() -> dict:
    """
    Lấy dữ liệu vĩ mô: VN-Index trend + USD/VND.
    Lưu ý: lãi suất SBV không có trong vnstock free — dùng VN-Index làm proxy môi trường thị trường.
    """
    try:
        from vnstock import Vnstock

        v = Vnstock()

        # VN-Index 20 phiên gần nhất
        vnindex_data = {}
        try:
            vni   = v.stock(symbol="VNINDEX", source="VCI")
            end   = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            df    = vni.quote.history(start=start, end=end, interval="1D")
            if df is not None and not df.empty:
                closes    = df["close"].tolist()
                latest    = float(closes[-1])
                prev      = float(closes[-2]) if len(closes) > 1 else latest
                change_1d = round((latest - prev) / prev * 100, 2)
                change_5d = round((latest - closes[-6]) / closes[-6] * 100, 2) if len(closes) >= 6 else None

                # Market regime: giảm >3%/tuần = cảnh báo margin call cascade
                market_alert = None
                if change_5d is not None and change_5d <= -3.0:
                    market_alert = f"CẢNH BÁO: VN-Index giảm {change_5d}% trong 5 phiên — Circuit breaker risk"

                vnindex_data = {
                    "latest":      latest,
                    "change_1d":   change_1d,
                    "change_5d":   change_5d,
                    "market_alert": market_alert,
                    "circuit_breaker": change_1d <= -3.0,  # Giảm >3%/phiên → dừng mua mới
                }
        except Exception:
            pass

        return {
            "vnindex":     vnindex_data,
            "note":        "Lãi suất SBV, tỷ giá chi tiết cần nguồn dữ liệu trả phí",
            "source":      "Vnstock VCI"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu vĩ mô: {str(e)}"}
