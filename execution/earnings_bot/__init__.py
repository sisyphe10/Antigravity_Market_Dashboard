"""Antigravity Earnings Bot — US 실적·IR Day 한국어 번역·요약·Notion·Telegram 파이프라인.

설계 v2 (Codex 리뷰 반영). 메모리 참조: project_antigravity_earnings_bot.md
"""
import os

# 패키지 import 시 자동으로 .env 로딩 (sisyphe_bot 패턴 차용)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv 미설치 환경은 직접 환경변수 사용
