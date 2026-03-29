import logging
import datetime
import os
import sys

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 환경 변수 로드
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env'))
TOKEN = os.getenv("RESEARCH_BOT_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

KST = datetime.timezone(datetime.timedelta(hours=9))

# DB 초기화
from messages_db import add_message, get_messages_by_date, get_today_count, mark_processed


def fetch_article(url):
    """URL에서 기사 본문 텍스트 추출"""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        # 네이버 블로그: 모바일 URL로 변환 (JS 렌더링 우회)
        import re as _re
        naver_match = _re.match(r'https?://blog\.naver\.com/([^/]+)/(\d+)', url)
        if naver_match:
            url = f'https://m.blog.naver.com/{naver_match.group(1)}/{naver_match.group(2)}'

        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, 'html.parser')

        # 불필요한 태그 제거
        for tag in soup.select('script, style, nav, header, footer, aside, .ad, .advertisement'):
            tag.decompose()

        # 기사 본문 추출 (일반적인 기사 컨테이너)
        article = (
            soup.select_one('div.se-main-container') or  # 네이버 블로그
            soup.select_one('div.__viewer_container') or  # 네이버 블로그 v2
            soup.select_one('article') or
            soup.select_one('[class*="article_body"]') or
            soup.select_one('[class*="newsct_article"]') or
            soup.select_one('[id*="articleBody"]') or
            soup.select_one('[class*="story-body"]') or
            soup.select_one('[class*="content"]') or
            soup.select_one('main')
        )

        if article:
            text = article.get_text(separator='\n', strip=True)
        else:
            # fallback: p 태그들 합치기
            paragraphs = soup.find_all('p')
            text = '\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)

        # 제목 추출
        title = ''
        title_tag = soup.select_one('h1') or soup.select_one('title')
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 너무 긴 본문은 잘라냄 (토큰 절약)
        if len(text) > 3000:
            text = text[:3000] + '...(truncated)'

        return f"[제목] {title}\n\n{text}" if title else text

    except Exception as e:
        logging.warning(f"Article fetch failed for {url}: {e}")
        return None


def now_kst():
    return datetime.datetime.now(tz=KST)


def today_str():
    return now_kst().strftime('%Y-%m-%d')


# ============================================================
# 메시지 핸들러
# ============================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.message
    text = msg.text or ''
    url = None

    # URL 추출
    if msg.entities:
        for entity in msg.entities:
            if entity.type in ('url', 'text_link'):
                if entity.type == 'text_link':
                    url = entity.url
                else:
                    url = text[entity.offset:entity.offset + entity.length]
                break

    # 전달된 메시지 처리
    forward_source = None
    if msg.forward_origin:
        try:
            if hasattr(msg.forward_origin, 'sender_user') and msg.forward_origin.sender_user:
                forward_source = msg.forward_origin.sender_user.full_name
            elif hasattr(msg.forward_origin, 'chat') and msg.forward_origin.chat:
                forward_source = msg.forward_origin.chat.title
            else:
                forward_source = str(msg.forward_origin.type)
        except:
            forward_source = 'unknown'

    # URL이 있으면 기사 본문 스크래핑
    article_content = None
    if url:
        article_content = fetch_article(url)

    add_message(
        timestamp=now_kst().isoformat(),
        message_type='text',
        text_content=text,
        url=url,
        article_content=article_content,
        forward_source=forward_source,
        telegram_message_id=msg.message_id
    )

    count = get_today_count(today_str())
    reply = f"📥 저장됨 (오늘 {count}건)"
    if article_content:
        reply += f"\n📰 기사 본문 수집 완료"
    await msg.reply_text(reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.message
    caption = msg.caption or ''

    # 사진 다운로드
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media', today_str())
    os.makedirs(media_dir, exist_ok=True)

    photo = msg.photo[-1]  # 최고 해상도
    file = await photo.get_file()
    file_path = os.path.join(media_dir, f"{msg.message_id}.jpg")
    await file.download_to_drive(file_path)

    add_message(
        timestamp=now_kst().isoformat(),
        message_type='photo',
        text_content=caption,
        media_path=file_path,
        telegram_message_id=msg.message_id
    )

    count = get_today_count(today_str())
    await msg.reply_text(f"📸 사진 저장됨 (오늘 {count}건)")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return

    msg = update.message
    caption = msg.caption or ''

    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'media', today_str())
    os.makedirs(media_dir, exist_ok=True)

    doc = msg.document
    file = await doc.get_file()
    file_path = os.path.join(media_dir, doc.file_name or f"{msg.message_id}")
    await file.download_to_drive(file_path)

    add_message(
        timestamp=now_kst().isoformat(),
        message_type='document',
        text_content=caption,
        media_path=file_path,
        telegram_message_id=msg.message_id
    )

    count = get_today_count(today_str())
    await msg.reply_text(f"📎 파일 저장됨 (오늘 {count}건)")


# ============================================================
# 명령어 핸들러
# ============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Research Notes Bot\n\n"
        "텍스트, 링크, 사진, 파일을 보내면 자동으로 저장됩니다.\n"
        "매일 23:30에 Claude AI가 정리하여 Notion에 게시합니다.\n\n"
        "/status - 오늘 수집 현황\n"
        "/summary - 수동 요약 실행\n"
        "/help - 도움말"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    count = get_today_count(today_str())
    await update.message.reply_text(f"📊 오늘 ({today_str()}) 수집: {count}건")


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """수동 요약 실행"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await update.message.reply_text("⏳ 요약 중...")
    await run_daily_summary(context, today_str())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 <b>사용법</b>\n\n"
        "메시지를 보내면 자동 저장됩니다.\n"
        "텍스트, 링크, 사진, 파일, 전달 메시지 모두 가능.\n\n"
        "<b>명령어</b>\n"
        "/status - 오늘 수집 현황\n"
        "/summary - 수동 요약 실행\n"
        "/help - 이 도움말",
        parse_mode='HTML'
    )


# ============================================================
# 일일 요약 작업
# ============================================================
async def run_daily_summary(context, date_str):
    """하루치 메시지를 Claude로 요약 → Notion에 게시"""
    messages = get_messages_by_date(date_str)

    if not messages:
        try:
            await context.bot.send_message(
                chat_id=ALLOWED_CHAT_ID,
                text=f"📝 {date_str}: 수집된 리서치 노트가 없습니다."
            )
        except:
            pass
        logging.info(f"No messages for {date_str}")
        return

    try:
        # 1. Claude API 요약
        from summarizer import summarize_daily_notes, extract_topics, extract_stocks, extract_image_indices
        summary = summarize_daily_notes(messages, date_str)
        topics = extract_topics(summary)
        stocks = extract_stocks(summary)
        image_indices = extract_image_indices(summary)

        # 이미지 파일 경로 수집
        images = []
        for idx in image_indices:
            if 1 <= idx <= len(messages):
                msg = messages[idx - 1]
                if msg.get('media_path') and os.path.exists(msg['media_path']):
                    images.append((msg['media_path'], idx))

        # 2. Notion에 게시
        from notion_publisher import publish_to_notion
        publish_to_notion(summary, date_str, topics, stocks, images)

        # 3. 처리 완료 표시
        mark_processed(date_str)

        # 4. 텔레그램 알림
        topic_str = ', '.join(topics) if topics else '없음'
        stock_str = ', '.join(stocks) if stocks else '없음'
        await context.bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            text=f"✅ {date_str} 리서치 노트 정리 완료!\n"
                 f"📊 {len(messages)}건 → Notion 게시됨\n"
                 f"🏷️ 토픽: {topic_str}\n"
                 f"📈 종목: {stock_str}",
            parse_mode='HTML'
        )
        logging.info(f"Daily summary done: {len(messages)} messages, topics: {topics}")

    except Exception as e:
        logging.error(f"Daily summary failed: {e}")
        try:
            await context.bot.send_message(
                chat_id=ALLOWED_CHAT_ID,
                text=f"❌ {date_str} 요약 실패: {str(e)}"
            )
        except:
            pass


async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """매일 23:30 KST 자동 실행"""
    logging.info("Daily summary job started")
    await run_daily_summary(context, today_str())


# ============================================================
# 메인
# ============================================================
if __name__ == '__main__':
    if not TOKEN:
        print("Error: RESEARCH_BOT_TOKEN is missing.")
        sys.exit(1)

    print(f"Research Bot starting...")
    print(f"  Allowed chat: {ALLOWED_CHAT_ID}")

    application = ApplicationBuilder().token(TOKEN).build()

    # 명령어
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('status', cmd_status))
    application.add_handler(CommandHandler('summary', cmd_summary))
    application.add_handler(CommandHandler('help', cmd_help))

    # 메시지 수집
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # 일일 요약 스케줄 (23:30 KST)
    job_queue = application.job_queue
    try:
        import pytz
        kst_tz = pytz.timezone('Asia/Seoul')
        summary_time = datetime.time(hour=23, minute=0, second=0, tzinfo=kst_tz)
    except:
        summary_time = datetime.time(hour=23, minute=0, second=0)

    job_queue.run_daily(daily_summary_job, time=summary_time)

    print(f"  Daily summary: 23:00 KST")
    print(f"  Bot ready!")

    application.run_polling()
