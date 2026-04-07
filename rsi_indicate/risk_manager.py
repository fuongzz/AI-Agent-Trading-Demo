"""
risk_manager.py — Phần 5: Lớp bảo vệ (Rule-based, deterministic)
Dùng rules cứng để chặn lệnh sai lầm của AI (vi phạm quy tắc cốt lõi VN).

KHÔNG dùng LLM — phải deterministic, không được hallucinate.
Override MỌI THỨ agent nói khi vi phạm rule.

Rules theo System Design:
  1. Biên độ ±7% — đã dùng >5% biên độ → giảm sizing
  2. T+3 constraint — không tính thanh khoản cổ đã mua trong 3 ngày
  3. Room nước ngoài >95% → giảm sizing 50%, >90% → cộng premium risk
  4. Circuit breaker — VN-Index giảm >3%/phiên → dừng mua mới
  5. ATO/ATC — chỉ vào lệnh 9:15–11:30 và 13:00–14:30, không vào 5 phút cuối
"""

from datetime import datetime, timedelta, timezone


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_vn_time() -> datetime:
    """Giờ hiện tại theo múi giờ VN (UTC+7)."""
    return datetime.now(timezone(timedelta(hours=7)))


def _is_valid_trading_window() -> dict:
    """
    Kiểm tra xem thời điểm hiện tại có phải khung giờ hợp lệ để vào lệnh không.
    Theo system design: 9:15–11:30 và 13:00–14:30 (không vào 5 phút cuối = 14:25–14:30).
    Returns: {"valid": bool, "reason": str, "current_time": str}
    """
    now  = _get_vn_time()
    time_str = now.strftime("%H:%M")

    # Cuối tuần
    if now.weekday() >= 5:
        return {"valid": False, "reason": f"Cuối tuần ({['T2','T3','T4','T5','T6','T7','CN'][now.weekday()]})", "current_time": time_str}

    h, m = now.hour, now.minute
    total_minutes = h * 60 + m

    # Buổi sáng: 9:15 – 11:30
    morning_open  = 9  * 60 + 15
    morning_close = 11 * 60 + 30

    # Buổi chiều: 13:00 – 14:25 (tránh 5 phút cuối ATC)
    afternoon_open  = 13 * 60 + 0
    afternoon_close = 14 * 60 + 25  # Không vào 14:25–14:30 (ATC zone)

    if morning_open <= total_minutes <= morning_close:
        return {"valid": True, "reason": "Khung sáng hợp lệ", "current_time": time_str}
    elif afternoon_open <= total_minutes <= afternoon_close:
        return {"valid": True, "reason": "Khung chiều hợp lệ", "current_time": time_str}
    elif total_minutes > afternoon_close and total_minutes <= 14 * 60 + 30:
        return {"valid": False, "reason": f"ATC zone {time_str} — Không vào 5 phút cuối phiên (14:25–14:30)", "current_time": time_str}
    elif total_minutes < morning_open:
        return {"valid": False, "reason": f"Chưa mở cửa (giờ hiện tại: {time_str}, mở cửa 9:15)", "current_time": time_str}
    else:
        return {"valid": False, "reason": f"Ngoài giờ giao dịch ({time_str})", "current_time": time_str}


def check_t3_conflict(symbol: str, recent_buys: list) -> dict:
    """
    Kiểm tra T+3: nếu đã mua {symbol} trong 3 ngày giao dịch gần đây,
    thanh khoản chưa về — không nên mua thêm cùng mã.

    Args:
        symbol: Mã cổ phiếu
        recent_buys: List[{"symbol": str, "date": "YYYY-MM-DD"}] — lịch sử mua gần đây

    Returns: {"conflict": bool, "bought_date": str | None}
    """
    if not recent_buys:
        return {"conflict": False, "bought_date": None}

    today = _get_vn_time().date()
    symbol = symbol.upper()

    for buy in recent_buys:
        if buy.get("symbol", "").upper() != symbol:
            continue
        try:
            bought_date = datetime.strptime(buy["date"], "%Y-%m-%d").date()
            days_diff = (today - bought_date).days
            if days_diff <= 3:
                return {
                    "conflict":    True,
                    "bought_date": buy["date"],
                    "days_ago":    days_diff,
                }
        except (ValueError, KeyError):
            continue

    return {"conflict": False, "bought_date": None}


# ── Main Risk Evaluator ────────────────────────────────────────────────────────

def evaluate_risk(
    symbol:                str,
    ai_decision:           str,
    vnindex_change_pct:    float,
    foreign_room_pct:      float,
    intraday_amplitude_pct: float = 0,
    recent_buys:           list  = None,
    check_trading_window:  bool  = True,
) -> dict:
    """
    Evaluate risk cho một quyết định của AI.

    Args:
        symbol:                 Mã cổ phiếu
        ai_decision:            "MUA" / "BÁN" / "CHỜ"
        vnindex_change_pct:     % thay đổi VN-Index trong phiên hôm nay
        foreign_room_pct:       % room nước ngoài đã dùng (0-100)
        intraday_amplitude_pct: % biên độ giá đã dùng trong phiên (0-7)
        recent_buys:            Lịch sử mua gần đây (T+3 check)
        check_trading_window:   Có kiểm tra khung giờ giao dịch không

    Returns:
        {"final_action": str, "override_reason": str | None,
         "warnings": list, "sizing_modifier": float}
    """
    warnings       = []
    sizing_modifier = 1.0  # 1.0 = giữ nguyên, 0.5 = giảm sizing 50%

    # ── Chỉ block MUA — BÁN/CHỜ không cần filter ────────────────────────────
    if ai_decision != "MUA":
        return {
            "final_action":    ai_decision,
            "override_reason": None,
            "warnings":        [],
            "sizing_modifier": 1.0,
        }

    # ── Rule 1: Circuit breaker (Phòng vệ Margin Call Cascade) ───────────────
    if vnindex_change_pct is not None and vnindex_change_pct <= -3.0:
        return {
            "final_action":    "CHỜ",
            "override_reason": f"[Rule 1] CIRCUIT BREAKER: VN-Index giảm {vnindex_change_pct:.2f}% — dừng tất cả lệnh MUA mới.",
            "warnings":        warnings,
            "sizing_modifier": 0.0,
        }

    # ── Rule 2: Foreign Room Trap ─────────────────────────────────────────────
    if foreign_room_pct is not None:
        if foreign_room_pct >= 95.0:
            return {
                "final_action":    "CHỜ",
                "override_reason": f"[Rule 2] FOREIGN ROOM TRAP: Room {foreign_room_pct:.1f}% — khối ngoại không mua được nữa, nguy cơ dump cao.",
                "warnings":        warnings,
                "sizing_modifier": 0.0,
            }
        elif foreign_room_pct >= 90.0:
            sizing_modifier *= 0.5
            warnings.append(f"[Rule 2] Room {foreign_room_pct:.1f}% cao — giảm sizing 50%, cộng premium risk.")

    # ── Rule 3: Biên độ ±7% (Intraday Amplitude) ─────────────────────────────
    if intraday_amplitude_pct and intraday_amplitude_pct >= 6.5:
        return {
            "final_action":    "CHỜ",
            "override_reason": f"[Rule 3] BIÊN ĐỘ HẾT: Cổ phiếu đã dùng {intraday_amplitude_pct:.1f}% biên độ — nguy cơ ăn xả T+3.",
            "warnings":        warnings,
            "sizing_modifier": 0.0,
        }
    elif intraday_amplitude_pct and intraday_amplitude_pct >= 5.0:
        sizing_modifier *= 0.7
        warnings.append(f"[Rule 3] Biên độ {intraday_amplitude_pct:.1f}% — giảm sizing 30%.")

    # ── Rule 4: T+3 Constraint ────────────────────────────────────────────────
    t3_check = check_t3_conflict(symbol, recent_buys or [])
    if t3_check["conflict"]:
        warnings.append(
            f"[Rule 4] T+3: Đã mua {symbol} ngày {t3_check['bought_date']} "
            f"({t3_check['days_ago']} ngày trước) — thanh khoản chưa về, cân nhắc không mua thêm."
        )
        sizing_modifier *= 0.5  # Giảm sizing nhưng không block hoàn toàn

    # ── Rule 5: ATO/ATC Time Window ───────────────────────────────────────────
    if check_trading_window:
        tw = _is_valid_trading_window()
        if not tw["valid"]:
            return {
                "final_action":    "CHỜ",
                "override_reason": f"[Rule 5] NGOÀI KHUNG GIỜ: {tw['reason']} — không vào lệnh.",
                "warnings":        warnings,
                "sizing_modifier": 0.0,
            }

    # ── Tất cả rules đều pass ─────────────────────────────────────────────────
    return {
        "final_action":    "MUA",
        "override_reason": None,
        "warnings":        warnings,
        "sizing_modifier": round(sizing_modifier, 2),
    }
