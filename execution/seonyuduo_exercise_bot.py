"""선유듀오 운동기록 봇 (@SeonyuDuo_bot)

자연어 운동 입력 → Claude Haiku 자동 분류 → 미리보기 확인 → 선유듀오 시트 '운동' 탭에 기록.

특징:
  - 한 메시지에 여러 카테고리(예: 포핸드…백핸드…발리…)가 섞이면 카테고리별로 분리해 여러 행으로 기록.
  - 담당자(TS/NY)는 보낸 사람 텔레그램 계정으로 자동 구분 (미등록 시 [TS][NY] 1회 등록).
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

PENDING_TTL = 900  # 초; 오래된 pending 정리 기준

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
        with open(SEONYUDUO_CHATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"chats 저장 실패: {e}")


async def capture_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """모든 업데이트에서 그룹/슈퍼그룹 chat_id를 비차단 캡처 (group=-1 등록).
    저장만 하고 propagation은 막지 않아 기존 핸들러는 정상 동작한다."""
    ch = update.effective_chat
    if not ch or ch.type not in ('group', 'supergroup'):
        return
    chats = _load_chats()
    key = str(ch.id)
    if key not in chats:
        chats[key] = {'type': ch.type, 'title': ch.title or ''}
        _save_chats(chats)
        logging.info(f"선유듀오 그룹챗 캡처: {key} ({ch.title})")


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
            f"👤 {who}\n━━━━━━━━━━━━━━━\n")
    body = '\n\n'.join(_entry_block(i, e, n) for i, e in enumerate(es, 1))
    return _warn_lines(batch) + head + body


def _format_saved(batch: dict, rng) -> str:
    es = batch['entries']
    n = len(es)
    who = es[0].get('담당자', '-') if es else '-'
    head = (f"✅ <b>운동 시트에 저장했어요{f' ({n}건)' if n > 1 else ''}</b>\n"
            f"👤 {who}\n━━━━━━━━━━━━━━━\n")
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
        "/help 도움말, /whoami 담당자 확인",
        parse_mode='HTML')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>사용법</b>\n"
        "운동 내용을 자연어로 보내면 → AI가 유형/카테고리/장소/날짜/내용 분류 → 미리보기 확인 후 [저장]\n\n"
        "• 한 메시지에 여러 카테고리를 적으면 <b>카테고리별로 행을 나눠</b> 저장해요.\n"
        "• 유형: 테니스 / 러닝 / 워크아웃 (자동)\n"
        "• 테니스 카테고리: 포핸드·백핸드·슬라이스·포핸드 발리·백핸드 발리·서브·공통\n"
        "• 러닝/워크아웃 카테고리: 종목명 자유\n"
        "• 날짜 미기재 시 오늘\n\n"
        "👥 <b>그룹</b>: 일반 텍스트 대신 <code>/fit 운동내용</code> 으로 보내세요 (DM은 그냥 텍스트로).\n"
        "/whoami — 내 담당자(TS/NY) 확인·변경",
        parse_mode='HTML')


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    who = load_user_map().get(uid)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("TS", callback_data="setwho:TS"),
        InlineKeyboardButton("NY", callback_data="setwho:NY")]])
    cur = f"현재 담당자: <b>{who}</b>" if who else "아직 담당자가 등록되지 않았어요."
    await update.message.reply_text(cur + "\n아래에서 선택/변경할 수 있어요.",
                                    parse_mode='HTML', reply_markup=kb)


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
            InlineKeyboardButton("TS", callback_data="reg:TS"),
            InlineKeyboardButton("NY", callback_data="reg:NY")]])
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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ''
    uid = str(update.effective_user.id)

    # 신규 담당자 등록 (분류 결과 대기 중)
    if data.startswith("reg:"):
        who = data.split(":", 1)[1]
        m = load_user_map(); m[uid] = who; save_user_map(m)
        batch = context.user_data.pop('await_register', None)
        if not batch:
            await q.edit_message_text(f"✅ {who}로 등록됐어요. 운동 내용을 다시 보내주세요.")
            return
        for e in batch['entries']:
            e['담당자'] = who
        await _send_preview(q.message, context, batch)
        return

    # /whoami 담당자 설정/변경
    if data.startswith("setwho:"):
        who = data.split(":", 1)[1]
        m = load_user_map(); m[uid] = who; save_user_map(m)
        await q.edit_message_text(f"✅ 담당자를 <b>{who}</b>로 설정했어요.", parse_mode='HTML')
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))
    print("선유듀오 운동기록 봇 시작")
    application.run_polling()


if __name__ == '__main__':
    main()
