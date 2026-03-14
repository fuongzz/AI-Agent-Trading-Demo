# AI Agent Trading Demo
AI Agent phân tích cổ phiếu VN

Về mặt hệ thống:

User -> Agent loop -> LLM (Claude)

# Cài đặt:
# 1. Clone repo
git clone https://github.com/fuongzz/AI-Agent-Trading-Demo.git
cd AI-Agent-Trading-Demo
# 2. Cài Python 3.11
- Chọn "Add Python to PATH" trong quá trình cài đặt
# 3. Cài thư viện
py -3.11 -m pip install -r requirements.txt

# 4. Tạo file môi trường và API key
copy rsi_indicate\.env.example rsi_indicate\.env

Điền API key vào file .env: 
ANTHROPIC_API_KEY=your_api_key_here

Key API tại: console.anthropic.com

# 5. Chạy demo:

py -3.11 rsi_indicate/stock_agent_demo.py