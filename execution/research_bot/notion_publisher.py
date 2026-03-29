import os
import re
from notion_client import Client


def _find_existing_page(database_id, date_str):
    """같은 날짜의 기존 페이지가 있는지 검색 (직접 HTTP 호출)"""
    try:
        import urllib.request, json
        api_key = os.getenv("NOTION_API_KEY")
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            data=json.dumps({"filter": {"property": "날짜", "date": {"equals": date_str}}}).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            results = json.loads(resp.read().decode())
        if results.get('results'):
            return results['results'][0]['id']
    except Exception as e:
        import logging
        logging.warning(f"Find existing page failed: {e}")
    return None


def publish_to_notion(summary_markdown, date_str, topics, stocks, images=None):
    """Notion 데이터베이스에 일별 리서치 요약 페이지 생성/업데이트 (이미지 포함)"""
    notion = Client(auth=os.getenv("NOTION_API_KEY"))
    database_id = os.getenv("NOTION_DATABASE_ID")

    if not database_id:
        raise RuntimeError("NOTION_DATABASE_ID not set")

    date_compact = date_str.replace('-', '')
    title = f"{date_compact}_Research Notes"

    # 이미지를 GitHub에 업로드하고 URL 맵 생성
    img_url_map = {}  # {idx: url}
    if images:
        for img_path, img_idx in images:
            url = upload_image_to_github(img_path, date_str, img_idx)
            if url:
                img_url_map[img_idx] = url

    blocks = markdown_to_blocks(summary_markdown, img_url_map)

    existing_page_id = _find_existing_page(database_id, date_str)

    if existing_page_id:
        # 기존 페이지에 추가: 구분선 + 새 요약 append
        append_blocks = [
            {"object": "block", "type": "divider", "divider": {}}
        ] + blocks

        notion.blocks.children.append(
            block_id=existing_page_id,
            children=append_blocks[:100]
        )
        # 속성 업데이트 (기존 값에 추가 병합)
        import urllib.request as _ur
        import json as _json
        try:
            req = _ur.Request(
                f"https://api.notion.com/v1/pages/{existing_page_id}",
                headers={"Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}", "Notion-Version": "2022-06-28"}
            )
            with _ur.urlopen(req, timeout=15) as resp:
                existing_props = _json.loads(resp.read().decode()).get("properties", {})

            # Research Topic 병합
            existing_topics = ""
            rt = existing_props.get("Research Topic", {})
            if rt.get("rich_text"):
                existing_topics = rt["rich_text"][0].get("text", {}).get("content", "")
            all_topics = set(t.strip() for t in existing_topics.split(",") if t.strip())
            all_topics.update(topics)

            # Ticker 병합
            existing_tickers = ""
            tk = existing_props.get("Ticker", {})
            if tk.get("rich_text"):
                existing_tickers = tk["rich_text"][0].get("text", {}).get("content", "")
            all_tickers = set(t.strip() for t in existing_tickers.split(",") if t.strip())
            all_tickers.update(stocks)
        except:
            all_topics = set(topics)
            all_tickers = set(stocks)

        update_props = {}
        if all_topics:
            update_props["Research Topic"] = {"rich_text": [{"text": {"content": ", ".join(sorted(all_topics))}}]}
        if all_tickers:
            update_props["Ticker"] = {"rich_text": [{"text": {"content": ", ".join(sorted(all_tickers))}}]}
        if update_props:
            notion.pages.update(page_id=existing_page_id, properties=update_props)
    else:
        # 새 페이지 생성
        properties = {
            "이름": {"title": [{"text": {"content": title}}]},
            "날짜": {"date": {"start": date_str}},
            "Research Topic": {"rich_text": [{"text": {"content": ", ".join(topics)}}]},
        }
        if stocks:
            properties["Ticker"] = {"rich_text": [{"text": {"content": ", ".join(stocks)}}]}

        notion.pages.create(
            parent={"database_id": database_id},
            icon=None,
            properties=properties,
            children=blocks[:100]
        )


def upload_image_to_github(file_path, date_str, img_idx):
    """이미지를 GitHub repo에 업로드하고 raw URL 반환"""
    import base64
    import json
    import urllib.request
    import subprocess

    try:
        # VM git remote에서 PAT 추출
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
        )
        url = result.stdout.strip()
        pat = url.split(':')[2].split('@')[0] if '@github.com' in url else None
        if not pat:
            return None

        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode()

        ext = os.path.splitext(file_path)[1] or '.jpg'
        gh_path = f"research_images/{date_str.replace('-', '')}_img{img_idx}{ext}"

        body = json.dumps({
            "message": f"research image {date_str} #{img_idx}",
            "content": content
        }).encode('utf-8')

        req = urllib.request.Request(
            f"https://api.github.com/repos/sisyphe10/Antigravity_Market_Dashboard/contents/{gh_path}",
            data=body,
            headers={
                'Authorization': f'token {pat}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            },
            method='PUT'
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result['content']['download_url']
    except Exception as e:
        import logging
        logging.error(f"Image upload to GitHub failed: {e}")
        return None


def markdown_to_blocks(md_text, img_url_map=None):
    """마크다운 텍스트를 Notion 블록 리스트로 변환"""
    if img_url_map is None:
        img_url_map = {}
    blocks = []
    lines = md_text.split('\n')
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        i += 1
        if not stripped:
            continue

        # 메타데이터 라인 건너뛰기
        if stripped.startswith('토픽:') or stripped.startswith('토픽 :'):
            continue
        if stripped.startswith('종목:') or stripped.startswith('종목 :'):
            continue
        if stripped.startswith('이미지:') or stripped.startswith('이미지 :'):
            continue
        if stripped.startswith('엄중이미지:') or stripped.startswith('엄중이미지 :'):
            continue

        # [IMG:N] 이미지 삽입 마커
        img_match = re.match(r'^\[IMG:(\d+)\]$', stripped)
        if img_match:
            idx = int(img_match.group(1))
            if idx in img_url_map:
                blocks.append({
                    "object": "block", "type": "image",
                    "image": {"type": "external", "external": {"url": img_url_map[idx]}}
                })
            continue

        # 마크다운 테이블 감지 (| 로 시작하는 행)
        if stripped.startswith('|') and '|' in stripped[1:]:
            table_rows = [stripped]
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip()
                i += 1
                # 구분선 (|---|---| ) 건너뛰기
                if re.match(r'^\|[\s\-:]+\|', row):
                    continue
                table_rows.append(row)

            # Notion 테이블 블록 생성
            if len(table_rows) >= 1:
                parsed_rows = []
                for tr in table_rows:
                    cells = [c.strip() for c in tr.strip('|').split('|')]
                    parsed_rows.append(cells)

                col_count = max(len(r) for r in parsed_rows)
                table_children = []
                for ri, row_cells in enumerate(parsed_rows):
                    # 각 셀을 col_count에 맞춤
                    while len(row_cells) < col_count:
                        row_cells.append('')
                    table_children.append({
                        "object": "block",
                        "type": "table_row",
                        "table_row": {"cells": [[{"text": {"content": cell}}] for cell in row_cells[:col_count]]}
                    })

                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": col_count,
                        "has_column_header": True,
                        "children": table_children
                    }
                })
            continue

        # Heading 2
        if stripped.startswith('## '):
            h2_text = stripped[3:]
            if '[중요]' in h2_text:
                h2_text = h2_text.replace('[중요]', '').strip()
                blocks.append({
                    "object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": h2_text}, "annotations": {"color": "red"}}]}
                })
            else:
                blocks.append({
                    "object": "block", "type": "heading_2",
                    "heading_2": {"rich_text": [{"text": {"content": h2_text}}]}
                })
        # Heading 3
        elif stripped.startswith('### '):
            h3_text = stripped[4:]
            if '[중요]' in h3_text:
                h3_text = h3_text.replace('[중요]', '').strip()
                blocks.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": h3_text}, "annotations": {"color": "red"}}]}
                })
            else:
                blocks.append({
                    "object": "block", "type": "heading_3",
                    "heading_3": {"rich_text": [{"text": {"content": h3_text}}]}
                })
        # Bullet list
        elif stripped.startswith('- ') or stripped.startswith('* '):
            bullet_text = stripped[2:]
            if bullet_text.startswith('[!] '):
                bullet_text = bullet_text[4:]
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"text": {"content": bullet_text}, "annotations": {"color": "red"}}]}
                })
            else:
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": parse_rich_text(bullet_text)}
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
    """==하이라이트==, **볼드**, URL을 Notion rich_text로 변환"""
    rich = []
    # ==highlight== 와 **bold** 처리
    parts = re.split(r'(==.+?==|\*\*[^*]+\*\*)', text)
    for part in parts:
        if part.startswith('==') and part.endswith('=='):
            rich.append({
                "text": {"content": part[2:-2]},
                "annotations": {"color": "red"}
            })
        elif part.startswith('**') and part.endswith('**'):
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
