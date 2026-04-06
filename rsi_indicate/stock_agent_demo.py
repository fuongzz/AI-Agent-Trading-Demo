"""
stock_agent_demo.py — Entry point chính
Chạy: python stock_agent_demo.py  hoặc  run.bat
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from orchestrator import run_pipeline

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║       MULTI-AGENT TRADING SYSTEM — VN STOCK MARKET       ║
║                                                          ║
║  Tầng I-A : PTKT Agent    (chỉ báo kỹ thuật)             ║
║  Tầng I-B : Sentiment     (crawl CafeF + VnExpress)      ║
║  Tầng II  : Debate Agent  (Bull vs Bear)                 ║
║  Tầng III : Trader Agent  (quyết định cuối)              ║
╚══════════════════════════════════════════════════════════╝
    """)

    symbol = input("Nhập mã cổ phiếu (vd: VNM, HPG, FPT): ").strip().upper() or "VNM"
    force  = input("Bỏ qua cache, chạy lại từ đầu? (y/N): ").strip().lower() == "y"

    run_pipeline(symbol, force=force)
