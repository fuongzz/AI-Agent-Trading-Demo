"""
database.py — Quản lý SQLite database (Hạ tầng dữ liệu)
Tích hợp SQLite để lưu trữ OHLCV, cache nội bộ tránh phải gọi vnstock nhiều lần.
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "trading_assistant.db")

def init_db():
    """Khởi tạo các bảng SQLite nếu chưa có."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Bảng giá cuối ngày (Daily OHLCV)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_prices (
        symbol TEXT,
        date TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        PRIMARY KEY (symbol, date)
    )
    ''')

    # Bảng lưu kết quả phân tích AI (cho Memory system)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agent_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        date TEXT,
        action TEXT,
        confluence_score REAL,
        raw_reasoning TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def save_daily_ohlcv(symbol: str, records: list):
    """
    Lưu dữ liệu lịch sử giá OHLCV. 
    records format: [{"date": "2024-01-01", "open": 10, ...}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for r in records:
        cursor.execute('''
        INSERT OR IGNORE INTO daily_prices (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol.upper(), r.get('date'), r.get('open'), r.get('high'), r.get('low'), r.get('close'), r.get('volume')))
        
    conn.commit()
    conn.close()

def get_latest_prices(symbol: str, limit: int = 100):
    """Truy xuất dữ liệu giá lịch sử của mã."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, open, high, low, close, volume 
        FROM daily_prices 
        WHERE symbol = ? 
        ORDER BY date DESC LIMIT ?
    ''', (symbol.upper(), limit))
    rows = cursor.fetchall()
    conn.close()
    
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in reversed(rows)]

def save_agent_decision(symbol: str, date: str, action: str, confluence_score: float, raw_reasoning: dict):
    """Lưu quyết định và lý lẽ của AI (Memory)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO agent_decisions (symbol, date, action, confluence_score, raw_reasoning)
    VALUES (?, ?, ?, ?, ?)
    ''', (symbol.upper(), date, action, confluence_score, json.dumps(raw_reasoning, ensure_ascii=False)))
    conn.commit()
    conn.close()

# Tự động tạo file .db khi import module này
init_db()
