import os
from dotenv import load_dotenv

load_dotenv()  # .envファイルを読み込む

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY が設定されていません。.env ファイルを確認してください。")
