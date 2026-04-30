"""orders/pending_orders.json → Wrap_NAV.xlsx NEW 시트 반영

매일 16:00 KST (07:00 UTC) GHA workflow에서 호출:
1. orders/pending_orders.json 로드
2. 오늘 날짜의 카드별 entry → Wrap_NAV.xlsx NEW 시트에 행 추가
   - 각 카드의 newSheetTargets (broker, product) × stocks 곱 만큼 행 생성
   - 같은 (날짜, broker, product) 기존 행은 먼저 제거 (덮어쓰기)
3. pending_orders.json에서 해당 날짜 entry 삭제 (확정 처리)

Wrap_NAV.xlsx, orders/pending_orders.json 둘 다 commit 됨.
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
import openpyxl

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRAP_NAV = os.path.join(ROOT, 'Wrap_NAV.xlsx')
PENDING = os.path.join(ROOT, 'orders', 'pending_orders.json')

KST = timezone(timedelta(hours=9))


def main():
    if not os.path.exists(PENDING):
        print(f'⚪ pending_orders.json 없음 — 처리할 ORDER 없음')
        return 0
    with open(PENDING, encoding='utf-8') as f:
        pending = json.load(f)
    if not isinstance(pending, dict) or not pending:
        print(f'⚪ pending_orders.json 비어있음')
        return 0

    today_kst = datetime.now(tz=KST).strftime('%Y-%m-%d')
    today_entry = pending.get(today_kst)
    if not today_entry:
        print(f'⚪ {today_kst} 자 pending entry 없음 (기존 keys: {list(pending.keys())})')
        return 0

    print(f'=== {today_kst} ORDER 확정 처리 ===')
    print(f'카드 수: {len(today_entry)}')

    if not os.path.exists(WRAP_NAV):
        print(f'❌ Wrap_NAV.xlsx 없음')
        return 1

    wb = openpyxl.load_workbook(WRAP_NAV)
    if 'NEW' not in wb.sheetnames:
        print(f'❌ NEW 시트 없음')
        return 1
    ws = wb['NEW']

    today_dt = datetime.strptime(today_kst, '%Y-%m-%d')

    rows_added_total = 0
    for card_name, card_entry in today_entry.items():
        targets = card_entry.get('targets', [])
        stocks = card_entry.get('stocks', [])
        if not targets or not stocks:
            print(f'  ⚠️ {card_name}: targets/stocks 비어있음, skip')
            continue

        # 같은 (오늘, broker, product) 기존 행 제거
        rows_to_delete = []
        for r in range(2, ws.max_row + 1):
            date_v = ws.cell(row=r, column=1).value
            broker_v = ws.cell(row=r, column=2).value
            product_v = ws.cell(row=r, column=3).value
            if not broker_v or not product_v:
                continue
            if isinstance(date_v, datetime):
                date_str = date_v.strftime('%Y-%m-%d')
            else:
                date_str = str(date_v)[:10]
            if date_str != today_kst:
                continue
            for t in targets:
                if broker_v == t['broker'] and product_v == t['product']:
                    rows_to_delete.append(r)
                    break
        for r in sorted(rows_to_delete, reverse=True):
            ws.delete_rows(r)
        if rows_to_delete:
            print(f'  {card_name}: 기존 {len(rows_to_delete)}행 제거 (덮어쓰기)')

        # 새 행 추가
        added = 0
        for t in targets:
            for s in stocks:
                ws.append([today_dt, t['broker'], t['product'], s.get('sector', ''),
                           str(s.get('code', '')), s.get('name', ''), s.get('weight', 0)])
                added += 1
        rows_added_total += added
        print(f'  ✓ {card_name}: {len(stocks)}종목 × {len(targets)}상품 = {added}행 추가')

    wb.save(WRAP_NAV)
    print(f'✅ Wrap_NAV.xlsx 저장 ({rows_added_total}행 추가)')

    # pending에서 오늘 entry 제거
    del pending[today_kst]
    with open(PENDING, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    print(f'✅ pending_orders.json 에서 {today_kst} 제거')
    return 0


if __name__ == '__main__':
    sys.exit(main())
