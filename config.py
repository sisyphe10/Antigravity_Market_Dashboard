import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    TWITTER_USER = os.getenv("TWITTER_USER")
    TWITTER_PASS = os.getenv("TWITTER_PASS")
    TWITTER_EMAIL = os.getenv("TWITTER_EMAIL")
    
    # 타겟 계정 리스트 파싱
    target_accounts_str = os.getenv("TARGET_ACCOUNTS", "")
    TARGET_ACCOUNTS = [acc.strip() for acc in target_accounts_str.split(",") if acc.strip()]

    @classmethod
    def validate(cls):
        missing = []
        if not cls.TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
        if not cls.TELEGRAM_CHAT_ID: missing.append("TELEGRAM_CHAT_ID")
        if not cls.TWITTER_USER: missing.append("TWITTER_USER")
        if not cls.TWITTER_PASS: missing.append("TWITTER_PASS")
        
        if missing:
            raise ValueError(f"다음 환경 변수가 설정되지 않았습니다: {', '.join(missing)}")
        
        if not cls.TARGET_ACCOUNTS:
            print("경고: 감시할 트위터 계정(TARGET_ACCOUNTS)이 설정되지 않았습니다.")

config = Config()
