import os
import re
from notion_client import Client


def publish_to_notion(summary_markdown, date_str, topics, stocks):
    """Notion 데이터베이스에 일별 리서치 요약 페이지 생성"""
    notion = Client(auth=os.getenv("NOTION_API_KEY"))
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID not set")

    # 제목: YYYYMMDD_Research Notes_Topic1, Topic2
    date_compact = date_str.replace('-', '')
    topic_str = ', '.join(topics) if topics else 'General'
    title = f"{date_compact}_Research Notes_{topic_str}"

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Date": {"date": {"start": date_str}},
        "Topics": {"multi_select": [{"name": t} for t in topics]},
    }

    # Stocks 속성 (multi_select)
    if stocks:
        properties["Ticker"] = {"multi_select": [{"name": s} for s in stocks]}

    notion.pages.create(
        parent={"database_id": database_id},
        icon={"emoji": "📝"},
        properties=properties,
        children=markdown_to_blocks(summary_markdown)
    )


def markdown_to_blocks(md_text):
    """마크다운 텍스트를 Notion 블록 리스트로 변환"""
    blocks = []
    lines = md_text.split('\n')

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 토픽 라인은 건너뛰기 (이미 속성으로 저장)
        if stripped.startswith('토픽:') or stripped.startswith('토픽 :'):
            continue

        # Heading 2
        if stripped.startswith('## '):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": stripped[3:]}}]}
            })
        # Heading 3
        elif stripped.startswith('### '):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"text": {"content": stripped[4:]}}]}
            })
        # Bullet list
        elif stripped.startswith('- ') or stripped.startswith('* '):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_rich_text(stripped[2:])}
            })
        # Numbered list
        elif re.match(r'^\d+\.\s', stripped):
            content = re.sub(r'^\d+\.\s', '', stripped)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": parse_rich_text(content)}
            })
        # Quote
        elif stripped.startswith('> '):
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": [{"text": {"content": stripped[2:]}}]}
            })
        # Divider
        elif stripped == '---' or stripped == '***':
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        # Paragraph
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": parse_rich_text(stripped)}
            })

    # Notion API 제한: 한 번에 최대 100블록
    return blocks[:100]


def parse_rich_text(text):
    """볼드/링크를 Notion rich_text로 변환"""
    rich = []
    # **bold** 처리
    parts = re.split(r'(\*\*[^*]+\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            rich.append({
                "text": {"content": part[2:-2]},
                "annotations": {"bold": True}
            })
        elif part:
            # URL 감지
            url_parts = re.split(r'(https?://\S+)', part)
            for up in url_parts:
                if up.startswith('http://') or up.startswith('https://'):
                    rich.append({
                        "text": {"content": up, "link": {"url": up}}
                    })
                elif up:
                    rich.append({"text": {"content": up}})
    return rich if rich else [{"text": {"content": text}}]
