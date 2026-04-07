"""
discord_bot.py — Discord Bot 2 chiều
Thay thế Telegram Bot theo System Design.

PUSH (tự động):
  - Morning brief 08:45 (qua scheduler.py + webhook)
  - Alert realtime trong phiên
  - Tổng kết phiên 15:10

PULL (người dùng hỏi, prefix = !):
  !gia <MÃ>          — Giá hiện tại (nhanh <5s)
  !phan-tich <MÃ>    — Phân tích TA + FA song song (<20s)
  !full <MÃ>         — Phân tích toàn diện full pipeline (<60s)
  !screener          — Chạy screener VN100 mẫu
  !help              — Hiện danh sách lệnh

Setup:
  1. Tạo Discord Bot tại https://discord.com/developers/applications
  2. Bật "Message Content Intent" trong Bot settings
  3. Lấy BOT_TOKEN, CHANNEL_ID, WEBHOOK_URL
  4. Thêm vào .env:
       DISCORD_BOT_TOKEN=...
       DISCORD_CHANNEL_ID=...
       DISCORD_WEBHOOK_URL=...
  5. Chạy: python discord_bot.py

Cài đặt: pip install discord.py
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

try:
    import discord
    from discord.ext import commands
except ImportError:
    print("Chưa cài discord.py. Chạy: pip install discord.py")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID  = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = 1800) -> str:
    """Discord message limit là 2000 chars."""
    return text[:max_len] + "..." if len(text) > max_len else text


async def _send_typing_then(ctx, coro):
    """Hiện typing indicator trong khi xử lý."""
    async with ctx.typing():
        return await coro


# ── Tier 1: Đơn giản <5s — Giá hiện tại ──────────────────────────────────────

@bot.command(name="gia", aliases=["price", "g"])
async def cmd_price(ctx, symbol: str = None):
    """!gia <MÃ> — Lấy giá hiện tại"""
    if not symbol:
        await ctx.send("❌ Cú pháp: `!gia VNM`")
        return

    symbol = symbol.upper()
    async with ctx.typing():
        try:
            from fetcher import fetch_ohlcv, fetch_realtime
            rt   = fetch_realtime(symbol)
            ohlcv = fetch_ohlcv(symbol, days=5)

            if "error" in ohlcv:
                await ctx.send(f"❌ Lỗi: {ohlcv['error']}")
                return

            price  = rt.get("realtime_price") or ohlcv.get("latest_price")
            change = ohlcv.get("change", 0)
            pct    = ohlcv.get("change_pct", "0%")
            icon   = "🟢" if change >= 0 else "🔴"

            embed = discord.Embed(
                title=f"{icon} {symbol}",
                color=discord.Color.green() if change >= 0 else discord.Color.red()
            )
            embed.add_field(name="Giá", value=f"**{price:,.1f}**", inline=True)
            embed.add_field(name="Thay đổi", value=f"{'+' if change >= 0 else ''}{change:.2f} ({pct})", inline=True)
            embed.add_field(name="Volume", value=f"{ohlcv.get('volume', 0):,}", inline=True)
            embed.set_footer(text=f"Cập nhật: {datetime.now().strftime('%H:%M:%S')} | {ohlcv.get('source', '')}")

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Lỗi: {e}")


# ── Tier 2: Trung bình <20s — Phân tích TA + FA ───────────────────────────────

@bot.command(name="phan-tich", aliases=["pt", "analyze"])
async def cmd_analyze(ctx, symbol: str = None):
    """!phan-tich <MÃ> — Phân tích TA + FA song song"""
    if not symbol:
        await ctx.send("❌ Cú pháp: `!phan-tich VNM`")
        return

    symbol = symbol.upper()
    msg = await ctx.send(f"⏳ Đang phân tích **{symbol}**... (TA + FA, ~15-20s)")

    try:
        # Chạy TA và FA song song
        loop = asyncio.get_event_loop()
        from analysts.ptkt_agent import run as run_ptkt
        from analysts.fa_agent   import run as run_fa

        ta_task = loop.run_in_executor(None, run_ptkt, symbol)
        fa_task = loop.run_in_executor(None, run_fa,   symbol)
        ta_report, fa_report = await asyncio.gather(ta_task, fa_task)

        # Format kết quả
        p  = ta_report.get("price", {})
        s  = ta_report.get("signals", {})
        r  = ta_report.get("recommendation", {})
        fa = fa_report or {}

        action = r.get("action", "CHỜ")
        icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "⚪")
        color  = {"MUA": discord.Color.green(), "BÁN": discord.Color.red(), "CHỜ": discord.Color.yellow()}.get(action, discord.Color.greyple())

        embed = discord.Embed(
            title=f"{icon} Phân tích {symbol} — {action}",
            description=f"Công ty: {ta_report.get('company')} ({ta_report.get('exchange')})",
            color=color
        )

        # TA signals
        embed.add_field(
            name="📊 Kỹ thuật",
            value=(f"RSI: {s.get('rsi', {}).get('value')} → {s.get('rsi', {}).get('signal', '')[:30]}\n"
                   f"MA: {s.get('ma', {}).get('trend', '')[:30]}\n"
                   f"Vol: {s.get('volume', {}).get('signal', '')[:40]}"),
            inline=True
        )

        # FA summary
        fa_verdict = fa.get("valuation_verdict", "N/A")
        fa_icon    = {"UNDERVALUED": "🟢", "OVERVALUED": "🔴", "FAIR_VALUE": "🟡"}.get(fa_verdict, "⚪")
        embed.add_field(
            name="📈 Cơ bản",
            value=(f"{fa_icon} {fa_verdict}\n"
                   f"Chất lượng: {fa.get('quality_score', '?')}/100\n"
                   f"Triển vọng: {fa.get('growth_outlook', '?')}"),
            inline=True
        )

        # Recommendation
        if action == "MUA":
            embed.add_field(
                name=f"{icon} Khuyến nghị",
                value=(f"Entry: **{r.get('entry')}** | SL: {r.get('sl')} | TP: {r.get('tp')}\n"
                       f"Tin cậy: {r.get('confidence')}"),
                inline=False
            )
        else:
            embed.add_field(name=f"{icon} Khuyến nghị", value=f"{action} — {r.get('confidence')}", inline=False)

        embed.add_field(name="Lý do", value=str(r.get("reason", ""))[:200], inline=False)
        embed.set_footer(text=f"Ngày: {ta_report.get('date')} | Chỉ mang tính tham khảo, không phải tư vấn đầu tư")

        await msg.edit(content="", embed=embed)

    except Exception as e:
        log.error(f"phan-tich {symbol} lỗi: {e}", exc_info=True)
        await msg.edit(content=f"❌ Lỗi phân tích {symbol}: {e}")


# ── Tier 3: Phức tạp <60s — Full Pipeline ─────────────────────────────────────

@bot.command(name="full", aliases=["f"])
async def cmd_full(ctx, symbol: str = None):
    """!full <MÃ> — Phân tích toàn diện full pipeline (~45-60s)"""
    if not symbol:
        await ctx.send("❌ Cú pháp: `!full VNM`")
        return

    symbol = symbol.upper()
    msg    = await ctx.send(f"⏳ Chạy full pipeline **{symbol}**... (~45-60s, xin chờ)")

    try:
        loop = asyncio.get_event_loop()
        from orchestrator import run_pipeline

        result = await loop.run_in_executor(None, run_pipeline, symbol)

        d      = result.get("decision", {})
        action = d.get("action", "CHỜ")
        icon   = {"MUA": "🟢", "BÁN": "🔴", "CHỜ": "🟡"}.get(action, "⚪")
        color  = {"MUA": discord.Color.green(), "BÁN": discord.Color.red(), "CHỜ": discord.Color.yellow()}.get(action, discord.Color.greyple())

        dbt  = result.get("debate", {})
        bull = dbt.get("bull", {})
        bear = dbt.get("bear", {})
        syn  = dbt.get("summary", {})
        snt  = result.get("sentiment", {})
        scr  = result.get("screen_result", {})

        embed = discord.Embed(
            title=f"{icon} Full Analysis: {symbol} — **{action}**",
            color=color,
            timestamp=datetime.now()
        )

        # Screener
        embed.add_field(
            name="🔍 Screener",
            value=f"Score: {scr.get('score', 0)} | Regime: {scr.get('regime', '?')}\n{scr.get('reason', '')[:80]}",
            inline=False
        )

        # Debate
        embed.add_field(
            name="⚔️ Debate",
            value=(f"Bull: {bull.get('score', '?')}/100 | Bear: {bear.get('score', '?')}/100\n"
                   f"Dominant: **{syn.get('dominant_side', '?')}** | Uncertainty: {syn.get('uncertainty_level', '?')}\n"
                   f"{syn.get('market_context', '')[:100]}"),
            inline=False
        )

        # Sentiment
        if snt and not snt.get("skipped"):
            snt_icon = {"TÍCH CỰC": "🟢", "TIÊU CỰC": "🔴", "TRUNG LẬP": "🟡"}.get(snt.get("overall_sentiment"), "⚪")
            embed.add_field(
                name="📰 Sentiment",
                value=f"{snt_icon} {snt.get('overall_sentiment')} ({snt.get('sentiment_score')}/100)\n{snt.get('sentiment_summary', '')[:100]}",
                inline=True
            )

        # Decision
        if d.get("risk_override"):
            embed.add_field(name="🛡️ Risk Override", value=d["risk_override"][:150], inline=False)
        elif action == "MUA":
            embed.add_field(
                name=f"{icon} Quyết định",
                value=(f"Entry: **{d.get('entry')}** | SL: {d.get('sl')} | TP: {d.get('tp')}\n"
                       f"R/R: 1:{d.get('risk_reward')} | {d.get('holding_period', '')} | {d.get('confidence', '')}"),
                inline=False
            )
        embed.add_field(name="Lý do", value=str(d.get("reason", ""))[:300], inline=False)

        for w in d.get("risk_warnings", []):
            embed.add_field(name="⚠️ Risk Warning", value=w[:150], inline=False)

        elapsed = result.get("elapsed_sec", "?")
        embed.set_footer(text=f"Thời gian: {elapsed}s | Chỉ mang tính tham khảo, không phải tư vấn đầu tư")

        await msg.edit(content="", embed=embed)

    except Exception as e:
        log.error(f"full pipeline {symbol} lỗi: {e}", exc_info=True)
        await msg.edit(content=f"❌ Lỗi full pipeline {symbol}: {e}")


# ── Screener command ───────────────────────────────────────────────────────────

@bot.command(name="screener", aliases=["sc"])
async def cmd_screener(ctx):
    """!screener — Chạy Domain Knowledge Screener trên VN100 mẫu"""
    from scheduler import VN100_SAMPLE
    msg = await ctx.send(f"⏳ Screener {len(VN100_SAMPLE)} mã VN100...")

    try:
        loop = asyncio.get_event_loop()
        from screener import run_quick_screener
        results = await loop.run_in_executor(None, run_quick_screener, VN100_SAMPLE)

        if not results:
            await msg.edit(content="📊 Không có mã nào pass screener hôm nay.")
            return

        lines = [f"📊 **Screener Results** — {len(results)}/{len(VN100_SAMPLE)} mã lọt qua\n"]
        for r in results[:15]:  # Giới hạn 15 mã
            regime_icon = "🚀" if "UPTREND" in r.get("regime", "") else "💥" if "DOWN" in r.get("regime", "") else "⚖️"
            score = r.get("score", 0)
            score_str = f"+{score}" if score > 0 else str(score)
            patterns = " | ".join(r.get("patterns", [])[:2])
            lines.append(f"{regime_icon} **{r['symbol']}** (score:{score_str}) — {patterns[:60]}")

        await msg.edit(content=_truncate("\n".join(lines)))

    except Exception as e:
        await msg.edit(content=f"❌ Screener lỗi: {e}")


# ── Help command ───────────────────────────────────────────────────────────────

@bot.command(name="help", aliases=["h"])
async def cmd_help(ctx):
    """!help — Danh sách lệnh"""
    embed = discord.Embed(
        title="🤖 VN100 AI Trading Assistant",
        description="AI hỗ trợ phân tích, người ra quyết định cuối",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="⚡ Nhanh (<5s)",
        value="`!gia <MÃ>` — Giá & thay đổi\nVD: `!gia VNM`",
        inline=False
    )
    embed.add_field(
        name="📊 Trung bình (<20s)",
        value="`!phan-tich <MÃ>` — TA + FA song song\nVD: `!phan-tich HPG`",
        inline=False
    )
    embed.add_field(
        name="🔬 Toàn diện (<60s)",
        value="`!full <MÃ>` — Full pipeline (TA+FA+Sentiment+Debate+Risk)\nVD: `!full SSI`",
        inline=False
    )
    embed.add_field(
        name="🔍 Screener",
        value="`!screener` — Quét VN100, lọc mã đáng chú ý",
        inline=False
    )
    embed.set_footer(text="Chỉ mang tính tham khảo, không phải tư vấn đầu tư")
    await ctx.send(embed=embed)


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info(f"Discord bot online: {bot.user} (ID: {bot.user.id})")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("🚀 **VN100 AI Trading Assistant** online!\nGõ `!help` để xem danh sách lệnh.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❓ Lệnh không tồn tại. Gõ `!help` để xem danh sách.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Thiếu tham số. Gõ `!help` để xem cú pháp.")
    else:
        log.error(f"Command error: {error}", exc_info=True)
        await ctx.send(f"❌ Lỗi: {error}")


# ── Push helper: gửi morning brief qua webhook ────────────────────────────────

def send_discord_webhook(message: str):
    """Gửi message qua Discord Webhook (dùng trong scheduler.py)."""
    if not WEBHOOK_URL:
        log.info(f"[Discord Webhook] (chưa config): {message[:80]}")
        return
    try:
        import requests
        requests.post(WEBHOOK_URL, json={"content": message[:1900]}, timeout=10)
    except Exception as e:
        log.error(f"Discord webhook lỗi: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Thiếu DISCORD_BOT_TOKEN trong .env")
        print("Setup: https://discord.com/developers/applications")
        sys.exit(1)

    print(f"""
Discord Bot VN100 AI Trading Assistant
Prefix: !
Commands: !gia, !phan-tich, !full, !screener, !help
    """)
    bot.run(BOT_TOKEN)
