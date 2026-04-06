"""
risk_manager.py — Phần 5: Lớp bảo vệ (Rule-based)
Dùng rules cứng để chặn lệnh sai lầm của AI (vi phạm quy tắc cốt lõi).
"""

def evaluate_risk(symbol: str, ai_decision: str, vnindex_change_pct: float, foreign_room_pct: float, intraday_amplitude_pct: float) -> dict:
    """
    Đầu vào là phân tích từ AI (ai_decision: MUA/BÁN/CHỜ).
    Trả về dict: {"final_action": str, "override_reason": str}
    """
    if ai_decision != "MUA":
        # Chỉ chặn MUA mới, các lệnh BÁN/CHỜ thì giữ nguyên
        return {"final_action": ai_decision, "override_reason": None}

    # 1. Circuit breaker (Phòng vệ Domino/Margin Call)
    if vnindex_change_pct <= -3.0:
        return {
            "final_action": "CHỜ", 
            "override_reason": f"OVERRIDE RULE: VN-Index chạm mốc giảm mạnh ({vnindex_change_pct}%). Kích hoạt Circuit Breaker, DỪNG MUA MỚI."
        }
        
    # 2. Xả hàng mồi ngoại khối (Foreign Room Trap)
    # Rất phổ biến ở VN: khi Room >95% dễ dính bẫy nước ngoài xả hàng.
    if foreign_room_pct is not None and foreign_room_pct >= 95.0:
         return {
            "final_action": "CHỜ", 
            "override_reason": f"OVERRIDE RULE: Room Khối ngoại đã quá sát mốc đầy ({foreign_room_pct}%). Nguy cơ xả hàng/úp sọt, DỪNG MUA."
        }
        
    # 3. Kẹt biên độ (±7%)
    if intraday_amplitude_pct and intraday_amplitude_pct >= 6.5:
        return {
            "final_action": "CHỜ", 
            "override_reason": f"OVERRIDE RULE: Cổ phiếu đã giật hết biên độ trong phiên ({intraday_amplitude_pct}%). Nguy cơ ăn xả T+3."
        }

    # Pass hết kiểm tra rủi ro -> Đồng ý cho AI mua
    return {"final_action": ai_decision, "override_reason": None}
