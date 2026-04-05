"""
stock_agent_demo.py — Entry point
Chạy: python stock_agent_demo.py
"""

from dotenv import load_dotenv
load_dotenv()

from agent import run_agent, run_agent_lite

if __name__ == "__main__":
    print("""
DEMO: AI AGENT - Phân tích mã cổ phiếu
Nhập bất kỳ mã HOSE/HNX: VNM, HPG, FPT, VIC, MSN...

Chọn chế độ:
  1. Full agent  — Sonnet + tool_use (~10 lần gọi API)
  2. Lite agent  — Haiku + JSON output + cache (tiết kiệm cost)
    """)

    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    mode   = input("Chế độ (1/2, mặc định 2): ").strip() or "2"

    if mode == "1":
        run_agent(
            f"Phân tích kỹ thuật cổ phiếu {symbol}. "
            f"Giá hiện tại bao nhiêu? RSI đang ở đâu? Xu hướng ngắn hạn thế nào?"
        )
    else:
        run_agent_lite(symbol)
