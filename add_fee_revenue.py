"""매출(실제 발생 수수료, 자문사 몫) 입력 헬퍼.

fee_revenue.json 에 정산 금액 레코드를 추가/갱신한다.
(대시보드 수수료 탭 > 매출 서브탭에 분기별/증권사별/상품별로 집계됨)

입력 형식 (라인당 1건):
    <분기>/<증권사>/<카테고리>/<금액>[/<라벨>]

  - 분기: 2026-Q1 | 2026Q1 | "2026년 1분기" 모두 허용 (→ 2026-Q1 로 정규화)
  - 증권사: 삼성 | NH | DB | 한투
  - 카테고리: 개방형 | 목표전환형
  - 금액: 원 단위 정수, 콤마 허용 (자문사 몫 실제 정산액)
  - 라벨(선택): 목표전환형 회차명 등 (예: '목표전환형 2호'). 개방형은 보통 생략.

중복 판정 키: (분기, 증권사, 카테고리, 라벨) — 같으면 금액 덮어쓰기.

사용 예:
    python add_fee_revenue.py - <<'EOF'
    2026-Q1/삼성/개방형/42,768,106
    2026-Q1/NH/개방형/21,184,926
    2026-Q1/DB/개방형/33,149,819
    2026-Q2/DB/목표전환형/15,709,514/목표전환형 2호
    EOF

입력 후 대시보드 재생성 필요:
    PYTHONIOENCODING=utf-8 python execution/create_dashboard.py
"""
from __future__ import annotations

import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

FILE_NAME = 'fee_revenue.json'
BROKERS = {'삼성', 'NH', 'DB', '한투'}
CATEGORIES = {'개방형', '목표전환형'}


def normalize_quarter(s: str) -> str:
    s = s.strip()
    m = re.match(r'^(\d{4})\D*Q?\s*([1-4])\s*(?:분기)?$', s)
    if not m:
        raise ValueError(f"분기 형식 오류: {s!r} (예: 2026-Q1)")
    return f"{m.group(1)}-Q{m.group(2)}"


def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    parts = [p.strip() for p in line.split('/')]
    if len(parts) not in (4, 5):
        raise ValueError(f"형식 오류 (4~5필드 필요): {line!r}")
    quarter, broker, category, amount_str = parts[:4]
    label = parts[4].strip() if len(parts) == 5 and parts[4].strip() else None
    if broker not in BROKERS:
        raise ValueError(f"미지의 증권사: {broker!r} (허용: {', '.join(sorted(BROKERS))})")
    if category not in CATEGORIES:
        raise ValueError(f"미지의 카테고리: {category!r} (허용: {', '.join(sorted(CATEGORIES))})")
    amount = int(amount_str.replace(',', '').replace(' ', '').replace('원', ''))
    rec = {'quarter': normalize_quarter(quarter), 'broker': broker, 'category': category}
    if label:
        rec['label'] = label
    rec['amount'] = amount
    return rec


def rec_key(r: dict) -> tuple:
    return (r['quarter'], r['broker'], r['category'], r.get('label'))


def read_input() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        return sys.argv[1]
    return sys.stdin.read()


def main() -> None:
    new_rows = []
    for line in read_input().splitlines():
        row = parse_line(line)
        if row is not None:
            new_rows.append(row)

    if not new_rows:
        print("입력이 비어있습니다.")
        return

    try:
        with open(FILE_NAME, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {'updated': '', 'records': []}
    records = data.get('records', [])

    new_keys = {rec_key(r) for r in new_rows}
    dup = sum(1 for r in records if rec_key(r) in new_keys)
    if dup:
        print(f"중복 {dup}건 갱신 (덮어쓰기).")
    kept = [r for r in records if rec_key(r) not in new_keys]
    records = kept + new_rows

    # 정렬: 분기 → 증권사 → 카테고리 → 라벨
    broker_order = {'삼성': 0, 'NH': 1, 'DB': 2, '한투': 3}
    records.sort(key=lambda r: (r['quarter'], broker_order.get(r['broker'], 9),
                                r['category'], r.get('label') or ''))
    data['records'] = records

    with open(FILE_NAME, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

    total = sum(r['amount'] for r in records)
    print(f"\n[성공] {FILE_NAME} 에 {len(new_rows)}건 추가/갱신 (총 {len(records)}건, 누적 {total:,}원)")
    for r in new_rows:
        lbl = f" / {r['label']}" if r.get('label') else ''
        print(f"  {r['quarter']} / {r['broker']} / {r['category']}{lbl} : {r['amount']:,}원")
    print("\n다음 단계: PYTHONIOENCODING=utf-8 python execution/create_dashboard.py")


if __name__ == '__main__':
    main()
