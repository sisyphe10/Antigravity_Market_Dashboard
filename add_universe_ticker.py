"""Universe 종목 추가 헬퍼.

입력 형식 (라인당 1건):
    <티커>/<기업명>/<섹터>

  - 티커: PREFIX:CODE (예: KRX:005930, NASDAQ:NVDA, TYO:7203)
  - PREFIX 매핑: KRX/KOSDAQ/NASDAQ/NYSE/NYSEAMERICAN/TPE/TYO/TSE/HKG/AMS/ETR/EPA
  - 기업명: 한글/영문 자유
  - 섹터: 한글 (예: 반도체, 자본재, 증권)

통화는 prefix에서 자동 결정 (KRX→KRW, NASDAQ→USD 등). 사용자 입력 불필요.

사용 예 (add_aum.py와 동일 패턴):
    python add_universe_ticker.py - <<'EOF'
    KRX:005930/삼성전자/반도체
    NASDAQ:NVDA/NVIDIA/반도체
    TYO:7203/Toyota Motor/자동차
    EOF

또는 단일 인자:
    python add_universe_ticker.py "KRX:005930/삼성전자/반도체"

처리 결과:
- universe_tickers.csv에 신규 행 append (# 자동 증가)
- 중복 티커는 skip (기존 정보 유지)
- 결과 출력 후 git commit + push까지 자동
- (옵션) GHA workflow_dispatch 즉시 트리거로 universe.json 빠르게 갱신
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
TICKERS_FILE = ROOT / 'universe_tickers.csv'

# fetch_universe.py와 동일한 매핑
VALID_PREFIXES = {
    'KRX', 'KOSDAQ', 'NASDAQ', 'NYSE', 'NYSEAMERICAN',
    'TPE', 'TYO', 'TSE', 'HKG', 'AMS', 'ETR', 'EPA',
}
PREFIX_CURRENCY = {
    'KRX': 'KRW', 'KOSDAQ': 'KRW',
    'NASDAQ': 'USD', 'NYSE': 'USD', 'NYSEAMERICAN': 'USD',
    'TPE': 'TWD', 'TYO': 'JPY', 'TSE': 'CAD',
    'HKG': 'HKD', 'AMS': 'EUR', 'ETR': 'EUR', 'EPA': 'EUR',
}


def parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    parts = [p.strip() for p in line.split('/')]
    if len(parts) != 3:
        raise ValueError(f"형식 오류 (3필드 필요 — 티커/기업명/섹터): {line!r}")
    ticker, name, sector = parts
    if ':' not in ticker:
        raise ValueError(f"티커에 PREFIX 누락 (예: KRX:005930): {ticker!r}")
    prefix = ticker.split(':', 1)[0]
    if prefix not in VALID_PREFIXES:
        raise ValueError(f"미지의 PREFIX: {prefix} (지원: {sorted(VALID_PREFIXES)})")
    return {
        'currency': PREFIX_CURRENCY[prefix],
        'sector': sector,
        'ticker': ticker,
        'name': name,
    }


def read_input() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        return sys.argv[1]
    return sys.stdin.read()


def main() -> None:
    allow_new_sector = '--new-sector' in sys.argv
    if allow_new_sector:
        sys.argv.remove('--new-sector')
    text = read_input()
    new_rows: list[dict] = []
    for line in text.splitlines():
        row = parse_line(line)
        if row is not None:
            new_rows.append(row)

    if not new_rows:
        print("입력이 비어있습니다.")
        return

    # 섹터 라벨 검증 — fetch_universe.ALLOWED_SECTORS 기준 (오타·라벨 난립 방지)
    if not allow_new_sector:
        try:
            sys.path.insert(0, str(ROOT / 'execution'))
            from fetch_universe import ALLOWED_SECTORS
        except Exception:
            ALLOWED_SECTORS = None
        if ALLOWED_SECTORS:
            unknown = sorted({r['sector'] for r in new_rows} - ALLOWED_SECTORS)
            if unknown:
                print(f"[중단] 미등록 섹터 라벨: {unknown}")
                print("  오타면 기존 라벨로 수정 (목록: execution/fetch_universe.py ALLOWED_SECTORS)")
                print("  새 라벨을 의도했다면 --new-sector로 재실행 후 ALLOWED_SECTORS에도 추가")
                sys.exit(1)

    # 기존 CSV 읽기
    existing_tickers: set[str] = set()
    existing_rows: list[list[str]] = []
    with open(TICKERS_FILE, encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for r in reader:
            existing_rows.append(r)
            if len(r) >= 4:
                existing_tickers.add(r[3].strip())

    # 중복 제거 + 신규 행 만들기
    appended: list[dict] = []
    skipped: list[str] = []
    next_idx = len(existing_rows) + 1
    for row in new_rows:
        if row['ticker'] in existing_tickers:
            skipped.append(row['ticker'])
            continue
        existing_rows.append([
            str(next_idx),
            row['currency'],
            row['sector'],
            row['ticker'],
            row['name'],
        ])
        existing_tickers.add(row['ticker'])
        appended.append(row)
        next_idx += 1

    # CSV 다시 쓰기
    with open(TICKERS_FILE, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(existing_rows)

    print(f"\n[추가] {len(appended)}건")
    for row in appended:
        print(f"  {row['ticker']:25s} {row['name']:20s} {row['sector']:15s} ({row['currency']})")
    if skipped:
        print(f"\n[중복 skip] {len(skipped)}건: {', '.join(skipped)}")

    if not appended:
        print("\n변경 없음 (모두 중복). 종료.")
        return

    # git commit + push
    print("\n[git] commit + push 진행...")
    try:
        subprocess.run(['git', 'add', str(TICKERS_FILE)], check=True, cwd=ROOT)
        msg_lines = [
            f"Universe 종목 추가: {len(appended)}건",
            '',
        ] + [f"- {r['ticker']} {r['name']} ({r['sector']})" for r in appended]
        msg = '\n'.join(msg_lines)
        subprocess.run(['git', 'commit', '-m', msg], check=True, cwd=ROOT)
        subprocess.run(['git', 'push', 'origin', 'main'], check=True, cwd=ROOT)
        print("[성공] push 완료. 다음 GHA cron이 universe.json에 반영합니다.")
        print("       즉시 갱신 원하시면: gh workflow run daily_universe.yml")
    except subprocess.CalledProcessError as e:
        print(f"[Warning] git 작업 실패: {e}")
        print("         수동으로 push 해주세요.")


if __name__ == '__main__':
    main()
