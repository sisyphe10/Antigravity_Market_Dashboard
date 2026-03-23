import os
import anthropic

def summarize_daily_notes(messages, date_str):
    """Claude API로 하루치 리서치 노트를 주제별로 정리/요약"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # 메시지들을 텍스트로 조합
    notes = []
    for i, msg in enumerate(messages, 1):
        parts = [f"[{i}] ({msg['timestamp'][:16]})"]
        if msg.get('forward_source'):
            parts.append(f"[전달: {msg['forward_source']}]")
        if msg.get('text_content'):
            parts.append(msg['text_content'])
        if msg.get('url'):
            parts.append(f"링크: {msg['url']}")
        if msg.get('media_path'):
            parts.append(f"[첨부파일: {os.path.basename(msg['media_path'])}]")
        notes.append('\n'.join(parts))

    notes_text = '\n\n---\n\n'.join(notes)

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""너는 월스트리트 IB의 최고 유능한 애널리스트 RA다. 꼼꼼하고 재능이 넘치며 열정과 야망이 넘친다. 다음은 {date_str}에 수집한 리서치 노트이다. 이 노트들을 주제별로 분류하고, 핵심 내용을 정리해라.

## 작성 규칙
1. **한글로 작성**. 영문 내용은 자동 번역하여 한글로 정리
2. 관련된 노트들을 주제(토픽)별로 묶기
3. 각 토픽의 요약은 **불릿 포인트** 활용. 표가 적합한 경우 표로 정리
4. 각 토픽에서 **언급된 종목명 + 관련될 수 있는 종목명**을 불릿 포인트에 함께 정리 (예: "- 삼성전자: 반도체 수출 호조 전망")
5. 기본 톤은 **간결하게**. 단, 원본 노트에 '엄중'이라는 코멘트가 있는 항목은 **상세하게** 분석
6. 중요한 링크/출처가 있으면 포함
7. 후속 조치(action items)가 있으면 별도 섹션으로 정리

## 출력 마지막에 반드시 아래 형식으로 메타데이터 작성 (이 형식 정확히 지킬 것)
토픽: 주요 토픽1, 토픽2 (쉼표 구분, 최대 3개)
종목: 삼성전자, SK하이닉스 (쉼표 구분, 없으면 "없음")

## 수집된 노트 ({len(messages)}건)
{notes_text}"""
        }]
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
