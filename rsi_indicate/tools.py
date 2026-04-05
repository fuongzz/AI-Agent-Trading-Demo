"""
tools.py — Định nghĩa Claude tools và executor
Dùng cho chế độ Full Agent (run_agent)
"""

import json
from fetcher import fetch_ohlcv, fetch_realtime, fetch_company_info
from indicators import (
    calculate_rsi, calculate_moving_average, calculate_macd,
    calculate_bollinger, calculate_atr, analyze_volume, find_support_resistance
)

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
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"]
        }
    },
    {
        "name": "get_company_info",
        "description": "Lấy thông tin cơ bản công ty: tên, ngành, sàn giao dịch",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
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
    },
    {
        "name": "calculate_macd",
        "description": "Tính MACD. Cần ít nhất 35 phiên giá.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices":        {"type": "array", "items": {"type": "number"}},
                "fast":          {"type": "integer"},
                "slow":          {"type": "integer"},
                "signal_period": {"type": "integer"}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_bollinger",
        "description": "Tính Bollinger Bands (20 phiên, 2 độ lệch chuẩn).",
        "input_schema": {
            "type": "object",
            "properties": {
                "prices":  {"type": "array", "items": {"type": "number"}},
                "period":  {"type": "integer"},
                "num_std": {"type": "number"}
            },
            "required": ["prices"]
        }
    },
    {
        "name": "calculate_atr",
        "description": "Tính ATR — đo biến động thực tế, gợi ý SL/TP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "highs":  {"type": "array", "items": {"type": "number"}},
                "lows":   {"type": "array", "items": {"type": "number"}},
                "closes": {"type": "array", "items": {"type": "number"}},
                "period": {"type": "integer"}
            },
            "required": ["highs", "lows", "closes"]
        }
    },
    {
        "name": "analyze_volume",
        "description": "Phân tích khối lượng — xác nhận xu hướng giá, phát hiện đột biến.",
        "input_schema": {
            "type": "object",
            "properties": {
                "closes":  {"type": "array", "items": {"type": "number"}},
                "volumes": {"type": "array", "items": {"type": "number"}},
                "period":  {"type": "integer"}
            },
            "required": ["closes", "volumes"]
        }
    },
    {
        "name": "find_support_resistance",
        "description": "Xác định vùng hỗ trợ và kháng cự từ các điểm pivot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "closes":   {"type": "array", "items": {"type": "number"}},
                "highs":    {"type": "array", "items": {"type": "number"}},
                "lows":     {"type": "array", "items": {"type": "number"}},
                "lookback": {"type": "integer"}
            },
            "required": ["closes", "highs", "lows"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    print(f"\n  🔧 Tool: [{name}]  →  {json.dumps(inputs, ensure_ascii=False)[:120]}")

    dispatch = {
        "get_ohlcv":              fetch_ohlcv,
        "get_realtime_price":     fetch_realtime,
        "get_company_info":       fetch_company_info,
        "calculate_rsi":          calculate_rsi,
        "calculate_moving_average": calculate_moving_average,
        "calculate_macd":         calculate_macd,
        "calculate_bollinger":    calculate_bollinger,
        "calculate_atr":          calculate_atr,
        "analyze_volume":         analyze_volume,
        "find_support_resistance": find_support_resistance,
    }

    fn = dispatch.get(name)
    result = fn(**inputs) if fn else {"error": f"Tool '{name}' không tồn tại"}

    print(f"     ✅ {json.dumps(result, ensure_ascii=False)[:200]}...")
    return json.dumps(result, ensure_ascii=False)
