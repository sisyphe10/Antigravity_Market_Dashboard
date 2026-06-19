"""선유듀오 운동기록 봇 (@SeonyuDuo_bot)

자연어 운동 입력 → Claude Haiku 자동 분류 → 미리보기 확인 → 선유듀오 시트 '운동' 탭에 기록.

특징:
  - 한 메시지에 여러 카테고리(예: 포핸드…백핸드…발리…)가 섞이면 카테고리별로 분리해 여러 행으로 기록.
  - 담당자(식/여니, 내부코드 TS/NY)는 보낸 사람 텔레그램 계정으로 자동 구분 (미등록 시 [식][여니] 1회 등록).
  - "확인 후 저장": 미리보기 + [저장]/[취소]/[담당자 변경] → 저장 시 분류 결과·기록 행을 확인 메시지로 회신.
  - 그룹 채팅 지원: 미리보기 상태를 채팅 단위(chat_data)로 보관 → 그룹원 누구나 버튼 사용.

시트: SEONYUDUO_SHEET_ID '운동' 탭. 컬럼 날짜/요일/담당자/장소/유형/카테고리/내용 (헤더명 동적 매핑).
  요일은 날짜와 동일한 date 값을 기록 → 시트 컬럼 포맷(" "ddd)이 요일로 렌더.
"""
import asyncio
import datetime
import html
import json
import logging
import os
import random
import re
import sys
import time

# ── 중복 실행 방지 (Unix fcntl 락; Windows 로컬 테스트에서는 생략) ──
_lock_file = None
try:
    import fcntl
    _lock_file = open('/tmp/seonyuduo_exercise_bot.lock', 'w')
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
    except IOError:
        print("ERROR: seonyuduo_exercise_bot is already running. Exiting.")
        sys.exit(1)
except ImportError:
    pass  # Windows: fcntl 없음 → 락 생략 (로컬 테스트용)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, ContextTypes, CommandHandler,
                          MessageHandler, CallbackQueryHandler, TypeHandler, filters)
from telegram.error import BadRequest
from dotenv import load_dotenv

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, '.env'))

TOKEN = os.getenv("TELEGRAM_SEONYUDUO_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

KST = datetime.timezone(datetime.timedelta(hours=9))
SEONYUDUO_SHEET_ID = '1w6q3UwUER7oINuk50LyMzgF2K0Fbt2wgSVJ34vImo0g'
SHEET_TAB = '운동'
HAIKU_MODEL = 'claude-haiku-4-5-20251001'
USER_MAP_FILE = os.path.join(ROOT, 'seonyuduo_exercise_user_map.json')

TENNIS_CATEGORIES = ['포핸드', '백핸드', '슬라이스', '포핸드 발리', '백핸드 발리', '서브', '공통']
EXERCISE_TYPES = ['테니스', '러닝', '워크아웃']
WEEKDAY_KO = ['월', '화', '수', '목', '금', '토', '일']  # datetime.weekday(): 월=0
TYPE_EMOJI = {'테니스': '🎾', '러닝': '🏃', '워크아웃': '💪'}
WHO_LABEL = {'TS': '식', 'NY': '여니'}  # 사용자 표시용. 내부 코드/콜백/시트값/user_map 키는 TS·NY 유지

PENDING_TTL = 900  # 초; 오래된 pending 정리 기준

# /remind (최근 운동 피드백 복습)
REMIND_SESSIONS = 4          # 보여줄 최근 세션(=구분되는 날짜) 수
REMIND_PER_CAT_MAX = 6       # 카테고리당 최대 표시 줄 수 (뒤 카테고리 통째 누락 방지)
REMIND_MAXLEN = 3900         # 텔레그램 4096 한도 여유분
REMIND_TARGET_LABEL = {'self': '본인', 'other': '상대', 'both': '둘 다'}
FEEDBACK_TIPS_N = 3          # 자동 리마인드에 랜덤으로 붙일 피드백 개수
FEEDBACK_TIPS_FILE = os.path.join(ROOT, 'seonyuduo_feedback_tips.json')

# 가계부 지출 알림(Sisyphe 봇 → 선유듀오 이관 시)을 보낼 그룹챗 id 저장소.
# Sisyphe 봇이 이 파일을 읽어 같은 토큰 대신 @SeonyuDuo_bot 토큰으로 전송한다.
SEONYUDUO_CHATS_FILE = os.path.join(ROOT, 'seonyuduo_chats.json')


def _load_chats():
    try:
        with open(SEONYUDUO_CHATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"chats 읽기 실패: {e}")
        return {}


def _save_chats(d):
    try:
        tmp = SEONYUDUO_CHATS_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SEONYUDUO_CHATS_FILE)  # 원자적 교체 (강제종료 중 깨짐 방지)
    except Exception as e:
        logging.error(f"chats 저장 실패: {e}")


async def capture_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """모든 업데이트에서 그룹/슈퍼그룹 chat_id를 비차단 캡처 (group=-1 등록).
    저장만 하고 propagation은 막지 않아 기존 핸들러는 정상 동작한다.
    ※ 텔레그램 프라이버시 모드 ON 그룹에선 '명령어(/...)'만 봇에 전달됨 → 캡처도 명령어로 트리거."""
    ch = update.effective_chat
    if not ch or ch.type not in ('group', 'supergroup'):
        return
    chats = _load_chats()
    key = str(ch.id)
    if key not in chats:
        chats[key] = {'type': ch.type, 'title': ch.title or ''}
        _save_chats(chats)
        logging.info(f"선유듀오 그룹챗 캡처: {key} ({ch.title})")
        try:
            await context.bot.send_message(
                chat_id=ch.id,
                text="✅ 이 그룹을 선유듀오 가계부 지출 알림 대상으로 등록했어요.\n"
                     "앞으로 시지프에서 '선유'로 이관하면 여기로 지출 내역이 옵니다.")
        except Exception as e:
            logging.warning(f"캡처 확인 메시지 전송 실패: {e}")


# ══════════════════════════════════════════════════════════
# Google Sheets
# ══════════════════════════════════════════════════════════
def _get_seonyuduo_service():
    """선유듀오용 Google Sheets API 서비스 (sisyphe_bot.py와 동일 서비스계정)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not sa_json:
        return None
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds)


def _read_header(service) -> list:
    """'운동' 탭 1행(헤더). 실패는 예외 전파(잘못된 컬럼 기록 방지)."""
    res = service.spreadsheets().values().get(
        spreadsheetId=SEONYUDUO_SHEET_ID, range=f'{SHEET_TAB}!1:1').execute()
    vals = res.get('values', [])
    return [h.strip() for h in vals[0]] if vals else []


def _row_for(header: list, entry: dict) -> list:
    """헤더 순서에 맞춰 한 행 구성. 요일에는 날짜값(컬럼 포맷이 요일로 렌더)."""
    field_map = {
        '날짜': entry['날짜'],
        '요일': entry['날짜'],
        '담당자': entry.get('담당자', ''),
        '장소': entry['장소'],
        '유형': entry['유형'],
        '카테고리': entry['카테고리'],
        '내용': entry['내용'],
    }
    if header:
        return [field_map.get(h, '') for h in header]
    return [field_map['날짜'], field_map['요일'], field_map['담당자'],
            field_map['장소'], field_map['유형'], field_map['카테고리'], field_map['내용']]


def _build_row(service, entry: dict) -> list:
    """단건 편의 함수 (헤더 1회 읽고 1행 구성)."""
    return _row_for(_read_header(service), entry)


def _save_to_sheet(batch: dict):
    """블로킹 작업 일괄 (executor에서 실행): 서비스 생성 + 헤더 1회 읽기 + 전 항목 append.
    기록된 (시작행, 끝행) 튜플 반환, 알 수 없으면 None."""
    service = _get_seonyuduo_service()
    if not service:
        raise RuntimeError("서비스 계정(GOOGLE_SERVICE_ACCOUNT_KEY) 미설정")
    header = _read_header(service)
    rows = [_row_for(header, e) for e in batch['entries']]
    res = service.spreadsheets().values().append(
        spreadsheetId=SEONYUDUO_SHEET_ID, range=f'{SHEET_TAB}!A1',
        valueInputOption='USER_ENTERED', insertDataOption='INSERT_ROWS',
        body={'values': rows}).execute()
    updated = (res or {}).get('updates', {}).get('updatedRange', '')
    tail = updated.split('!')[-1] if '!' in updated else ''
    nums = [int(x) for x in re.findall(r'(\d+)', tail)]
    if len(nums) >= 2:
        return (nums[0], nums[1])
    if len(nums) == 1:
        return (nums[0], nums[0])
    return None


# ══════════════════════════════════════════════════════════
# 담당자 매핑
# ══════════════════════════════════════════════════════════
def load_user_map() -> dict:
    try:
        with open(USER_MAP_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_user_map(m: dict):
    with open(USER_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
# Haiku 분류 + 결정적 검증
# ══════════════════════════════════════════════════════════
_anthropic_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None and ANTHROPIC_API_KEY:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def build_system_prompt() -> str:
    now = datetime.datetime.now(tz=KST)
    today = now.strftime('%Y-%m-%d')
    yest = (now - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    cats = ' / '.join(TENNIS_CATEGORIES)
    return f"""너는 부부의 운동 기록을 분류하는 어시스턴트다. 사용자의 한국어 자연어 입력을 읽고 아래 JSON 1개만 출력한다. 코드블록·설명·마크다운 금지.

오늘 날짜(KST): {today} ({WEEKDAY_KO[now.weekday()]})
어제 날짜(KST): {yest}

출력 스키마:
{{"is_exercise": true, "확신도": "high", "entries": [{{"유형": "...", "카테고리": "...", "장소": "...", "날짜": "YYYY-MM-DD", "내용": "..."}}]}}

규칙:
- is_exercise (bool): 운동 기록이면 true. 운동과 무관한 잡담/질문/인사면 false (이때 entries는 빈 배열 []).
- ★ 한 메시지에 여러 카테고리(테니스 스트로크 여러 개, 또는 여러 운동 종목)가 섞여 있으면 **카테고리별로 분리**해 entries에 각각 한 항목으로 넣는다. 한 종류만 있으면 entries 길이는 1.
  예: "포핸드는 손목 고정, 백핸드는 체중 이동, 발리는 짧게 펀치" → 3개 항목(포핸드/백핸드/포핸드 발리 또는 백핸드 발리).
- 같은 메시지의 날짜·장소는 모든 항목에 공통 적용한다.
- 각 항목 필드:
  · 유형: 반드시 "테니스" / "러닝" / "워크아웃" 중 하나.
    테니스(포핸드/백핸드/발리/서브/슬라이스/랠리/스트로크) → "테니스"; 달리기/조깅/러닝/마라톤/km → "러닝"; 그 외 근력·코어·맨몸(데드리프트/스쿼트/벤치프레스/풀업/플랭크/코어) → "워크아웃".
  · 카테고리: 유형이 "테니스"이면 반드시 다음 7개 중 정확히 하나: {cats}
    슬라이스(포핸드든 백핸드든)는 "슬라이스". 발리는 포/백 구분해 "포핸드 발리"/"백핸드 발리". 어디에도 안 맞거나 혼합이면 "공통".
    유형이 "테니스"가 아니면 구체적 운동명(러닝/데드리프트/스쿼트/벤치프레스/코어 등) 자유 텍스트.
  · 장소: 있으면 추출(JD테니스/한강공원/헬스장), 없으면 "".
  · 날짜(YYYY-MM-DD): "오늘"→{today}, "어제"→{yest}, 상대표현은 {today} 기준 역산, 명시일은 정규화, 언급 없으면 {today}.
  · 내용: 그 카테고리에 해당하는 피드백/메모만 추려 기술. 장소·날짜 메타는 빼고. 없으면 "".
- 확신도: 분류가 명확하면 "high", 모호하면 "low".

반드시 위 스키마의 JSON 1개만 출력."""


def _coerce_tennis_cat(c: str):
    c = (c or '').replace(' ', '')
    if not c:
        return None
    if '슬라이스' in c:
        return '슬라이스'
    if '발리' in c:
        return '포핸드 발리' if '포' in c else ('백핸드 발리' if '백' in c else '공통')
    if '서브' in c:
        return '서브'
    if '포핸드' in c:
        return '포핸드'
    if '백핸드' in c:
        return '백핸드'
    if '공통' in c:
        return '공통'
    return None


def _validate_entry(p: dict) -> dict:
    """항목 1개를 결정적으로 보정 (테니스 7종/날짜/미래교정)."""
    today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')

    유형 = (p.get('유형') or '').strip()
    if 유형 not in EXERCISE_TYPES:
        유형 = '워크아웃'

    카테고리 = (p.get('카테고리') or '').strip()
    if 유형 == '테니스':
        if 카테고리 not in TENNIS_CATEGORIES:
            카테고리 = _coerce_tennis_cat(카테고리) or '공통'
    else:
        카테고리 = 카테고리 or 유형

    날짜 = (p.get('날짜') or '').strip()
    future_corrected = False
    try:
        d = datetime.date.fromisoformat(날짜)
        if d > datetime.date.fromisoformat(today_str):
            날짜 = today_str
            future_corrected = True
    except ValueError:
        날짜 = today_str

    return {
        '유형': 유형,
        '카테고리': 카테고리,
        '장소': (p.get('장소') or '').strip(),
        '날짜': 날짜,
        '내용': (p.get('내용') or '').strip(),
        '_future_corrected': future_corrected,
    }


def _validate_batch(data: dict) -> dict:
    """모델 출력 → {is_exercise, 확신도, entries:[검증된 항목…]}."""
    raw = data.get('entries')
    if not isinstance(raw, list) or not raw:
        # 모델이 단일 객체로 준 경우 호환 처리
        raw = [data] if (data.get('유형') or data.get('카테고리') or data.get('내용')) else []
    return {
        'is_exercise': bool(data.get('is_exercise', True)),
        '확신도': (data.get('확신도') or 'high').strip(),
        'entries': [_validate_entry(e) for e in raw if isinstance(e, dict)],
    }


def classify(text: str):
    """자연어 → 검증된 batch dict. 실패 시 None."""
    client = _get_anthropic()
    if not client:
        logging.error('ANTHROPIC_API_KEY 미설정')
        return None
    for attempt in range(2):
        try:
            resp = client.messages.create(
                model=HAIKU_MODEL, max_tokens=1024,
                system=build_system_prompt(),
                messages=[{"role": "user", "content": text}])
            raw = resp.content[0].text.strip().encode('utf-8', 'ignore').decode('utf-8')
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if not m:
                logging.warning(f'JSON 미발견: {raw[:120]}')
                return None
            return _validate_batch(json.loads(m.group(0)))
        except Exception as e:
            es = str(e).lower()
            if attempt == 0 and ('529' in es or '429' in es or 'overloaded' in es or 'timeout' in es):
                time.sleep(8)
                continue
            logging.error(f'classify 실패: {e}')
            return None
    return None


# ══════════════════════════════════════════════════════════
# 미리보기 / 저장확인 / pending
# ══════════════════════════════════════════════════════════
def _weekday_char(date_str: str) -> str:
    try:
        return WEEKDAY_KO[datetime.date.fromisoformat(date_str).weekday()]
    except ValueError:
        return ''


def _entry_block(i: int, e: dict, total: int) -> str:
    wd = _weekday_char(e['날짜'])
    emoji = TYPE_EMOJI.get(e['유형'], '🏃')
    num = f"{i}. " if total > 1 else ""
    # parse_mode='HTML' 전송 → LLM/사용자 텍스트는 반드시 이스케이프 (<,>,& 깨짐 방지)
    kat = html.escape(e['카테고리'])
    typ = html.escape(e['유형'])
    loc = html.escape(e['장소'] or '-')
    cont = html.escape(e['내용'] or '-')
    return (f"{num}{emoji} <b>{kat}</b>  ·  {typ}\n"
            f"📅 {e['날짜']} ({wd})   📍 {loc}\n"
            f"📝 {cont}")


def _warn_lines(batch: dict) -> str:
    w = ''
    if batch.get('확신도') == 'low':
        w += '⚠️ 분류가 불확실해요. 확인해주세요.\n'
    if any(e.get('_future_corrected') for e in batch['entries']):
        w += '⚠️ 미래 날짜는 오늘로 바꿨어요.\n'
    return w


def _format_preview(batch: dict) -> str:
    es = batch['entries']
    n = len(es)
    who = es[0].get('담당자', '-') if es else '-'
    head = (f"<b>운동 기록 미리보기{f' ({n}건)' if n > 1 else ''}</b>\n"
            f"[{_who_disp(who)}]\n━━━━━━━━━━━━━━━\n")
    body = '\n\n'.join(_entry_block(i, e, n) for i, e in enumerate(es, 1))
    return _warn_lines(batch) + head + body


def _format_saved(batch: dict, rng) -> str:
    es = batch['entries']
    n = len(es)
    who = es[0].get('담당자', '-') if es else '-'
    head = (f"✅ <b>운동 시트에 저장했어요{f' ({n}건)' if n > 1 else ''}</b>\n"
            f"[{_who_disp(who)}]\n━━━━━━━━━━━━━━━\n")
    body = '\n\n'.join(_entry_block(i, e, n) for i, e in enumerate(es, 1))
    tail = ''
    if rng:
        s, en = rng
        tail = f"\n\n🗂 운동 탭 {s}행에 기록" if s == en else f"\n\n🗂 운동 탭 {s}~{en}행에 기록"
    return head + body + tail


def _put_pending(context, msg_id: int, batch: dict):
    # chat_data(채팅 단위) — 그룹에서 둘 중 누구든 버튼을 누를 수 있게. DM에서도 동일.
    pend = context.chat_data.setdefault('pending', {})
    now = time.time()
    for k in [k for k, v in pend.items() if now - v.get('_ts', now) > PENDING_TTL]:
        pend.pop(k, None)
    batch = dict(batch)
    batch['_ts'] = now
    batch['_saved'] = False
    pend[msg_id] = batch


def _preview_keyboard(mid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 저장", callback_data=f"save:{mid}"),
         InlineKeyboardButton("❌ 취소", callback_data=f"cancel:{mid}")],
        [InlineKeyboardButton("👤 담당자 변경", callback_data=f"who:{mid}")],
    ])


async def _send_preview(status_msg, context, batch: dict):
    mid = status_msg.message_id
    _put_pending(context, mid, batch)
    await status_msg.edit_text(_format_preview(batch), parse_mode='HTML',
                               reply_markup=_preview_keyboard(mid))


# ══════════════════════════════════════════════════════════
# 핸들러
# ══════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏃 선유듀오 운동기록 봇이에요.\n\n"
        "운동한 내용을 자연어로 보내면 자동으로 분류해서 운동 시트에 기록해드려요.\n"
        "여러 카테고리를 한 번에 적으면 카테고리별로 나눠서 여러 줄로 저장해요.\n\n"
        "예) <code>오늘 JD테니스 - 포핸드 손목 고정, 백핸드 체중 이동, 발리 짧게 펀치</code>\n"
        "예) <code>어제 헬스장 데드리프트 100kg, 스쿼트 80kg</code>\n"
        "예) <code>한강 5km 25분</code>\n\n"
        "👥 <b>그룹 채팅에서는</b> <code>/fit 운동내용</code> 으로 보내주세요.\n"
        "예) <code>/fit 오늘 JD테니스 포핸드 손목 고정, 백핸드 체중 이동</code>\n\n"
        "💰 <b>가계부</b>는 <code>/ledger 지출 식비 점심 15000 생활비</code> 처럼 입력해요.\n\n"
        "/remind 복습, /help 도움말, /whoami 담당자 확인",
        parse_mode='HTML')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📋 선유듀오 봇 사용법</b>\n\n"
        "<b>🏃 운동 기록</b>\n"
        "운동 내용을 자연어로 보내면 → AI가 유형/카테고리/날짜 분류 → 미리보기 [저장]\n"
        "• 그룹에선 <code>/fit 운동내용</code> (DM은 그냥 텍스트)\n"
        "   예) <code>/fit 오늘 JD테니스 포핸드 손목 고정, 백핸드 체중 이동</code>\n"
        "• 한 메시지에 여러 카테고리 → 카테고리별로 나눠 저장\n"
        "• 테니스 카테고리: 포핸드·백핸드·슬라이스·포핸드 발리·백핸드 발리·서브·공통\n"
        "• 러닝/워크아웃: 종목명 자유 · 날짜 미기재 시 오늘\n\n"
        "<b>💰 가계부 입력</b>\n"
        "<code>/ledger [유형] [카테고리] [메모] [금액] [통장]</code>\n"
        "   예) <code>/ledger 지출 식비 점심 15000 생활비</code>\n"
        "   예) <code>/ledger 수입 급여 생활비충원 800000 생활비</code>\n"
        "• 유형: 지출/ㅈ · 수입/ㅅ\n"
        "• <code>/ledger</code> 만 보내면 카테고리 목록 + 예산 소진율\n\n"
        "<b>🔁 복습</b>\n"
        "<code>/remind</code> — 유형·대상 골라 최근 운동 피드백 복습 (읽기 전용)\n\n"
        "/whoami — 내 담당자(식/여니) 확인·변경",
        parse_mode='HTML')


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    who = load_user_map().get(uid)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("식", callback_data="setwho:TS"),
        InlineKeyboardButton("여니", callback_data="setwho:NY")]])
    cur = f"현재 담당자: <b>[{_who_disp(who)}]</b>" if who else "아직 담당자가 등록되지 않았어요."
    await update.message.reply_text(cur + "\n아래에서 선택/변경할 수 있어요.",
                                    parse_mode='HTML', reply_markup=kb)


# ── 선유듀오 가계부 입력 (/ledger) ──────────────────────────────────
SEONYUDUO_BUDGET = 800000  # 월 예산(원)


def _seonyuduo_month_spent(service):
    """선유듀오 가계부 이번달(KST) 지출 합계. 실패 시 None."""
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='가계부!A:F').execute()
        mp = datetime.datetime.now(tz=KST).strftime('%Y-%m')
        total = 0
        for r in res.get('values', [])[1:]:
            if len(r) > 3 and str(r[0]).startswith(mp) and r[1] == '지출':
                try:
                    total += int(str(r[3]).replace(',', '') or '0')
                except ValueError:
                    pass
        return total
    except Exception:
        return None


def _budget_line(total):
    """예산 소진율 줄. total None이면 빈 문자열."""
    if total is None:
        return ''
    pct = max(0, round(total / SEONYUDUO_BUDGET * 100))
    remaining = max(0, SEONYUDUO_BUDGET - total)
    filled = min(10, max(0, round(pct / 100 * 10)))
    bar = '█' * filled + '░' * (10 - filled)
    return f"\n📊 예산 소진율 {pct}% [{bar}]\n💵 잔액 {remaining:,}원"


async def cmd_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """선유듀오 가계부 입력: /ledger [유형] [카테고리] [메모] [금액] [통장]"""
    service = _get_seonyuduo_service()
    if not service:
        await update.message.reply_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return
    args = context.args

    # 인자 없음 → 카테고리/통장 목록 + 예산 + 사용법
    if not args:
        expense, income, accounts = [], [], []
        try:
            res = service.spreadsheets().values().get(
                spreadsheetId=SEONYUDUO_SHEET_ID, range='카테고리!A:C').execute()
            for r in res.get('values', []):
                if len(r) >= 2:
                    if r[0] == '지출' and r[1] not in expense:
                        expense.append(r[1])
                    elif r[0] == '수입' and r[1] not in income:
                        income.append(r[1])
                if len(r) >= 3 and r[2] and r[2] not in accounts:
                    accounts.append(r[2])
        except Exception:
            pass
        msg = "<b><u>선유듀오 가계부</u></b>\n"
        bl = _budget_line(_seonyuduo_month_spent(service))
        if bl:
            msg += bl + "\n"
        msg += "\n<b>카테고리</b>\n"
        if expense:
            msg += f"지출: {' · '.join(expense)}\n"
        if income:
            msg += f"수입: {' · '.join(income)}\n"
        if accounts:
            msg += f"통장: {' · '.join(accounts)}\n"
        msg += ("\n📝 <b>사용법</b>\n"
                "<code>/ledger 지출 식비 점심 15000 생활비</code>\n"
                "<code>/ledger 수입 급여 생활비충원 800000 생활비</code>\n\n"
                "형식: /ledger [유형] [카테고리] [메모] [금액] [통장]\n"
                "※ 금액은 숫자만. 메모에 숫자만 단독으로 쓰면 금액으로 오인될 수 있어요.")
        await update.message.reply_text(msg, parse_mode='HTML')
        return

    if len(args) < 3:
        await update.message.reply_text(
            "❌ 형식: /ledger [유형] [카테고리] [메모] [금액] [통장]", parse_mode='HTML')
        return

    if args[0] in ('지출', 'ㅈ'):
        tx_type = '지출'
    elif args[0] in ('수입', 'ㅅ'):
        tx_type = '수입'
    else:
        await update.message.reply_text("❌ 유형은 '지출/ㅈ' 또는 '수입/ㅅ'으로 입력하세요.")
        return
    category = args[1]

    # 금액/통장/메모 파싱 (/ledger2와 동일: 마지막=통장, 그 앞=금액 / 통장 생략 케이스)
    # 카테고리 검증보다 먼저 파싱 → 금액 불량이면 신규 카테고리 프롬프트 띄우지 않음
    account = args[-1]
    try:
        amount = int(args[-2].replace(',', ''))
        if amount <= 0:
            raise ValueError
        memo = ' '.join(args[2:-2]) if len(args) > 4 else ''
    except Exception:
        try:
            amount = int(args[-1].replace(',', ''))
            if amount <= 0:
                raise ValueError
            memo = ' '.join(args[2:-1]) if len(args) > 3 else ''
            account = ''
        except Exception:
            await update.message.reply_text("❌ 금액(숫자)을 확인하세요.")
            return

    # 카테고리 검증 (탭이 비어 valid가 없으면 통과). 없는 카테고리면 거부 대신 추가 프롬프트.
    valid = []
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='카테고리!A:B').execute()
        valid = [r[1] for r in res.get('values', []) if len(r) >= 2 and r[0] == tx_type]
    except Exception:
        valid = []
    if valid and category not in valid:
        context.user_data['pending_sd_ledger'] = {
            'tx_type': tx_type, 'category': category, 'amount': amount,
            'memo': memo, 'account': account,
            'today_str': datetime.datetime.now(tz=KST).strftime('%Y-%m-%d'),
        }
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ 추가하고 입력", callback_data='sdcat:add'),
            InlineKeyboardButton("✖️ 취소", callback_data='sdcat:cancel'),
        ]])
        await update.message.reply_text(
            f"❓ '{category}'는 {tx_type} 카테고리에 없어요.\n"
            f"새로 추가하고 가계부에 입력할까요?\n\n"
            f"기존 {tx_type} 카테고리: {' · '.join(valid) if valid else '(없음)'}",
            reply_markup=kb,
        )
        return

    try:
        today_str = datetime.datetime.now(tz=KST).strftime('%Y-%m-%d')
        # 안전 기록: A:F 다음 빈 행에 직접 update (보조열 I~K 미관여)
        existing = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='가계부!A:F').execute().get('values', [])
        n = len(existing) + 1
        service.spreadsheets().values().update(
            spreadsheetId=SEONYUDUO_SHEET_ID, range=f'가계부!A{n}:F{n}',
            valueInputOption='USER_ENTERED',
            body={'values': [[today_str, tx_type, category, amount, memo, account]]}).execute()

        emoji = '🔴' if tx_type == '지출' else '🟢'
        msg = (f"<b><u>선유듀오 가계부</u></b>\n{emoji} <b>{tx_type}</b> 입력 완료\n"
               f"━━━━━━━━━━━━━━━\n📅 {today_str}\n📂 {category}\n💰 {amount:,}원\n")
        if memo:
            msg += f"📝 {memo}\n"
        if account:
            msg += f"🏦 {account}\n"
        if tx_type == '지출':
            msg += _budget_line(_seonyuduo_month_spent(service))
        await update.message.reply_text(msg, parse_mode='HTML')
        logging.info(f"SeonyuDuo /ledger: {tx_type} {amount} {category} {memo} {account}")
    except Exception as e:
        logging.error(f"SeonyuDuo /ledger error: {e}")
        await update.message.reply_text(f"❌ 저장 실패: {e}")


async def _process_exercise_text(update, context, text: str):
    status = await update.message.reply_text("🏷️ 분류 중...")
    loop = asyncio.get_running_loop()
    batch = await loop.run_in_executor(None, classify, text)

    if batch is None:
        await status.edit_text("⚠️ 분류에 실패했어요(AI 응답 오류). 잠시 후 다시 시도해주세요.")
        return
    if not batch['is_exercise'] or not batch['entries']:
        await status.edit_text("🤔 운동 기록으로 보이지 않아요. 운동한 내용을 적어주세요.")
        return

    uid = str(update.effective_user.id)
    user_map = load_user_map()
    if uid not in user_map:
        context.user_data['await_register'] = batch
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("식", callback_data="reg:TS"),
            InlineKeyboardButton("여니", callback_data="reg:NY")]])
        await status.edit_text("처음이시네요! 담당자를 선택하세요.", reply_markup=kb)
        return

    who = user_map[uid]
    for e in batch['entries']:
        e['담당자'] = who
    await _send_preview(status, context, batch)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 일반 텍스트는 1:1(DM)에서만 처리. 그룹에서는 /log 명령 사용(프라이버시·스팸 회피).
    if update.effective_chat and update.effective_chat.type != 'private':
        return
    text = (update.message.text or '').strip()
    if len(text) < 2:
        await update.message.reply_text(
            "운동 내용을 적어주세요. 예) 오늘 JD테니스 슬라이스 연습")
        return
    await _process_exercise_text(update, context, text)


async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/log 운동내용 — 그룹·DM 공통 (프라이버시 ON 그룹에서도 동작)."""
    raw = update.message.text or ''
    text = re.sub(r'^/\S+\s*', '', raw, count=1).strip()  # 앞의 /log 또는 /log@bot 제거
    if not text:
        await update.message.reply_text(
            "운동 내용을 함께 적어주세요.\n"
            "예) <code>/fit 오늘 JD테니스 포핸드 손목 고정, 백핸드 체중 이동</code>",
            parse_mode='HTML')
        return
    await _process_exercise_text(update, context, text)


async def handle_sd_ledger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """선유듀오 가계부 신규 카테고리 추가 확인 버튼. (q.answer()는 handle_callback에서 이미 호출)"""
    q = update.callback_query
    data = q.data or ''
    if data == 'sdcat:cancel':
        context.user_data.pop('pending_sd_ledger', None)
        await q.edit_message_text("↩️ 취소했어요. /ledger 를 다시 입력해주세요.")
        return
    op = context.user_data.pop('pending_sd_ledger', None)
    if op is None:
        await q.edit_message_text("⌛ 만료된 요청이에요. /ledger 를 다시 입력해주세요.")
        return
    service = _get_seonyuduo_service()
    if not service:
        await q.edit_message_text("❌ Google 서비스 계정이 설정되지 않았습니다.")
        return
    tx_type, category = op['tx_type'], op['category']
    amount, memo, account, today_str = op['amount'], op['memo'], op['account'], op['today_str']
    # 1) 카테고리 탭에 추가 [유형, 카테고리, 통장빈칸]
    try:
        cat_rows = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='카테고리!A:C').execute().get('values', [])
        cn = len(cat_rows) + 1
        service.spreadsheets().values().update(
            spreadsheetId=SEONYUDUO_SHEET_ID, range=f'카테고리!A{cn}:C{cn}',
            valueInputOption='RAW', body={'values': [[tx_type, category, '']]}).execute()
        logging.info(f"SeonyuDuo 카테고리 추가: {tx_type} {category}")
    except Exception as e:
        logging.error(f"SeonyuDuo 카테고리 추가 실패: {e}")
        await q.edit_message_text(f"❌ 카테고리 추가 실패: {e}")
        return
    # 2) 원래 입력하려던 가계부 거래 완료 (A:F 다음 빈 행에 직접 update)
    try:
        existing = service.spreadsheets().values().get(
            spreadsheetId=SEONYUDUO_SHEET_ID, range='가계부!A:F').execute().get('values', [])
        n = len(existing) + 1
        service.spreadsheets().values().update(
            spreadsheetId=SEONYUDUO_SHEET_ID, range=f'가계부!A{n}:F{n}',
            valueInputOption='USER_ENTERED',
            body={'values': [[today_str, tx_type, category, amount, memo, account]]}).execute()
        emoji = '🔴' if tx_type == '지출' else '🟢'
        msg = (f"<b><u>선유듀오 가계부</u></b>\n✅ '{category}' 카테고리 추가됨\n"
               f"{emoji} <b>{tx_type}</b> 입력 완료\n"
               f"━━━━━━━━━━━━━━━\n📅 {today_str}\n📂 {category}\n💰 {amount:,}원\n")
        if memo:
            msg += f"📝 {memo}\n"
        if account:
            msg += f"🏦 {account}\n"
        if tx_type == '지출':
            msg += _budget_line(_seonyuduo_month_spent(service))
        await q.edit_message_text(msg, parse_mode='HTML')
        logging.info(f"SeonyuDuo sdcat confirm: {tx_type} {amount} {category}")
    except Exception as e:
        logging.error(f"SeonyuDuo sdcat 가계부 입력 실패: {e}")
        await q.edit_message_text(f"❌ 가계부 저장 실패 (카테고리는 추가됨): {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ''

    # 선유듀오 가계부 신규 카테고리 추가 확인 (q.answer()는 위에서 호출됨)
    if data.startswith('sdcat:'):
        await handle_sd_ledger_callback(update, context)
        return

    uid = str(update.effective_user.id)

    # 신규 담당자 등록 (분류 결과 대기 중)
    if data.startswith("reg:"):
        who = data.split(":", 1)[1]
        m = load_user_map(); m[uid] = who; save_user_map(m)
        batch = context.user_data.pop('await_register', None)
        if not batch:
            await q.edit_message_text(f"✅ [{_who_disp(who)}] 등록 완료. 운동 내용을 다시 보내주세요.")
            return
        for e in batch['entries']:
            e['담당자'] = who
        await _send_preview(q.message, context, batch)
        return

    # /whoami 담당자 설정/변경
    if data.startswith("setwho:"):
        who = data.split(":", 1)[1]
        m = load_user_map(); m[uid] = who; save_user_map(m)
        await q.edit_message_text(f"✅ 담당자 설정 완료: <b>[{_who_disp(who)}]</b>", parse_mode='HTML')
        return

    # /remind 흐름 (rmd:t:유형 / rmd:s:유형:target) — 멀티콜론이라 아래 split 파싱보다 먼저 처리
    if data.startswith("rmd:"):
        if await _handle_remind_callback(q, data):
            return

    # 미리보기 버튼: who/save/cancel + 메시지ID
    try:
        action, mid_s = data.split(":", 1)
        mid = int(mid_s)
    except ValueError:
        return
    pending = context.chat_data.get('pending', {})
    batch = pending.get(mid)
    if not batch:
        await q.edit_message_text("⌛ 만료되었거나 이미 처리된 항목이에요. 다시 입력해주세요.")
        return

    if action == "who":
        cur = batch['entries'][0].get('담당자') if batch['entries'] else None
        new = 'NY' if cur == 'TS' else 'TS'
        for e in batch['entries']:
            e['담당자'] = new
        try:
            await q.edit_message_text(_format_preview(batch), parse_mode='HTML',
                                      reply_markup=_preview_keyboard(mid))
        except BadRequest as err:
            if 'not modified' not in str(err).lower():
                raise
        return

    if action == "cancel":
        pending.pop(mid, None)
        await q.edit_message_text("❌ 취소했어요.")
        return

    if action == "save":
        if batch.get('_saved'):
            return  # 더블탭: 상단에서 이미 q.answer() 호출됨
        batch['_saved'] = True
        try:
            loop = asyncio.get_running_loop()
            rng = await loop.run_in_executor(None, _save_to_sheet, batch)
            pending.pop(mid, None)
            await q.edit_message_text(_format_saved(batch, rng), parse_mode='HTML')
        except Exception as ex:
            batch['_saved'] = False  # 실패 → 재시도 허용
            logging.error(f"시트 저장 실패: {ex}")
            await q.edit_message_text("❌ 저장 실패. [저장]을 다시 눌러주세요.",
                                      reply_markup=_preview_keyboard(mid))
        return


# ══════════════════════════════════════════════════════════
# /remind — 최근 운동 피드백 복습 (읽기 전용, 시트 미수정)
# ══════════════════════════════════════════════════════════
def _fetch_recent_sessions(유형: str, who_list: list) -> dict:
    """'운동' 탭에서 (유형 일치 AND 담당자 ∈ who_list) 행 → 최근 REMIND_SESSIONS개
    세션(=구분되는 날짜, 최신순)만 추림. 블로킹(시트 read) → executor에서 호출.
    반환: {'dates': [최신순 날짜…], 'rows': [{'날짜','담당자','카테고리','내용'}…]}"""
    service = _get_seonyuduo_service()
    if not service:
        raise RuntimeError("서비스 계정(GOOGLE_SERVICE_ACCOUNT_KEY) 미설정")
    res = service.spreadsheets().values().get(
        spreadsheetId=SEONYUDUO_SHEET_ID, range=f'{SHEET_TAB}!A:G').execute()
    vals = res.get('values', [])
    if not vals:
        return {'dates': [], 'rows': []}
    idx = {h.strip(): i for i, h in enumerate(vals[0])}

    def cell(r, name):
        i = idx.get(name)
        return (r[i].strip() if (i is not None and i < len(r) and r[i] is not None) else '')

    matched = []
    for r in vals[1:]:
        if cell(r, '유형') != 유형:
            continue
        if cell(r, '담당자') not in who_list:
            continue
        matched.append({'날짜': cell(r, '날짜'), '담당자': cell(r, '담당자'),
                        '카테고리': cell(r, '카테고리'), '내용': cell(r, '내용')})

    def _key(d):
        try:
            return datetime.date.fromisoformat(d).isoformat()
        except ValueError:
            return ''  # 파싱 실패는 맨 뒤로
    matched.sort(key=lambda x: _key(x['날짜']), reverse=True)

    seen, dates = set(), []
    for m in matched:
        if m['날짜'] not in seen:
            if len(dates) >= REMIND_SESSIONS:
                break
            seen.add(m['날짜']); dates.append(m['날짜'])
    keep = set(dates)
    rows = [m for m in matched if m['날짜'] in keep]
    return {'dates': dates, 'rows': rows}


def _format_remind(유형: str, target: str, who_list: list, data: dict) -> str:
    """최근 세션을 카테고리별로 그룹핑해 HTML 포맷 (원문 내용+날짜 그대로).
    테니스=TENNIS_CATEGORIES 순서, 그 외=최신 등장순. 카테고리당 최대 REMIND_PER_CAT_MAX줄,
    전체 REMIND_MAXLEN 가드 (카테고리당 캡으로 뒤 카테고리 통째 누락 방지)."""
    emoji = TYPE_EMOJI.get(유형, '🏃')
    who_label = '[듀오]' if len(who_list) == 2 else f"[{html.escape(_who_disp(who_list[0]))}]"
    head = (f"{emoji} <b>{html.escape(유형)} · 최근 {len(data['dates'])}회 복습</b>\n"
            f"{who_label}\n"
            f"━━━━━━━━━━━━━━━\n")
    rows = data['rows']
    if not rows:
        return head + f"📂 최근 {html.escape(유형)} 기록 없음"

    default_cat = '공통' if 유형 == '테니스' else 유형

    def _cat_of(r):
        return r['카테고리'] or default_cat

    if 유형 == '테니스':
        order = [c for c in TENNIS_CATEGORIES if any(_cat_of(r) == c for r in rows)]
        for r in rows:  # 7종 밖 카테고리도 뒤에 보존
            if _cat_of(r) not in order:
                order.append(_cat_of(r))
    else:
        order = []
        for r in rows:  # rows는 날짜 내림차순 → 최신 등장순
            if _cat_of(r) not in order:
                order.append(_cat_of(r))

    parts, dropped = [], False
    for cat in order:
        items = [r for r in rows if _cat_of(r) == cat]
        if not items:
            continue
        block = [f"<b>[ {html.escape(cat)} ]</b>"]
        for r in items[:REMIND_PER_CAT_MAX]:
            wd = _weekday_char(r['날짜'])
            date_disp = f"{r['날짜']} ({wd})" if wd else (r['날짜'] or '날짜미상')
            who_tag = f" · {html.escape(_who_disp(r['담당자']))}" if len(who_list) > 1 else ''
            block.append(f"  · {html.escape(r['내용'] or '-')}  <i>({date_disp}{who_tag})</i>")
        if len(items) > REMIND_PER_CAT_MAX:
            block.append(f"  <i>…외 {len(items) - REMIND_PER_CAT_MAX}건</i>")
        candidate = '\n'.join(block)
        if len(head) + sum(len(p) + 2 for p in parts) + len(candidate) > REMIND_MAXLEN:
            dropped = True
            break
        parts.append(candidate)

    body = '\n\n'.join(parts)
    if dropped:
        body += '\n\n<i>…(이하 생략, 메시지 길이 초과)</i>'
    return head + body


def _load_feedback_tips() -> dict:
    """유형별 큐레이션 피드백 목록 (코드 수정 없이 JSON 편집으로 추가 가능). TS/NY 공유."""
    try:
        with open(FEEDBACK_TIPS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"피드백 목록 읽기 실패: {e}")
        return {}


def _format_feedback_tips(유형: str, n: int = FEEDBACK_TIPS_N) -> str:
    """유형 풀에서 랜덤 n개를 뽑아 '💡 피드백' 섹션 생성. 풀이 비면(예: 워크아웃) '' 반환→섹션 생략."""
    tips = _load_feedback_tips().get(유형, [])
    if not tips:
        return ''
    chosen = random.sample(tips, min(n, len(tips)))
    lines = '\n'.join(f"• {html.escape(t)}" for t in chosen)
    return f"\n━━━━━━━━━━━━━━━\n📝 <b>피드백</b>\n{lines}"


def _remind_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💪 워크아웃", callback_data="rmd:t:워크아웃"),
        InlineKeyboardButton("🏃 러닝", callback_data="rmd:t:러닝"),
        InlineKeyboardButton("🎾 테니스", callback_data="rmd:t:테니스"),
    ]])


def _remind_target_keyboard(유형: str, uid: str) -> InlineKeyboardMarkup:
    me = load_user_map().get(uid)  # 등록돼 있으면 버튼에 실제 담당자 표기
    if me:
        other = 'NY' if me == 'TS' else 'TS'
        me_lbl, other_lbl = f"👤 본인 ({_who_disp(me)})", f"👥 상대 ({_who_disp(other)})"
    else:
        me_lbl, other_lbl = "👤 본인", "👥 상대"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(me_lbl, callback_data=f"rmd:s:{유형}:self"),
        InlineKeyboardButton(other_lbl, callback_data=f"rmd:s:{유형}:other"),
        InlineKeyboardButton("👫 둘 다", callback_data=f"rmd:s:{유형}:both"),
    ]])


def _resolve_targets(uid: str, target: str):
    """본인/상대/둘다 → 담당자 코드 리스트. 미등록+본인/상대면 None(안내용)."""
    me = load_user_map().get(uid)
    if target == 'both':
        return ['TS', 'NY']  # 둘 다는 등록 불필요
    if not me:
        return None
    if target == 'self':
        return [me]
    return ['NY' if me == 'TS' else 'TS']  # 상대 = 다른 한 명 (2인 부부 전제)


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/remind — 유형 선택부터 (그룹·DM 공통, 읽기 전용)."""
    await update.message.reply_text(
        "🔁 <b>복습할 운동 유형</b>을 골라주세요.",
        parse_mode='HTML', reply_markup=_remind_type_keyboard())


async def _handle_remind_callback(q, data: str) -> bool:
    """rmd: 콜백 처리. 처리하면 True (handle_callback에서 즉시 return)."""
    uid = str(q.from_user.id)
    parts = data.split(":")  # ['rmd','t',유형] | ['rmd','s',유형,target]
    if len(parts) == 3 and parts[1] == 't':
        유형 = parts[2]
        await q.edit_message_text(
            f"{TYPE_EMOJI.get(유형, '🏃')} <b>{html.escape(유형)}</b> — 누구 기록을 볼까요?",
            parse_mode='HTML', reply_markup=_remind_target_keyboard(유형, uid))
        return True
    if len(parts) == 4 and parts[1] == 's':
        유형, target = parts[2], parts[3]
        who_list = _resolve_targets(uid, target)
        if who_list is None:
            await q.edit_message_text(
                "🙋 담당자가 등록되어 있지 않아요. <code>/whoami</code> 로 먼저 등록해주세요.\n"
                "('둘 다'는 등록 없이도 볼 수 있어요.)", parse_mode='HTML')
            return True
        await q.edit_message_text("🔎 최근 기록을 불러오는 중...")
        try:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, _fetch_recent_sessions, 유형, who_list)
            await q.edit_message_text(_format_remind(유형, target, who_list, res),
                                      parse_mode='HTML')
        except Exception as ex:
            logging.error(f"/remind 조회 실패: {ex}")
            await q.edit_message_text("❌ 기록 조회에 실패했어요. 잠시 후 다시 시도해주세요.")
        return True
    return False


# ══════════════════════════════════════════════════════════
# 구글 캘린더 다이제스트(06:00) + 운동 1시간 전 리마인드 (옥쥬와 빵빵이)
# ══════════════════════════════════════════════════════════
# sisyphe_bot.check_dday_alerts와 동일 캘린더. 같은 서비스계정 + calendar.readonly로 읽기.
SEONYUDUO_CAL_ID = ('a49c912f9e11c6e050c873312ae00a314e45dc075540c86cf428c9921fcbc20c'
                    '@group.calendar.google.com')
CAL_REMINDED_FILE = os.path.join(ROOT, '.seonyuduo_cal_reminded.json')
CAL_POLL_INTERVAL = 300        # 초; 운동 리마인드 폴링 주기(5분)
CAL_REMIND_LEAD = 3600         # 초; 일정 시작 몇 초 전 리마인드(1시간)
CAL_DIGEST_HOUR = 6            # 06:00 KST 다이제스트
CAL_DIGEST_CATCHUP_UNTIL = 10  # 06시에 봇이 죽어있었어도 이 시각(KST)까진 폴링이 다이제스트 따라잡기

# 일정 제목 키워드 → 운동 유형 (구체적 테니스 → 러닝 → 광범위 워크아웃 순으로 검사). 튜닝 가능.
CAL_KEYWORDS = [
    ('테니스', ['테니스', 'tennis', '코트', '랠리', '스트로크', '레슨']),
    ('러닝', ['러닝', '달리기', '조깅', '마라톤', 'run', 'running', '런데이', '하프']),
    ('워크아웃', ['헬스', 'pt', '웨이트', '운동', '짐', 'gym', '요가', '필라테스', '수영',
                 '등산', '클라이밍', '골프', '풋살', '축구', '배드민턴', '크로스핏',
                 '스쿼트', '데드', '벤치', '홈트', '워크아웃', 'workout', '자전거', '라이딩']),
]


def _get_cal_service():
    """선유듀오 캘린더 읽기용 서비스 (calendar.readonly; 시트 서비스와 별도 스코프)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    sa_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_KEY')
    if not sa_json:
        return None
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=['https://www.googleapis.com/auth/calendar.readonly'])
    return build('calendar', 'v3', credentials=creds)


def _fetch_cal_events_sync() -> list:
    """옥쥬와 빵빵이 캘린더의 '오늘(KST)' 일정 (raw Google event items). 블로킹 → executor에서 호출."""
    service = _get_cal_service()
    if not service:
        raise RuntimeError("서비스 계정(GOOGLE_SERVICE_ACCOUNT_KEY) 미설정")
    now = datetime.datetime.now(tz=KST)
    start = datetime.datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=KST)
    end = datetime.datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=KST)
    res = service.events().list(
        calendarId=SEONYUDUO_CAL_ID, timeMin=start.isoformat(), timeMax=end.isoformat(),
        singleEvents=True, orderBy='startTime', maxResults=50).execute()
    return res.get('items', [])


def _event_start_kst(ev: dict):
    """이벤트 start → KST aware datetime. 종일(date만)이면 None(시간 없음). 파싱 실패 None."""
    dt_str = ev.get('start', {}).get('dateTime')
    if not dt_str:
        return None  # 종일 일정
    try:
        return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00')).astimezone(KST)
    except ValueError:
        return None


def _detect_exercise_type(summary: str):
    """제목 → 운동 유형('테니스'/'러닝'/'워크아웃') 또는 None(운동 아님)."""
    s = (summary or '').lower()
    for 유형, kws in CAL_KEYWORDS:
        if any(kw in s for kw in kws):
            return 유형
    return None


def _infer_cal_scope(summary: str) -> list:
    """제목 태그로 피드백 대상: [식]→TS, [여니]→NY, 둘 다/없음 → ['TS','NY']."""
    s = summary or ''
    who = []
    if '[식]' in s:
        who.append('TS')
    if '[여니]' in s:
        who.append('NY')
    return who or ['TS', 'NY']


def _title_with_emoji(summary: str, emoji: str) -> str:
    """제목의 [식]/[여니] 태그는 앞에 두고, 유형 이모지는 운동명 바로 앞에 끼움.
    예) '[여니] 테니스' → '[여니] 🎾 테니스', 태그 없으면 '🎾 테니스 레슨'. (HTML escape 포함)"""
    s = (summary or '').strip()
    m = re.match(r'^((?:\[[^\]]*\]\s*)+)(.*)$', s)
    if m:
        tags = html.escape(re.sub(r'\s+', ' ', m.group(1).strip()))
        rest = html.escape(m.group(2).strip())
        core = f"{emoji} {rest}".strip() if rest else emoji
        return f"{tags} {core}".strip()
    return f"{emoji} {html.escape(s)}".strip()


def _who_disp(code: str) -> str:
    """담당자 코드(TS/NY) → 사용자 표시 라벨(식/여니). 미지정/기타는 그대로."""
    return WHO_LABEL.get(code, code)


def _load_cal_reminded() -> dict:
    try:
        with open(CAL_REMINDED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.warning(f"cal_reminded 읽기 실패: {e}")
        return {}


def _save_cal_reminded(d: dict):
    """오늘 이전 날짜 키 prune 후 원자적 저장.
    키: 'YYYY-MM-DD|eventid' / 'digest|YYYY-MM-DD' / 'dday|YYYY-MM-DD'."""
    today = datetime.datetime.now(tz=KST).date().isoformat()

    def _date_of(k):
        head, _, tail = k.partition('|')
        return tail if head in ('digest', 'dday') else head
    pruned = {k: v for k, v in d.items() if _date_of(k) >= today}
    try:
        tmp = CAL_REMINDED_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(pruned, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CAL_REMINDED_FILE)  # 원자적 교체
    except Exception as e:
        logging.error(f"cal_reminded 저장 실패: {e}")


async def _cal_broadcast(context, text: str) -> bool:
    """캡처된 선유듀오 그룹챗 전체로 발송. 그룹챗 없으면 False."""
    chats = _load_chats()
    if not chats:
        logging.info("선유듀오 그룹챗 미등록 → 캘린더 발송 스킵")
        return False
    for cid in chats:
        try:
            await context.bot.send_message(chat_id=int(cid), text=text, parse_mode='HTML')
        except Exception as e:
            logging.warning(f"캘린더 그룹챗 {cid} 전송 실패: {e}")
    return True


def _format_cal_digest(events: list) -> str:
    """오늘 일정 → 그룹용 HTML 다이제스트. 운동 일정엔 유형 이모지 부착."""
    now = datetime.datetime.now(tz=KST)
    wd = WEEKDAY_KO[now.weekday()]
    lines = [f"📅 <b>오늘의 일정</b> ({now.strftime('%Y-%m-%d')} {wd}요일)",
             "━━━━━━━━━━━━━━━"]
    for ev in events:
        raw_summary = ev.get('summary') or '(제목 없음)'
        sdt = _event_start_kst(ev)
        time_str = sdt.strftime('%H:%M') if sdt else '종일'
        유형 = _detect_exercise_type(ev.get('summary', ''))
        if 유형:
            title = _title_with_emoji(raw_summary, TYPE_EMOJI.get(유형, ''))
        else:
            title = html.escape(raw_summary)
        lines.append(f"• {time_str} · {title}")
    return '\n'.join(lines)


async def _send_daily_digest(context, state: dict):
    """오늘 다이제스트 발송 (중복방지 digest|date). 일정 0건이면 silent."""
    today = datetime.datetime.now(tz=KST).date().isoformat()
    dkey = f"digest|{today}"
    if dkey in state:
        return
    loop = asyncio.get_running_loop()
    try:
        events = await loop.run_in_executor(None, _fetch_cal_events_sync)
    except Exception as e:
        logging.error(f"캘린더 다이제스트 조회 실패: {e}")
        return
    if not events:
        logging.info("오늘 일정 없음 → 다이제스트 발송 안 함(silent)")
        state[dkey] = time.time()  # 무일정도 '오늘 처리됨'으로 기록 (폴링 반복조회 방지)
        _save_cal_reminded(state)
        return
    if await _cal_broadcast(context, _format_cal_digest(events)):
        state[dkey] = time.time()
        _save_cal_reminded(state)
        logging.info(f"캘린더 다이제스트 발송 ({len(events)}건)")


# ── 가족 생일/명절 + 'D-day |' 하이라이트 사전 알림 (30일/7일/1일 전) ──
# sisyphe_bot.check_dday_alerts에서 이관(MOVE). 같은 음력 기념일·같은 캘린더('D-day |' 이벤트)를
# 선유듀오 부부 그룹챗으로 발송. 06:00 다이제스트와 동일 시점·동일 state 파일(digest|date 옆에 dday|date).
LUNAR_EVENTS = [
    {'name': '🎂 혜자 생일', 'month': 3, 'day': 4},
    {'name': '🎂 동석 생일', 'month': 3, 'day': 12},
    {'name': '🎂 연순 생일', 'month': 5, 'day': 3},
    {'name': '🎂 맹호 생일', 'month': 8, 'day': 16},
    {'name': '🧧 설날', 'month': 1, 'day': 1},
    {'name': '🌕 추석', 'month': 8, 'day': 15},
]


def _collect_dday_highlights_sync() -> list:
    """음력 기념일(생일+설/추석) + 캘린더 'D-day |' 이벤트 → [{name, date}]. 블로킹 → executor."""
    from korean_lunar_calendar import KoreanLunarCalendar
    today = datetime.datetime.now(tz=KST).date()
    highlights = []

    # 1) 음력 기념일 (올해/내년 두 해치 펼쳐서 D-N 매칭)
    cal = KoreanLunarCalendar()
    for year in (today.year, today.year + 1):
        for ev in LUNAR_EVENTS:
            try:
                if cal.setLunarDate(year, ev['month'], ev['day'], False):
                    d = datetime.date(cal.solarYear, cal.solarMonth, cal.solarDay)
                    highlights.append({'name': ev['name'], 'date': d})
            except Exception:
                pass

    # 2) Google Calendar 'D-day |' 이벤트 (옥쥬와 빵빵이, 같은 캘린더)
    try:
        service = _get_cal_service()
        if service:
            time_min = datetime.datetime.combine(today, datetime.time.min).isoformat() + '+09:00'
            time_max = (datetime.datetime.combine(today + datetime.timedelta(days=400),
                                                  datetime.time.min).isoformat() + '+09:00')
            res = service.events().list(
                calendarId=SEONYUDUO_CAL_ID, timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy='startTime', maxResults=200).execute()
            for item in res.get('items', []):
                summary = item.get('summary', '')
                if summary.startswith('D-day |') or summary.startswith('D-day|'):
                    clean = summary.split('|', 1)[1].strip()
                    start = item['start'].get('date') or item['start'].get('dateTime', '')[:10]
                    d = datetime.date.fromisoformat(start)
                    highlights.append({'name': f'📌 {clean}', 'date': d})
    except Exception as e:
        logging.warning(f"D-Day 캘린더 조회 실패: {e}")
    return highlights


def _format_dday_alerts(highlights: list) -> str:
    """오늘 기준 D-30/D-7/D-1 매칭 항목만 HTML 메시지로. 매칭 없으면 빈 문자열."""
    today = datetime.datetime.now(tz=KST).date()
    alerts = []
    for ev in highlights:
        diff = (ev['date'] - today).days
        if diff == 30:
            alerts.append(f"📅 <b>[한 달 전]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-30)")
        elif diff == 7:
            alerts.append(f"📅 <b>[일주일 전]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-7)")
        elif diff == 1:
            alerts.append(f"📅 <b>[내일]</b> {ev['name']}\n    {ev['date'].strftime('%Y-%m-%d')} (D-1)")
    if not alerts:
        return ''
    return ("━━━━━━━━━━━━━━━\n<b>🔔 D-Day 알림</b>\n━━━━━━━━━━━━━━━\n\n"
            + "\n\n".join(alerts))


async def _send_dday_alerts(context, state: dict):
    """오늘 D-Day 알림 발송 (중복방지 dday|date). 매칭 없으면 silent (그래도 오늘 처리됨 기록)."""
    today = datetime.datetime.now(tz=KST).date().isoformat()
    dkey = f"dday|{today}"
    if dkey in state:
        return
    loop = asyncio.get_running_loop()
    try:
        highlights = await loop.run_in_executor(None, _collect_dday_highlights_sync)
    except Exception as e:
        logging.error(f"D-Day 하이라이트 수집 실패: {e}")
        return
    msg = _format_dday_alerts(highlights)
    if not msg:
        logging.info("오늘 D-Day 알림 없음 → 발송 안 함(silent)")
        state[dkey] = time.time()  # 무알림도 '오늘 처리됨' 기록 (폴링 반복조회 방지)
        _save_cal_reminded(state)
        return
    if await _cal_broadcast(context, msg):
        state[dkey] = time.time()
        _save_cal_reminded(state)
        logging.info("D-Day 알림 발송")


async def daily_cal_digest_job(context: ContextTypes.DEFAULT_TYPE):
    """run_daily 06:00 KST — 다이제스트 + D-Day 알림 punctual 발송."""
    state = _load_cal_reminded()
    await _send_daily_digest(context, state)
    await _send_dday_alerts(context, _load_cal_reminded())


async def cal_reminder_poll_job(context: ContextTypes.DEFAULT_TYPE):
    """run_repeating(5분): ①06시 다이제스트 따라잡기(재시작 대비) ②운동 1시간 전 리마인드."""
    now = datetime.datetime.now(tz=KST)
    today = now.date().isoformat()
    state = _load_cal_reminded()

    # ① 다이제스트 + D-Day 알림 따라잡기: 06:00~10:00 사이인데 아직 안 보냈으면 발송 (06시 다운 대비)
    if CAL_DIGEST_HOUR <= now.hour < CAL_DIGEST_CATCHUP_UNTIL:
        if f"digest|{today}" not in state:
            await _send_daily_digest(context, state)
            state = _load_cal_reminded()  # 갱신분 반영
        if f"dday|{today}" not in state:
            await _send_dday_alerts(context, state)
            state = _load_cal_reminded()  # 갱신분 반영

    # ② 운동 1시간 전 리마인드
    loop = asyncio.get_running_loop()
    try:
        events = await loop.run_in_executor(None, _fetch_cal_events_sync)
    except Exception as e:
        logging.error(f"리마인드 폴링 캘린더 조회 실패: {e}")
        return
    changed = False
    for ev in events:
        sdt = _event_start_kst(ev)
        if sdt is None:
            continue  # 종일/시간없음 → 1시간 전 스킵
        유형 = _detect_exercise_type(ev.get('summary', ''))
        if not 유형:
            continue
        reminder_at = sdt - datetime.timedelta(seconds=CAL_REMIND_LEAD)
        if not (reminder_at <= now < sdt):
            continue  # 1시간 전 지났고 + 아직 시작 전일 때만 (늦게 떠도 시작 전이면 발송)
        key = f"{today}|{ev.get('id', '')}"
        if key in state:
            continue  # 이미 발송
        who_list = _infer_cal_scope(ev.get('summary', ''))
        try:
            data = await loop.run_in_executor(None, _fetch_recent_sessions, 유형, who_list)
        except Exception as e:
            logging.error(f"리마인드용 최근기록 조회 실패: {e}")
            data = {'dates': [], 'rows': []}
        target = 'both' if len(who_list) == 2 else who_list[0]
        emoji = TYPE_EMOJI.get(유형, '🏃')
        title = _title_with_emoji(ev.get('summary', ''), emoji)
        header = (f"{title} · {sdt.strftime('%H:%M')} 시작\n"
                  f"━━━━━━━━━━━━━━━\n\n")
        msg = (header + _format_remind(유형, target, who_list, data)
               + _format_feedback_tips(유형))
        if await _cal_broadcast(context, msg):
            state[key] = time.time()
            changed = True
            logging.info(f"운동 리마인드 발송: {ev.get('summary', '')} ({유형}, {who_list})")
    if changed:
        _save_cal_reminded(state)


def main():
    if not TOKEN:
        print("Error: TELEGRAM_SEONYUDUO_BOT_TOKEN is missing.")
        sys.exit(1)
    application = ApplicationBuilder().token(TOKEN).build()
    # 모든 업데이트에서 그룹 chat_id 캡처 (비차단, 다른 핸들러보다 먼저)
    application.add_handler(TypeHandler(Update, capture_chat), group=-1)
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('help', cmd_help))
    application.add_handler(CommandHandler('whoami', cmd_whoami))
    application.add_handler(CommandHandler(['fit', 'log', 'ex'], cmd_log))
    application.add_handler(CommandHandler('ledger', cmd_ledger))  # 텔레그램 명령은 ASCII만 (한글 별칭 불가)
    application.add_handler(CommandHandler('remind', cmd_remind))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # ── 캘린더 다이제스트(06:00 KST) + 운동 1시간 전 리마인드(5분 폴링) ──
    # run_daily는 APScheduler 크론이라 pytz 타임존 필요 (sisyphe_bot 검증 패턴). 내부 연산은 KST.
    jq = application.job_queue
    if jq is not None:
        try:
            import pytz
            digest_time = datetime.time(hour=CAL_DIGEST_HOUR, minute=0, second=0,
                                        tzinfo=pytz.timezone('Asia/Seoul'))
        except Exception:
            digest_time = datetime.time(hour=CAL_DIGEST_HOUR, minute=0, second=0, tzinfo=KST)
        jq.run_daily(daily_cal_digest_job, time=digest_time, name='cal_daily_digest')
        jq.run_repeating(cal_reminder_poll_job, interval=CAL_POLL_INTERVAL, first=30,
                         name='cal_reminder_poll')
    else:
        logging.warning("JobQueue 미설치(python-telegram-bot[job-queue]) → 캘린더 잡 비활성. "
                        "봇 본기능(운동기록/remind/ledger)은 정상. VM엔 설치돼 있어 정상 동작.")

    print("선유듀오 운동기록 봇 시작")
    application.run_polling()


if __name__ == '__main__':
    main()
