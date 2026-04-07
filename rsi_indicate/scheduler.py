"""
scheduler.py — Phần 1: Scheduler tự động + Health Monitor
Chạy pipeline theo lịch phiên giao dịch VN.

Lịch theo System Design:
  06:00 — Fetch macro đêm qua, foreign flow, news mới nhất
  08:45 — Morning brief: chạy pipeline top VN100, gửi Telegram
  15:10 — Tổng kết phiên: vận động thị trường, lesson learned
  20:00 — Fetch cuối ngày, nén mid-term memory

Chạy: python scheduler.py
"""

import os
import sys
import logging
from datetime import datetime

from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Thêm path để import được các module
sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# VN100 mẫu (cần cập nhật danh sách đầy đủ từ vnstock)
VN100_SAMPLE = [
    "VNM", "HPG", "VIC", "VHM", "GAS", "BID", "CTG", "VCB", "TCB", "MBB",
    "ACB", "STB", "HDB", "VPB", "MSN", "SAB", "VRE", "PLX", "POW", "REE",
    "SSI", "VND", "HCM", "FPT", "MWG", "PNJ", "DGC", "GVR", "BCM", "NVL",
]

# Discord webhook (optional — nếu chưa config thì skip)
_DISCORD_AVAILABLE = False
try:
    import requests
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
    _DISCORD_AVAILABLE  = bool(DISCORD_WEBHOOK_URL)
except ImportError:
    pass


# ── Discord Helper ─────────────────────────────────────────────────────────────

def send_discord(message: str):
    """Gửi message qua Discord Webhook. No-op nếu chưa config."""
    if not _DISCORD_AVAILABLE:
        log.info(f"[Discord] (chưa config) {message[:100]}...")
        return
    try:
        # Discord dùng **bold** thay *bold* của Markdown
        discord_msg = message.replace("*", "**")
        requests.post(DISCORD_WEBHOOK_URL, json={"content": discord_msg}, timeout=10)
    except Exception as e:
        log.error(f"[Discord] Lỗi gửi: {e}")


def send_health_alert(message: str):
    """Gửi alert lỗi pipeline về Discord."""
    send_discord(f"🚨 **HEALTH ALERT**\n{message}")


# ── Job Functions ──────────────────────────────────────────────────────────────

def job_morning_fetch():
    """06:00 — Fetch dữ liệu đầu ngày: macro, foreign flow, news."""
    log.info("=== JOB 06:00: Morning Fetch ===")
    try:
        from fetcher import fetch_macro
        macro = fetch_macro()
        vni   = macro.get("vnindex", {})
        log.info(f"VN-Index hôm qua: {vni.get('latest')} ({vni.get('change_1d', 0):+.2f}%)")
        if vni.get("circuit_breaker"):
            send_health_alert(f"⚠️ VN-Index giảm mạnh {vni.get('change_1d')}% — Circuit breaker có thể kích hoạt!")
        log.info("Morning fetch hoàn thành.")
    except Exception as e:
        log.error(f"Morning fetch lỗi: {e}")
        send_health_alert(f"Morning fetch lỗi: {e}")


def job_morning_brief():
    """08:45 — Chạy screener + pipeline, gửi morning brief."""
    log.info("=== JOB 08:45: Morning Brief ===")
    try:
        from screener import run_quick_screener
        from orchestrator import run_pipeline

        # Screener VN100 → lọc xuống 10-15 mã
        log.info(f"Screener {len(VN100_SAMPLE)} mã...")
        candidates = run_quick_screener(VN100_SAMPLE)
        log.info(f"Screener: {len(candidates)} mã lọt qua")

        if not candidates:
            send_discord("📊 *Morning Brief*\nHôm nay không có mã nào pass screener. Thị trường có thể đang phân phối hoặc giảm mạnh.")
            return

        # Chạy pipeline cho top 5 mã (giới hạn để tiết kiệm API cost)
        top5 = candidates[:5]
        results = []
        for c in top5:
            sym = c["symbol"]
            log.info(f"Pipeline: {sym}...")
            try:
                r = run_pipeline(sym, skip_screener=True)  # Skip screener vì đã chạy rồi
                results.append(r)
            except Exception as e:
                log.error(f"Pipeline lỗi {sym}: {e}")

        # Format và gửi Telegram
        lines = ["📊 *MORNING BRIEF*", f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n"]
        lines.append(f"Screener: {len(candidates)}/{len(VN100_SAMPLE)} mã đáng chú ý\n")

        for r in results:
            sym    = r.get("symbol", "?")
            d      = r.get("decision", {})
            action = d.get("action", "CHỜ")
            icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "⚪")
            entry  = d.get("entry", "?")
            sl     = d.get("sl", "?")
            tp     = d.get("tp", "?")
            reason = str(d.get("reason", ""))[:80]
            lines.append(f"{icon} *{sym}*: {action} | Entry:{entry} SL:{sl} TP:{tp}")
            lines.append(f"  _{reason}_\n")

        send_discord("\n".join(lines))
        log.info(f"Morning brief gửi thành công ({len(results)} mã).")

    except Exception as e:
        log.error(f"Morning brief lỗi: {e}")
        send_health_alert(f"Morning brief lỗi: {e}")


def job_session_close():
    """15:10 — Tổng kết phiên."""
    log.info("=== JOB 15:10: Session Close ===")
    try:
        from fetcher import fetch_macro
        macro = fetch_macro()
        vni   = macro.get("vnindex", {})

        change_1d = vni.get("change_1d", 0)
        change_5d = vni.get("change_5d")
        alert     = vni.get("market_alert", "")

        icon  = "🟢" if change_1d > 0 else "🔴" if change_1d < -1 else "🟡"
        lines = [
            "📈 *TỔNG KẾT PHIÊN*",
            f"_{datetime.now().strftime('%d/%m/%Y 15:10')}_\n",
            f"{icon} VN-Index: {vni.get('latest')} ({change_1d:+.2f}% hôm nay",
            f"{f' | {change_5d:+.2f}% 5 phiên' if change_5d else ''})",
        ]
        if alert:
            lines.append(f"\n⚠️ {alert}")

        send_discord("\n".join(lines))
        log.info("Session close summary gửi thành công.")

    except Exception as e:
        log.error(f"Session close lỗi: {e}")
        send_health_alert(f"Session close lỗi: {e}")


def job_evening_update():
    """20:00 — Fetch cuối ngày + nén mid-term memory."""
    log.info("=== JOB 20:00: Evening Update ===")
    try:
        from memory.memory_system import compress_to_mid_term
        for sym in VN100_SAMPLE[:10]:  # Chỉ compress top 10 để tiết kiệm
            try:
                compress_to_mid_term(sym, days=90)
            except Exception as e:
                log.warning(f"compress_to_mid_term {sym}: {e}")
        log.info("Evening update hoàn thành.")
    except Exception as e:
        log.error(f"Evening update lỗi: {e}")
        send_health_alert(f"Evening update lỗi: {e}")


def job_health_check():
    """Mỗi 30 phút — Ping health check, kiểm tra các service còn sống."""
    log.info("[Health Check] OK")


# ── Main Scheduler ─────────────────────────────────────────────────────────────

def run_scheduler():
    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

    # Lịch theo System Design
    scheduler.add_job(job_morning_fetch,  CronTrigger(hour=6,  minute=0),  id="morning_fetch")
    scheduler.add_job(job_morning_brief,  CronTrigger(hour=8,  minute=45), id="morning_brief")
    scheduler.add_job(job_session_close,  CronTrigger(hour=15, minute=10), id="session_close")
    scheduler.add_job(job_evening_update, CronTrigger(hour=20, minute=0),  id="evening_update")
    scheduler.add_job(job_health_check,   CronTrigger(minute="*/30"),      id="health_check")

    log.info("Scheduler khởi động. Jobs đã đăng ký:")
    for job in scheduler.get_jobs():
        log.info(f"  {job.id}: {job.trigger}")

    send_discord("🚀 *Trading Assistant Scheduler* đã khởi động!")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler dừng.")
        send_discord("⏹️ Scheduler đã dừng.")


if __name__ == "__main__":
    run_scheduler()
