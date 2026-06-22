import os
import sys
import json
import asyncio
import logging
from io import BytesIO
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta, timezone
from telegram import Bot
import holidays
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

# 로깅 설정
logging.basicConfig(level=logging.INFO)
# httpx INFO 로그가 sendMessage/sendPhoto URL(토큰 path 포함)을 찍으므로 차단
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── 종목 표 PNG 렌더링 설정 ───────────────────────────────
FONT_REGULAR = '/home/ubuntu/fonts/pretendard/Pretendard-Regular.otf'
FONT_BOLD = '/home/ubuntu/fonts/pretendard/Pretendard-Bold.otf'

# 2배 해상도로 렌더링 (retina 디스플레이 대응)
SCALE = 2

# 컬럼 폭 (1x 기준 픽셀)
COL_WIDTHS = {
    '#':   40 * SCALE,
    '종목': 160 * SCALE,
    '비중': 75 * SCALE,
    '당일': 95 * SCALE,
    '기여': 70 * SCALE,
    '누적': 105 * SCALE,
}
ROW_HEIGHT = 30 * SCALE
PADDING = 16 * SCALE
TITLE_HEIGHT = 38 * SCALE
FONT_SIZE = 15 * SCALE
TITLE_FONT_SIZE = 17 * SCALE

# Light theme
BG_COLOR = (255, 255, 255)
HEADER_BG = (153, 27, 27)         # 와인 빨강 (#991B1B, red-800)
HEADER_TEXT_COLOR = (255, 255, 255)  # 헤더 위 글자 (흰색)
ALT_ROW_BG = (248, 248, 248)
RISK_ROW_BG = (220, 220, 220)     # 누적 -10% 이하 위험 표시 (엷은 회색)
TEXT_COLOR = (0, 0, 0)
LINE_COLOR = (200, 200, 200)
POSITIVE_COLOR = (220, 38, 38)    # 한국 컨벤션: 양수 빨강
NEGATIVE_COLOR = (37, 99, 235)    # 음수 파랑
RISK_THRESHOLD = -10.0

def is_korean_trading_day():
    """한국 거래일 여부 확인 (주말 + 공휴일 제외)"""
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).date()
    kr_holidays = holidays.KR(years=today.year)
    if today.weekday() >= 5:
        logging.info(f"{today} 주말 - 리포트 스킵")
        return False
    if today in kr_holidays:
        logging.info(f"{today} 공휴일({kr_holidays.get(today)}) - 리포트 스킵")
        return False
    return True

file_name = 'Wrap_NAV.xlsx'

def get_day_of_week_kor():
    """한글 요일 반환"""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[datetime.now().weekday()]

def get_report_date():
    """리포트 기준 날짜 결정 (16시 기준)"""
    from datetime import timezone, timedelta as td
    
    # KST 시간대 (UTC+9)
    kst = timezone(td(hours=9))
    now_kst = datetime.now(kst)
    
    # 15시 이전이면 전일, 15시 이후면 당일
    if now_kst.hour < 15:
        report_date = now_kst.date() - td(days=1)
    else:
        report_date = now_kst.date()
    
    return report_date

def get_latest_nav():
    """최신 기준가 가져오기"""
    df = pd.read_excel(file_name, sheet_name='기준가')
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date')
    
    # 리포트 날짜 기준으로 데이터 가져오기
    report_date = get_report_date()

    # 리포트 날짜 이하로 필터
    df_filtered = df[df.index.date <= report_date]
    if df_filtered.empty:
        df_filtered = df

    # 각 포트폴리오별 NaN이 아닌 마지막 값 가져오기
    nav_map = {
        '삼성 트루밸류': '트루밸류',
        'NH Value ESG': 'Value ESG',
        'DB 개방형 랩': '개방형 랩',
        # 'DB 목표전환형 5차': '목표전환형 5차',  # DB 5차 완료 (2026-06-19 청산, +7.72%)
        # 'NH 목표전환형 4호': '목표전환형 4호',  # NH 4호 완료 (2026-06-19 청산, +5.38%)
        # 'NH 목표전환형 3호': '목표전환형 3호',  # NH 3호 완료 (2026-05-27 청산, 목표달성)
        # 'DB 목표전환형 4차': '목표전환형 4차',  # DB 4차 완료 (2026-05-27 청산, 목표달성)
        # 'NH 목표전환형 2호': '목표전환형 2호',  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
        # 'DB 목표전환형 3차': '목표전환형 3차',  # DB 3차 완료 (2026-05-06, +7.97%, 목표 7.5% 초과)
        # 'DB 목표전환형 2차 / NH 목표전환형 1호': '목표전환형 2차',  # 2차+1호 완료 (2026-04-15, DB 7.5% / NH 6.5% 달성)
    }
    nav_data = {}
    for display_name, col_name in nav_map.items():
        if col_name in df_filtered.columns:
            valid = df_filtered[col_name].dropna()
            if not valid.empty:
                nav_data[display_name] = valid.iloc[-1]

    latest_date = df_filtered.index[-1]
    return latest_date, nav_data

def get_latest_returns():
    """최신 수익률 가져오기"""
    df = pd.read_excel(file_name, sheet_name='수익률')
    
    if len(df) == 0:
        return {}
    
    latest_row = df.iloc[-1]
    
    # 트루밸류, KOSPI, KOSDAQ 수익률 추출
    returns_data = {}
    
    for product in ['트루밸류', 'KOSPI', 'KOSDAQ']:  # NH 4호/DB 5차 청산 (2026-06-19)
        returns_data[product] = {
            '1D': latest_row.get(f'{product}_1D', 'N/A'),
            '1W': latest_row.get(f'{product}_1W', 'N/A'),
            '1M': latest_row.get(f'{product}_1M', 'N/A'),
            '3M': latest_row.get(f'{product}_3M', 'N/A'),
            '6M': latest_row.get(f'{product}_6M', 'N/A'),
            '1Y': latest_row.get(f'{product}_1Y', 'N/A'),
            'YTD': latest_row.get(f'{product}_YTD', 'N/A')
        }

    return returns_data

def get_portfolio_holdings():
    """portfolio_data.json에서 일반형 / 목표전환형 그룹 추출

    portfolio_data.json은 create_portfolio_tables.py가 15:35 자동 업데이트 사이클에서
    당일 종가 기준으로 미리 갱신해 둠. 키는 'PORTFOLIO_GROUPS'의 combined 명을 사용:
    - 일반형: '삼성 트루밸류 / NH Value ESG / DB 개방형'
    - 목표전환형: 'NH 목표전환형 N호 / DB 목표전환형 M차' (운용 중일 때만 존재)
    """
    json_path = 'portfolio_data.json'
    if not os.path.exists(json_path):
        logging.warning(f"{json_path} not found — holdings 섹션 생략")
        return None, None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logging.warning(f"{json_path} 로드 실패: {e}")
        return None, None

    general = None
    target = None
    for key, stocks in data.items():
        if not key or key.startswith('_'):
            continue
        if not isinstance(stocks, list) or not stocks:
            continue
        if '목표전환형' in key:
            target = (key, stocks)
        elif '트루밸류' in key:
            general = (key, stocks)

    return general, target

def _color_for(text):
    """양수(+) 빨강, 음수(-) 파랑, 그 외 검정"""
    if not text or text == '-':
        return TEXT_COLOR
    if text.startswith('+'):
        return POSITIVE_COLOR
    if text.startswith('-'):
        return NEGATIVE_COLOR
    return TEXT_COLOR


def render_holdings_png(title, stocks):
    """랩 종목 구성을 PNG 표로 렌더링 (비중 내림차순, 가운데 정렬)

    컬럼: # / 종목 / 비중 / 당일 / 기여 / 누적
    위험 표시: 누적 ≤ -10% 행은 엷은 회색 배경
    기여도 = 비중 × 당일 수익률 / 100
    """
    headers = list(COL_WIDTHS.keys())
    width = sum(COL_WIDTHS.values()) + PADDING * 2
    sorted_stocks = sorted(stocks, key=lambda s: s.get('weight') or 0, reverse=True)
    height = TITLE_HEIGHT + ROW_HEIGHT * (len(sorted_stocks) + 1) + PADDING * 2

    img = Image.new('RGB', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(FONT_BOLD, TITLE_FONT_SIZE)
    header_font = ImageFont.truetype(FONT_BOLD, FONT_SIZE)
    body_font = ImageFont.truetype(FONT_REGULAR, FONT_SIZE)

    # 제목
    draw.text((PADDING, PADDING), f"■ {title}", fill=TEXT_COLOR, font=title_font)

    # 헤더 배경 + 텍스트 (가운데 정렬)
    header_y = PADDING + TITLE_HEIGHT
    draw.rectangle(
        [PADDING, header_y, width - PADDING, header_y + ROW_HEIGHT],
        fill=HEADER_BG,
    )
    x = PADDING
    for h in headers:
        col_w = COL_WIDTHS[h]
        text_w = draw.textlength(h, font=header_font)
        cx = x + (col_w - text_w) / 2
        draw.text((cx, header_y + 6 * SCALE), h, fill=HEADER_TEXT_COLOR, font=header_font)
        x += col_w

    line_y = header_y + ROW_HEIGHT
    draw.line([(PADDING, line_y), (width - PADDING, line_y)], fill=LINE_COLOR, width=1)

    # 데이터 행
    for idx, s in enumerate(sorted_stocks, 1):
        y = line_y + (idx - 1) * ROW_HEIGHT

        name = s.get('name', '?')
        weight = s.get('weight')
        today_ret = s.get('today_return')
        cum_ret = s.get('cumulative_return')
        contrib = (weight / 100) * today_ret if (weight is not None and today_ret is not None) else None

        is_risky = cum_ret is not None and cum_ret <= RISK_THRESHOLD
        if is_risky:
            row_bg = RISK_ROW_BG
        elif idx % 2 == 0:
            row_bg = ALT_ROW_BG
        else:
            row_bg = None
        if row_bg:
            draw.rectangle(
                [PADDING, y, width - PADDING, y + ROW_HEIGHT],
                fill=row_bg,
            )

        today_str = f"{today_ret:+.1f}%" if today_ret is not None else "-"
        contrib_str = f"{contrib:+.1f}" if contrib is not None else "-"
        cum_str = f"{cum_ret:+.1f}%" if cum_ret is not None else "-"

        cells = [
            (f"#{idx}", TEXT_COLOR),
            (name, TEXT_COLOR),
            (f"{weight:.1f}%" if weight is not None else "-", TEXT_COLOR),
            (today_str, _color_for(today_str)),
            (contrib_str, _color_for(contrib_str)),
            (cum_str, _color_for(cum_str)),
        ]

        x = PADDING
        for (cell_text, cell_color), h in zip(cells, headers):
            col_w = COL_WIDTHS[h]
            text_w = draw.textlength(cell_text, font=body_font)
            cx = x + (col_w - text_w) / 2
            draw.text((cx, y + 6 * SCALE), cell_text, fill=cell_color, font=body_font)
            x += col_w

    return img


def format_message(date, nav_data, returns_data):
    """텔레그램 텍스트 메시지 포맷 (HTML) — 헤더 + 기준가 + 수익률만 (종목 표는 별도 사진 전송)"""
    LINE = "━━━━━━━━━━━━━━━"

    # 실제 데이터 날짜 기준
    data_date = date.date() if hasattr(date, 'date') else date
    day_of_week = ["월", "화", "수", "목", "금", "토", "일"][data_date.weekday()]
    date_str = f"{data_date.strftime('%Y-%m-%d')} ({day_of_week})"

    msg = f"<b>📊 포트폴리오 리포트</b>\n{date_str}\n"

    # 기준가
    msg += f"{LINE}\n<b>💰 기준가</b>\n{LINE}\n"
    for name, value in nav_data.items():
        msg += f"<b>{name}  {value:,.2f}</b>\n"

    # 수익률
    msg += f"{LINE}\n<b>📈 수익률</b>\n{LINE}\n"
    display_names = {
        '트루밸류': '삼성 트루밸류',
        # '목표전환형 5차': 'DB 목표전환형 5차',  # DB 5차 완료 (2026-06-19 청산, +7.72%)
        # '목표전환형 4호': 'NH 목표전환형 4호',  # NH 4호 완료 (2026-06-19 청산, +5.38%)
        # '목표전환형 3호': 'NH 목표전환형 3호',  # NH 3호 완료 (2026-05-27 청산, 목표달성)
        # '목표전환형 4차': 'DB 목표전환형 4차',  # DB 4차 완료 (2026-05-27 청산, 목표달성)
        # '목표전환형 2호': 'NH 목표전환형 2호',  # NH 2호 완료 (2026-05-06, +7.26%, 목표 6.5% 초과)
        # '목표전환형 3차': 'DB 목표전환형 3차',  # DB 3차 완료 (2026-05-06, +7.97%, 목표 7.5% 초과)
        'KOSPI': 'KOSPI',
        'KOSDAQ': 'KOSDAQ',
    }
    periods = ['1D', '1W', '1M', '3M', '6M', '1Y', 'YTD']
    for product in ['트루밸류', 'KOSPI', 'KOSDAQ']:  # NH 4호/DB 5차 청산 (2026-06-19)
        if product in returns_data:
            returns = returns_data[product]
            # N/A가 아닌 항목만 표시
            valid_periods = []
            for p in periods:
                val = returns.get(p, 'N/A')
                if not pd.isna(val) and val != 'N/A':
                    if p == 'YTD':
                        valid_periods.append(f"<b><u>{p} {val}</u></b>")
                    else:
                        valid_periods.append(f"{p} {val}")
            if valid_periods:
                name = display_names.get(product, product)
                msg += f"* <b>{name}</b>\n"
                # 3개씩 끊어서 줄바꿈
                for i in range(0, len(valid_periods), 3):
                    msg += " | ".join(valid_periods[i:i+3]) + "\n"
                msg += "\n"

    return msg

async def send_report(no_send=False):
    """리포트 생성 및 전송 (거래일만)"""
    if not is_korean_trading_day():
        print("거래일이 아니므로 리포트를 생략합니다.")
        return

    logging.info("1. 기준가 데이터 읽기...")
    date, nav_data = get_latest_nav()

    logging.info("2. 수익률 데이터 읽기...")
    returns_data = get_latest_returns()

    logging.info("3. 일반형/목표전환형 종목 구성 로드...")
    general, target = get_portfolio_holdings()

    logging.info("4. 메시지 포맷팅...")
    message = format_message(date, nav_data, returns_data)

    if not no_send:
        token = os.getenv("TELEGRAM_SISYPHE_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logging.error("TELEGRAM_SISYPHE_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")
            sys.exit(1)
        logging.info("5. 텔레그램 전송...")
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')

        # 종목 구성 PNG 표 전송 (일반형 + 운용 중인 목표전환형)
        for section_title, holdings in [('일반형 랩', general), ('목표전환형 랩', target)]:
            if not holdings:
                continue
            _, stocks = holdings
            img = render_holdings_png(section_title, stocks)
            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            await bot.send_photo(chat_id=chat_id, photo=buf, caption=f"■ {section_title}")
            logging.info(f"{section_title} 사진 전송 완료 ({img.size[0]}x{img.size[1]}px)")

    logging.info("완료!")
    print(f"\n전송된 메시지:\n{message}")

if __name__ == "__main__":
    no_send = '--no-send' in sys.argv
    asyncio.run(send_report(no_send=no_send))
