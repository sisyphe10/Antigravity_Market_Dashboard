"""일일 AUM 입력 헬퍼.

입력 형식 (라인당 1건):
    YYYY-MM-DD/<증권사>/<유형>/<AUM>

  - 증권사: NH | DB | 삼성
  - 유형: 일반형 | 성과형
  - AUM: 원 단위 정수, 콤마 허용

상품명 매핑:
  NH 일반형 → 다이내믹밸류
  DB 일반형 → 개방형 랩
  삼성 일반형 → 트루밸류
  NH 성과형 → ACTIVE_TARGET_TRANSFORM['NH']
  DB 성과형 → ACTIVE_TARGET_TRANSFORM['DB']

목표전환형 출시/청산 시 ACTIVE_TARGET_TRANSFORM 갱신 필요
(target-transform.md SOP 매핑 목록에 함께 등록).

사용 예:
    python add_aum.py - <<'EOF'
    2026-05-19/NH/일반형/12,221,113,968
    2026-05-19/DB/일반형/13,452,045,967
    2026-05-19/삼성/일반형/53,981,536,215
    2026-05-19/NH/성과형/26,223,353,681
    2026-05-19/DB/성과형/7,501,605,632
    EOF
"""
from __future__ import annotations

import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

FILE_NAME = 'Wrap_NAV.xlsx'
SHEET = 'AUM'

FIXED_PRODUCTS = {
    ('NH', '일반형'): '다이내믹밸류',
    ('DB', '일반형'): '개방형 랩',
    ('삼성', '일반형'): '트루밸류',
}

ACTIVE_TARGET_TRANSFORM = {
    # NH 4호 / DB 5차 청산 (2026-06-19, 목표달성) — 신규 회차 출시 시 갱신
    # 'NH': '목표전환형 4호',
    # 'DB': '목표전환형 5차',
}


def resolve_product(brokerage: str, kind: str) -> str:
    if (brokerage, kind) in FIXED_PRODUCTS:
        return FIXED_PRODUCTS[(brokerage, kind)]
    if kind in ('성과형', '전환형'):
        if brokerage not in ACTIVE_TARGET_TRANSFORM:
            raise ValueError(f"{kind} 매핑 없음: {brokerage}")
        return ACTIVE_TARGET_TRANSFORM[brokerage]
    raise ValueError(f"미지의 입력: 증권사={brokerage}, 유형={kind}")


def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    parts = [p.strip() for p in line.split('/')]
    if len(parts) != 4:
        raise ValueError(f"형식 오류 (4필드 필요): {line!r}")
    date_str, brokerage, kind, aum_str = parts
    aum = int(aum_str.replace(',', '').replace(' ', ''))
    return {
        '날짜': pd.Timestamp(date_str),
        '증권사': brokerage,
        '상품명': resolve_product(brokerage, kind),
        'AUM': aum,
    }


def read_input() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        return sys.argv[1]
    return sys.stdin.read()


def main() -> None:
    text = read_input()
    new_rows = []
    for line in text.splitlines():
        row = parse_line(line)
        if row is not None:
            new_rows.append(row)

    if not new_rows:
        print("입력이 비어있습니다.")
        return

    df_new = pd.DataFrame(new_rows)
    df_existing = pd.read_excel(FILE_NAME, sheet_name=SHEET)
    df_existing['날짜'] = pd.to_datetime(df_existing['날짜'])

    keys = set(zip(df_new['날짜'], df_new['증권사'], df_new['상품명']))
    mask_dup = df_existing.apply(
        lambda r: (r['날짜'], r['증권사'], r['상품명']) in keys,
        axis=1,
    )
    if mask_dup.any():
        print(f"중복 {int(mask_dup.sum())}건 제거 (덮어쓰기).")

    df_final = pd.concat([df_existing[~mask_dup], df_new], ignore_index=True)
    df_final = df_final.sort_values(['날짜', '증권사', '상품명']).reset_index(drop=True)

    with pd.ExcelWriter(FILE_NAME, engine='openpyxl', mode='a', if_sheet_exists='replace') as w:
        df_final.to_excel(w, sheet_name=SHEET, index=False)

    print(f"\n[성공] AUM 시트에 {len(new_rows)}건 추가/갱신")
    print(df_new.to_string(index=False))


if __name__ == '__main__':
    main()
