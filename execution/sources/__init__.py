"""Source 어댑터 플랫폼.

새 사이트 추가 절차:
  1. execution/sources/<name>.py 작성 (LABEL, ICON, fetch_new_posts, commit_state, format_message)
  2. DASHBOARD_DIR/sources.json 에 entry 한 줄 추가
  3. bash scripts/deploy.sh

ra_sisyphe_bot 부팅 시 sources.json 의 enabled=true 항목을 모두 읽어
job_queue.run_daily 로 자동 등록.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Any

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES_JSON = os.path.join(DASHBOARD_DIR, 'sources.json')
STATE_DIR = os.path.join(DASHBOARD_DIR, 'sources_state')

logger = logging.getLogger(__name__)


def load_sources_config() -> list[dict[str, Any]]:
    """sources.json 읽어 enabled=true 항목만 반환. 파일 없으면 빈 리스트."""
    if not os.path.exists(SOURCES_JSON):
        logger.warning(f'sources.json 없음: {SOURCES_JSON}')
        return []
    with open(SOURCES_JSON, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    sources = cfg.get('sources', [])
    return [s for s in sources if s.get('enabled', True)]


def load_adapter(name: str):
    """execution/sources/<name>.py 모듈 동적 import."""
    return importlib.import_module(f'sources.{name}')


def ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
