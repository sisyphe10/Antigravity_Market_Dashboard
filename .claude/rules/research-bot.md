---
patterns:
  - "execution/research_bot/*"
---

# 리서치 봇 규칙

## 요약 프롬프트 (summarizer.py)
- 모든 토픽 상세 요약 (불릿 8~12개 이상)
- 이미 불릿/단답식이면 원문 그대로 유지
- 모든 이미지 첨부 ([IMG:번호])
- 이미지 헤더 → 캡션, 텍스트 많은 이미지 → OCR 후 옮겨 적기
- 엄중/ㅇㅈ/중요/ㅈㅇ 표시 → {RED} 태그로 빨간색 처리
- AI가 중요하다고 판단한 불릿도 {RED} 태그

## Notion 퍼블리셔 (notion_publisher.py)
- {RED} 태그 → Notion 빨간색 텍스트 (제목/불릿 모두)
- 메타데이터: 토픽, 종목, 이미지 (엄중이미지 아님)
- 이미지는 GitHub에 업로드 후 URL로 삽입
