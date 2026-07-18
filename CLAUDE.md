# Antigravity Market Dashboard — 맥미니 프로덕션 트리 규칙

일반 작업 규칙은 `.claude/instructions.md`를 따른다. 아래는 **이 맥미니 워킹트리에서만 적용되는 필수 규칙**이다 (2026-07-11 VM→맥미니 이전 완료 후 확정).

## ★ 최우선: 수정 → 검증 → 즉시 commit+push 를 한 묶음으로

이 트리는 launchd 수집 잡들이 상시 사용하는 **프로덕션 워킹트리**다. 잡들의 `safe_commit_push.sh`가
`git reset --hard origin/main`으로 시작하므로, **push 안 된 커밋·변경은 다음 잡 실행(수 분 내)에 소멸**한다.
- 파일 수정 후 검증이 끝나면 그 자리에서 바로 commit+push. "나중에 몰아서 커밋" 금지.
- 실제 사고 사례: 2026-07-11 weather fix가 push 전에 reset --hard로 소실 → reflog로 복구.
- 장기 개발(며칠짜리)은 이 트리에서 하지 말고 별도 dev 클론에서.

## push 규칙

- `execution/**`를 push할 때 커밋 메시지에 **`[skip ci]` 필수** — 없으면 GHA Daily Market Crawl이 오발된다.
- `orders/pending_orders.json`은 팀원 주문 데이터 — 함부로 수정 금지, 보호 절차 없이는 push 금지.
- `Wrap_NAV.xlsx` 등 xlsx는 safe_commit_push의 xlsx-conflict 옵션 경유로만.

## 배포·시각 규칙

- **16:00~17:00 KST 배포 금지** (finalize-orders 16:00 등 민감 잡 시간대).
- 잡 스케줄 확인: `~/Antigravity_Market_Dashboard/logs/launchd/schedule.tsv` (타이머 8 + gha 10).
- launchd 잡 상태: `sudo launchctl list | grep com.antigravity`, 성공 stamp: `logs/launchd/stamps/*.last`.

## 웹서빙 (2026-07-11 구축)

- ts.net 대시보드는 `~/srv/dashboard/current`(게시 스냅숏)에서 서빙된다 — **스냅숏 디렉토리 직접 수정 금지**.
  게시는 잡 wrapper가 `scripts/publish_snapshot.sh`로 자동 수행(개인용 가공: WRAP 제거+Sisyphe 탭 주입 포함).
- Caddy 설정 = `launchd/web/Caddyfile` (수정 시 검증 `caddy validate` → push → `sudo launchctl kickstart -k system/com.antigravity.web`).

## 기타 함정

- `.env`에 JSON 블롭 값(예: GOOGLE_SERVICE_ACCOUNT_KEY)을 넣을 땐 **홑따옴표로 감싼 원문 JSON** —
  겉 쌍따옴표+이스케이프 형식은 wrapper 파서(겉따옴표 한 쌍만 제거)를 거치며 깨진다.
- push 시 `failed to store: -61/-25308` 키체인 경고는 무해했음(자격 저장만 실패, push는 성공). **2026-07-14 제거**: `~/.gitconfig`에서 `credential.helper`를 빈값으로 리셋 후 `store`만 지정 → 헤드리스 데몬에서 접근 불가한 osxkeychain 헬퍼를 체인에서 제외(자격증명은 `~/.git-credentials` 파일 사용). 재등장 시 `git config --global --get-all credential.helper`가 `(빈값)`+`store` 인지 확인.
- 시각 판단은 반드시 이 맥의 `date`(KST) 기준.

## 파일 배치 규칙
- 이 기기 전체의 파일시스템 계약(최상위 승인제·배치 규칙·tmp 정책) = `~/.claude/CLAUDE.md` — 새 파일을 만들기 전 반드시 확인.


## UI/스타일 작업 시 (영구 기조)

ts.net 전 페이지는 **터미널 블랙+앰버 디자인 시스템**을 따른다 — 새 탭/페이지 추가 시에도 동일.
팔레트·스펙·신규 페이지 적용 방법·함정 = 루트 `AOE_STYLE_GUIDE.md` 참조 (2026-07-18 확정, WRAP만 라이트 예외).
