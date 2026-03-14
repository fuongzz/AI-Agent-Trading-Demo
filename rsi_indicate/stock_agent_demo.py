import anthropic
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Lấy dữ liệu từ Vnstock

def fetch_ohlcv(symbol: str, days: int = 30) -> dict:
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
        volumes = df["volume"].tolist()
        latest  = df.iloc[-1]
        prev    = df.iloc[-2] if len(df) > 1 else df.iloc[-1]

        change  = round(float(latest["close"]) - float(prev["close"]), 2)
        pct     = round((change / float(prev["close"])) * 100, 2)

        return {
            "symbol":       symbol.upper(),
            "latest_price": float(latest["close"]),
            "open":         float(latest["open"]),
            "high":         float(latest["high"]),
            "low":          float(latest["low"]),
            "volume":       int(latest["volume"]),
            "change":       change,
            "change_pct":   f"{pct}%",
            "closes_20":    closes[-20:],
            "volumes_5":    volumes[-5:],
            "date":         str(latest.name)[:10] if hasattr(latest, "name") else end,
            "source":       "Vnstock / VCI"
        }

    except ImportError:
        return {"error": "Chưa cài vnstock. Chạy: pip install vnstock"}
    except Exception as e:
        return {"error": f"Lỗi lấy dữ liệu: {str(e)}"}


def fetch_realtime(symbol: str) -> dict:
    """Lấy giá realtime"""
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
            "symbol":    symbol.upper(),
            "company":   str(row.get("short_name", row.get("company_name", "N/A"))),
            "industry":  str(row.get("industry_name", row.get("sector", "N/A"))),
            "exchange":  str(row.get("exchange", "N/A")),
            "source":    "Vnstock company info"
        }

    except Exception as e:
        return {"error": f"Lỗi lấy thông tin công ty: {str(e)}"}


def calculate_rsi(prices: list, period: int = 14) -> dict:
    """Tính RSI"""
    if len(prices) < period + 1:
        return {"error": f"Cần ít nhất {period + 1} phiên, hiện có {len(prices)}"}

    gains, losses = [], []
    for i in range(1, len(prices)):
        chg = prices[i] - prices[i-1]
        gains.append(max(chg, 0))
        losses.append(abs(min(chg, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    rsi = 100 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    if rsi < 30:
        signal = "OVERSOLD (quá bán) → Có thể là cơ hội MUA"
    elif rsi > 70:
        signal = "OVERBOUGHT (quá mua) → Cân nhắc CHỐT LỜI"
    else:
        signal = "NEUTRAL (trung tính) → Chờ thêm tín hiệu"

    return {"rsi": rsi, "signal": signal, "period": period}


def calculate_moving_average(prices: list, period: int) -> dict:
    """Tính MA"""
    if len(prices) < period:
        return {"error": f"Cần ít nhất {period} phiên"}

    ma     = round(sum(prices[-period:]) / period, 2)
    latest = prices[-1]
    trend  = "TRÊN MA → Xu hướng tăng ✅" if latest > ma else "DƯỚI MA → Xu hướng giảm ⚠️"

    return {"ma": ma, "latest_price": latest, "trend": trend, "period": period}



# Định nghĩa Tools

TOOLS = [
    {
        "name": "get_ohlcv",
        "description": "Lấy dữ liệu giá cổ phiếu VN theo phiên (OHLCV) qua Vnstock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Mã cổ phiếu, VD: VNM, HPG, FPT, MSN, VIC"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_realtime_price",
        "description": "Lấy giá realtime trong giờ giao dịch (9:00–15:00)",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_company_info",
        "description": "Lấy thông tin cơ bản công ty: tên, ngành, sàn giao dịch",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "calculate_rsi",
        "description": "Tính chỉ số RSI từ danh sách giá đóng cửa",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices": {"type": "array", "items": {"type": "number"}},
                "period": {"type": "integer", "default": 14}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_moving_average",
        "description": "Tính đường trung bình động MA",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices": {"type": "array", "items": {"type": "number"}},
                "period": {"type": "integer"}
            },
            "required": ["prices", "period"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    print(f"\n  🔧 Tool: [{name}]  →  {json.dumps(inputs, ensure_ascii=False)}")

    if name == "get_ohlcv":
        result = fetch_ohlcv(**inputs)
    elif name == "get_realtime_price":
        result = fetch_realtime(**inputs)
    elif name == "get_company_info":
        result = fetch_company_info(**inputs)
    elif name == "calculate_rsi":
        result = calculate_rsi(**inputs)
    elif name == "calculate_moving_average":
        result = calculate_moving_average(**inputs)
    else:
        result = {"error": f"Tool '{name}' không tồn tại"}

    print(f"     ✅ {json.dumps(result, ensure_ascii=False)[:200]}...")
    return json.dumps(result, ensure_ascii=False)



# Agent Loop


def run_agent(question: str):
    client = anthropic.Anthropic()

    print("\n" + "="*60)
    print(f"👤 {question}")
    print("="*60)

    messages = [{"role": "user", "content": question}]
    system = """Bạn là AI Agent phân tích cổ phiếu chuyên nghiệp, dùng dữ liệu thực từ Vnstock.
Khi phân tích một mã cổ phiếu, hãy:
1. Lấy thông tin công ty (get_company_info)
2. Lấy dữ liệu OHLCV thực (get_ohlcv)
3. Thử lấy giá realtime (get_realtime_price)
4. Tính RSI 14 phiên từ closes_20
5. Tính MA5 và MA10 từ closes_20
6. Tổng hợp phân tích bằng tiếng Việt gồm:
   - Tên công ty, ngành
   - Giá hiện tại, thay đổi so với hôm qua
   - RSI đang ở mức nào, ý nghĩa
   - Xu hướng theo MA5 và MA10
   - Nhận xét ngắn gọn về kỹ thuật"""

    step = 1
    while True:
        print(f"\nAgent suy nghĩ... (bước {step})")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            step += 1

        elif response.stop_reason == "end_turn":
            answer = "".join(b.text for b in response.content if hasattr(b, "text"))
            print("\n" + "="*60)
            print("KẾT QUẢ PHÂN TÍCH:")
            print("="*60)
            print(answer)
            print("="*60)
            break
        else:
            print(f"⚠️ Stop reason: {response.stop_reason}")
            break



# Run


if __name__ == "__main__":
    print("""
DEMO: AI AGENT - Phân tích mã cổ phiếu                        
Nhập bất kỳ mã HOSE/HNX: VNM, HPG, FPT, VIC, MSN...     
Agent sẽ tự động lấy dữ liệu thực, tính RSI, MA và đưa ra nhận định kỹ thuật.
    """)

    symbol = input("Nhập mã cổ phiếu (vd: VNM): ").strip().upper() or "VNM"
    run_agent(
        f"Phân tích kỹ thuật cổ phiếu {symbol}. "
        f"Giá hiện tại bao nhiêu? RSI đang ở đâu? Xu hướng ngắn hạn thế nào?"
    )