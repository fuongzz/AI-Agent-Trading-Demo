"""
Backtest engine — tái sử dụng các hàm indicator từ stock_agent_demo.py
Chiến lược: kết hợp RSI + MA crossover + MACD histogram

Cách chạy:
    python rsi_indicate/backtest.py
"""

import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# Patch pandas compatibility
try:
    import pandas as pd
    if not hasattr(pd.DataFrame, "applymap"):
        pd.DataFrame.applymap = pd.DataFrame.map
except ImportError:
    pass

# Import các hàm indicator đã có
from stock_agent_demo import (
    fetch_ohlcv,
    calculate_rsi,
    calculate_moving_average,
    calculate_macd,
    analyze_volume,
)


# ── Cấu hình chiến lược ──────────────────────────────────────────────────────

STRATEGY = {
    # RSI
    "rsi_buy":        30,   # RSI dưới ngưỡng này → tín hiệu MUA
    "rsi_sell":       70,   # RSI trên ngưỡng này → tín hiệu BÁN

    # MA crossover: MA5 cắt lên MA20 → MUA, cắt xuống → BÁN
    "use_ma_cross":   True,

    # MACD histogram dương → xác nhận MUA, âm → xác nhận BÁN
    "use_macd":       True,

    # Yêu cầu bao nhiêu tín hiệu trùng nhau mới vào lệnh (1, 2 hoặc 3)
    "min_signals":    2,

    # Quản lý vốn
    "capital":        100_000_000,  # Vốn ban đầu (VND)
    "position_pct":   0.9,          # Dùng 90% vốn mỗi lệnh
    "stop_loss_pct":  0.07,         # Cắt lỗ -7%
    "take_profit_pct": 0.15,        # Chốt lời +15%
}

# Số phiên tối thiểu cần có trước khi bắt đầu tính tín hiệu (đủ cho MACD)
WARMUP = 40


# ── Hàm tính tín hiệu ────────────────────────────────────────────────────────

def compute_signal(closes: list, volumes: list) -> str:
    """
    Tính tín hiệu BUY / SELL / HOLD từ dữ liệu lịch sử.
    Chỉ dùng dữ liệu đến ngày hiện tại (không lookahead bias).
    Trả về: 'BUY', 'SELL', hoặc 'HOLD'
    """
    if len(closes) < WARMUP:
        return "HOLD"

    buy_signals  = 0
    sell_signals = 0

    # 1. RSI
    rsi_result = calculate_rsi(closes)
    if "error" not in rsi_result:
        rsi = rsi_result["rsi"]
        if rsi < STRATEGY["rsi_buy"]:
            buy_signals += 1
        elif rsi > STRATEGY["rsi_sell"]:
            sell_signals += 1

    # 2. MA crossover
    if STRATEGY["use_ma_cross"] and len(closes) >= 20:
        ma5_now  = calculate_moving_average(closes, 5)["ma"]
        ma20_now = calculate_moving_average(closes, 20)["ma"]
        ma5_prev = calculate_moving_average(closes[:-1], 5)["ma"]
        ma20_prev = calculate_moving_average(closes[:-1], 20)["ma"]

        # Golden cross: MA5 cắt lên MA20
        if ma5_prev <= ma20_prev and ma5_now > ma20_now:
            buy_signals += 1
        # Death cross: MA5 cắt xuống MA20
        elif ma5_prev >= ma20_prev and ma5_now < ma20_now:
            sell_signals += 1
        # Xu hướng hiện tại
        elif ma5_now > ma20_now:
            buy_signals += 0.5
        else:
            sell_signals += 0.5

    # 3. MACD histogram
    if STRATEGY["use_macd"]:
        macd_result = calculate_macd(closes)
        if "error" not in macd_result:
            hist = macd_result["histogram"]
            if hist > 0:
                buy_signals += 1
            elif hist < 0:
                sell_signals += 1

    # Quyết định
    if buy_signals >= STRATEGY["min_signals"] and buy_signals > sell_signals:
        return "BUY"
    elif sell_signals >= STRATEGY["min_signals"] and sell_signals > buy_signals:
        return "SELL"
    return "HOLD"


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_backtest(symbol: str, days: int = 365) -> dict:
    """
    Chạy backtest walk-forward trên dữ liệu lịch sử.

    Args:
        symbol: Mã cổ phiếu (VD: 'VNM')
        days:   Số ngày lịch sử để test

    Returns:
        Dict chứa kết quả và danh sách giao dịch
    """
    print(f"\n{'='*60}")
    print(f"BACKTEST: {symbol.upper()} | {days} ngày lịch sử")
    print(f"Chiến lược: RSI({STRATEGY['rsi_buy']}/{STRATEGY['rsi_sell']}) "
          f"+ MA5/20 cross + MACD | Min signals: {STRATEGY['min_signals']}")
    print("="*60)

    # Lấy dữ liệu
    print("Đang lấy dữ liệu lịch sử...")
    data = fetch_ohlcv(symbol, days=days)
    if "error" in data:
        print(f"Lỗi: {data['error']}")
        return {}

    closes  = data["closes"]
    highs   = data["highs"]
    lows    = data["lows"]
    volumes = data["volumes"]
    total   = len(closes)

    if total < WARMUP + 10:
        print(f"Không đủ dữ liệu (cần ít nhất {WARMUP + 10} phiên, có {total})")
        return {}

    print(f"Có {total} phiên dữ liệu. Bắt đầu simulate từ phiên {WARMUP + 1}...")

    # Trạng thái portfolio
    capital      = float(STRATEGY["capital"])
    capital_init = capital
    position     = 0        # Số cổ phiếu đang nắm giữ
    entry_price  = 0.0
    trades       = []       # Lịch sử giao dịch
    equity_curve = []       # Giá trị portfolio theo từng phiên

    prev_signal = "HOLD"

    # Walk-forward: mỗi bước i = cuối phiên i, dùng dữ liệu [0..i]
    for i in range(WARMUP, total):
        price   = closes[i]
        signal  = compute_signal(closes[:i+1], volumes[:i+1])

        # Kiểm tra stop-loss / take-profit nếu đang giữ cổ
        if position > 0:
            change_pct = (price - entry_price) / entry_price
            if change_pct <= -STRATEGY["stop_loss_pct"]:
                signal = "SELL"  # Cắt lỗ bắt buộc
            elif change_pct >= STRATEGY["take_profit_pct"]:
                signal = "SELL"  # Chốt lời bắt buộc

        # Thực hiện giao dịch
        if signal == "BUY" and position == 0 and prev_signal != "BUY":
            # Mua vào
            invest   = capital * STRATEGY["position_pct"]
            position = invest / price
            entry_price = price
            capital -= invest
            trades.append({
                "type":        "BUY",
                "session":     i,
                "price":       round(price, 2),
                "shares":      round(position, 2),
                "capital_left": round(capital, 0),
            })

        elif signal == "SELL" and position > 0:
            # Bán ra
            proceeds = position * price
            pnl      = proceeds - (position * entry_price)
            pnl_pct  = round((price - entry_price) / entry_price * 100, 2)
            capital += proceeds
            trades.append({
                "type":      "SELL",
                "session":   i,
                "price":     round(price, 2),
                "pnl":       round(pnl, 0),
                "pnl_pct":   f"{pnl_pct}%",
                "capital":   round(capital, 0),
            })
            position    = 0
            entry_price = 0.0

        # Equity curve: giá trị tổng (tiền mặt + cổ phiếu đang giữ)
        equity = capital + position * price
        equity_curve.append(round(equity, 0))
        prev_signal = signal

    # Đóng vị thế cuối nếu còn
    if position > 0:
        final_price = closes[-1]
        proceeds    = position * final_price
        pnl         = proceeds - (position * entry_price)
        pnl_pct     = round((final_price - entry_price) / entry_price * 100, 2)
        capital    += proceeds
        trades.append({
            "type":    "SELL (close)",
            "session": total - 1,
            "price":   round(final_price, 2),
            "pnl":     round(pnl, 0),
            "pnl_pct": f"{pnl_pct}%",
            "capital": round(capital, 0),
        })

    # ── Tính performance metrics ─────────────────────────────────────────────

    sell_trades = [t for t in trades if "SELL" in t["type"]]
    n_trades    = len(sell_trades)
    wins        = [t for t in sell_trades if t["pnl"] > 0]
    losses      = [t for t in sell_trades if t["pnl"] <= 0]
    win_rate    = round(len(wins) / n_trades * 100, 1) if n_trades > 0 else 0

    total_pnl    = sum(t["pnl"] for t in sell_trades)
    total_return = round((capital - capital_init) / capital_init * 100, 2)

    avg_win  = round(sum(t["pnl"] for t in wins) / len(wins), 0) if wins else 0
    avg_loss = round(sum(t["pnl"] for t in losses) / len(losses), 0) if losses else 0

    # Buy & hold để so sánh
    bh_return = round((closes[-1] - closes[WARMUP]) / closes[WARMUP] * 100, 2)

    # Max drawdown từ equity curve
    max_dd = 0.0
    peak   = equity_curve[0] if equity_curve else capital_init
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = round(max_dd * 100, 2)

    results = {
        "symbol":           symbol.upper(),
        "periods_tested":   total - WARMUP,
        "capital_init":     capital_init,
        "capital_final":    round(capital, 0),
        "total_return_pct": f"{total_return}%",
        "buy_hold_return":  f"{bh_return}%",
        "alpha":            f"{round(total_return - bh_return, 2)}%",
        "n_trades":         n_trades,
        "win_rate":         f"{win_rate}%",
        "avg_win_vnd":      avg_win,
        "avg_loss_vnd":     avg_loss,
        "profit_factor":    round(-avg_win / avg_loss, 2) if avg_loss < 0 else "∞",
        "max_drawdown":     f"{max_dd_pct}%",
        "trades":           trades,
    }

    return results


# ── In kết quả ───────────────────────────────────────────────────────────────

def print_results(results: dict):
    if not results:
        return

    print(f"\n{'='*60}")
    print(f"KẾT QUẢ BACKTEST: {results['symbol']}")
    print(f"{'='*60}")
    print(f"Số phiên test      : {results['periods_tested']}")
    print(f"Vốn ban đầu        : {results['capital_init']:,.0f} VND")
    print(f"Vốn cuối           : {results['capital_final']:,.0f} VND")
    print(f"Lợi nhuận chiến lược: {results['total_return_pct']}")
    print(f"Lợi nhuận Buy&Hold : {results['buy_hold_return']}")
    print(f"Alpha (vượt trội)  : {results['alpha']}")
    print(f"{'─'*40}")
    print(f"Số giao dịch       : {results['n_trades']}")
    print(f"Tỷ lệ thắng        : {results['win_rate']}")
    print(f"Lãi TB/lệnh thắng  : {results['avg_win_vnd']:,.0f} VND")
    print(f"Lỗ TB/lệnh thua    : {results['avg_loss_vnd']:,.0f} VND")
    print(f"Profit Factor      : {results['profit_factor']}")
    print(f"Max Drawdown       : {results['max_drawdown']}")
    print(f"{'─'*40}")
    print(f"Chi tiết giao dịch:")
    for t in results["trades"]:
        if "SELL" in t["type"]:
            sign = "+" if t["pnl"] > 0 else ""
            print(f"  Phiên {t['session']:3d} | {t['type']:12s} | Giá: {t['price']:>10,.1f} "
                  f"| P&L: {sign}{t['pnl']:>12,.0f} VND ({t['pnl_pct']})")
        else:
            print(f"  Phiên {t['session']:3d} | {t['type']:12s} | Giá: {t['price']:>10,.1f}")
    print("="*60)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
BACKTEST — Phân tích hiệu quả chiến lược giao dịch
Chiến lược: RSI + MA5/MA20 crossover + MACD histogram
    """)

    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    days   = input("Số ngày lịch sử (vd: 365, mặc định 365): ").strip()
    days   = int(days) if days.isdigit() else 365

    results = run_backtest(symbol, days=days)
    print_results(results)
