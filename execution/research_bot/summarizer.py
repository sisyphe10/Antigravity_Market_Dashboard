import os
import base64
import anthropic

def _encode_image(file_path):
    """이미지 파일을 base64로 인코딩"""
    try:
        with open(file_path, 'rb') as f:
            data = base64.standard_b64encode(f.read()).decode('utf-8')
        ext = os.path.splitext(file_path)[1].lower()
        media_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        return data, media_types.get(ext, 'image/jpeg')
    except:
        return None, None


def summarize_daily_notes(messages, date_str):
    """Claude API로 하루치 리서치 노트를 주제별로 정리/요약 (이미지 분석 포함)"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # 메시지들을 Claude API content 블록으로 조합
    content_blocks = []
    notes_parts = []

    for i, msg in enumerate(messages, 1):
        parts = [f"[{i}] ({msg['timestamp'][:16]})"]
        if msg.get('forward_source'):
            parts.append(f"[전달: {msg['forward_source']}]")
        if msg.get('text_content'):
            parts.append(msg['text_content'])
        if msg.get('url'):
            parts.append(f"링크: {msg['url']}")
        if msg.get('article_content'):
            parts.append(f"[기사 본문]\n{msg['article_content']}")
        notes_parts.append('\n'.join(parts))

        # 이미지가 있으면 Vision용 블록 추가
        if msg.get('media_path') and msg['message_type'] in ('photo', 'document'):
            img_data, media_type = _encode_image(msg['media_path'])
            if img_data:
                notes_parts.append(f"[이미지 {i} 첨부 - 아래 참조]")
                content_blocks.append({
                    "type": "text",
                    "text": f"\n--- 이미지 {i} (메시지 [{i}]의 첨부) ---"
                })
                content_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": img_data}
                })

    notes_text = '\n\n---\n\n'.join(notes_parts)

    # 프롬프트 텍스트
    prompt = f"""너는 월스트리트 IB의 최고 유능한 애널리스트 RA다. 꼼꼼하고 재능이 넘치며 열정과 야망이 넘친다. 다음은 {date_str}에 수집한 리서치 노트이다. 이 노트들을 주제별로 분류하고, 핵심 내용을 정리해라.

## 작성 규칙
1. 한글로 작성. 영문 내용은 자동 번역하여 한글로 정리
2. 관련된 노트들을 주제(토픽)별로 묶기
3. 각 토픽의 요약은 불릿 포인트 활용. 표가 적합한 경우 표로 정리
4. 각 토픽에서 언급된 종목명 + 관련될 수 있는 종목명을 불릿 포인트에 함께 정리 (예: "- 삼성전자: 반도체 수출 호조 전망")
5. 기본 톤은 간결하게. 단, 원본 노트에 '엄중'이라는 코멘트가 있는 항목은 상세하게 분석
6. 본문 불릿 포인트에는 URL을 넣지 말 것
7. 첨부된 이미지(스크린샷, 차트 등)의 내용도 분석하여 요약에 반영
8. 마크다운 볼드(**) 사용하지 말 것. 제목은 ## 또는 ### 헤딩만 사용
9. '엄중' 태그가 붙은 토픽의 제목 앞에 [엄중] 표시 추가
10. 요약 마지막에 "## 출처" 섹션을 만들고, 노트에 포함된 모든 링크를 아래 형식의 표로 정리:
| 제목 | URL |
| 기사/페이지 제목 | https://... |

## 출력 마지막에 반드시 아래 형식으로 메타데이터 작성 (이 형식 정확히 지킬 것)
토픽: 주요 토픽1, 토픽2 (쉼표 구분, 최대 3개)
종목: 삼성전자, SK하이닉스 (쉼표 구분, 없으면 "없음")

## 수집된 노트 ({len(messages)}건)
{notes_text}"""

    # content 블록 조합: 프롬프트 텍스트 먼저, 이미지 블록 뒤에
    all_content = [{"type": "text", "text": prompt}] + content_blocks

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": all_content}]
    )

    return response.content[0].text


def extract_topics(summary_text):
    """요약 텍스트에서 토픽 키워드 추출"""
    topics = []
    for line in summary_text.split('\n'):
        if line.strip().startswith('토픽:') or line.strip().startswith('토픽 :'):
            raw = line.split(':', 1)[1].strip()
            topics = [t.strip() for t in raw.split(',') if t.strip()]
            break
    return topics[:5]


def extract_stocks(summary_text):
    """요약 텍스트에서 종목명 추출"""
    stocks = []
    for line in summary_text.split('\n'):
        if line.strip().startswith('종목:') or line.strip().startswith('종목 :'):
            raw = line.split(':', 1)[1].strip()
            if raw != '없음':
                stocks = [s.strip() for s in raw.split(',') if s.strip()]
            break
    return stocks


def extract_critical_image_indices(summary_text):
    """요약 텍스트에서 '엄중' 이미지 번호 추출"""
    for line in summary_text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('엄중이미지:') or stripped.startswith('엄중이미지 :'):
            raw = stripped.split(':', 1)[1].strip()
            if raw == '없음':
                return []
            try:
                return [int(x.strip()) for x in raw.split(',') if x.strip().isdigit()]
            except:
                return []
    return []
