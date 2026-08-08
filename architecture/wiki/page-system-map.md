---
id: "page-system-map"
name: "system_map.html (시스템 지도)"
domain: "ops-infra"
project: "antigravity"
type: "page"
runs_on: "vm_macmini"
schedule_kst: "생성=주간 지도 잡 훅 + 수동"
status: "active"
code:
  - "system_map.html"
  - "execution/create_system_map.py"
reads: []
writes: []
depends_on:
  - "src-nav-style"
  - "web-publish-snapshot"
alerts: ""
---

# system_map.html (시스템 지도)

**Domain:** 운영 · 인프라 · **Type:** Page · **Runs on:** vm_macmini · **Schedule (KST):** 생성=주간 지도 잡 훅 + 수동 · **Status:** active · **Project:** antigravity

메모리의 위치 라우터(`reference_system_map.md`)를 AoE 터미널 다크로 렌더한 웹뷰. 기기·경로·웹 위계·별칭 지도를 한 페이지로 보여준다. ts.net 개인 화면의 **Architecture 스트립**에 실린다(팀 공개 Pages에는 미게시).

- md 소스 = `~/.claude/projects/-Users-sisyphe/memory/reference_system_map.md`, 출력 = repo 루트 `system_map.html`([[web-publish-snapshot]] whitelist `/*.html` 경유로 게시, `scripts/compose_personal_view.py`가 개인 뷰 Architecture 그룹에 매핑).
- **범용 마크다운 렌더러**(heading/table/list/fence)라 주간 지도 편집이 이 빌더를 건드릴 필요가 없다. 테마 토큰 섹션은 [[src-nav-style]]의 `PALETTE`/`WRAP_PALETTE`(코드 단일 출처)에서 **라이브로** 렌더돼 팔레트 변경이 재빌드 시 자동 전파된다.
- 재생성 = `reference_system_map.md` 편집 후 `python execution/create_system_map.py`(주간 지도 잡 훅이 md 자동 갱신 후 호출, 수동 편집 시에도 재실행). 지도 자체가 최신화되는 주기는 주 1회(일 22:10 KST) 메모리 잡.
- **주간 보정 잡의 실패 알림(2026-08-08 배선)**: 지도를 갱신하는 일요일 22:10 잡(`weekly_map_update.sh`, 메모리 저장소 `scripts/` 소재 — repo 밖 **crontab** 잡)이 중단되면 [[infra-telegram]]의 `notify_sisyphe_failure.sh map-weekly`가 🗺️ 전용 문구로 알린다(로그 `~/tmp/map_update.log`). launchd 타이머가 아니라 `schedule.tsv` stamp 감시([[daemon-daily-selfcheck]]) 밖에 있어, **지도가 몇 주씩 조용히 낡는** 실패가 무음으로 지나가던 구멍을 메운 것. 이 잡도 구독 쿼터 headless claude를 쓰므로 인증이 만료되면 함께 멈춘다.
- [[page-architecture]]가 registry 코퍼스를 렌더하는 도식/타임라인이라면, 이 페이지는 **WHERE 전용** 위치 라우터로 상보적이다.

## Reads
- (none)

## Writes
- (none)

## Depends on
- [[src-nav-style]] — AoE 스타일 정본 (nav_style.py)
- [[web-publish-snapshot]] — 개인 스냅숏 게시 (publish_snapshot.sh)

## Code
- `system_map.html`
- `execution/create_system_map.py`
