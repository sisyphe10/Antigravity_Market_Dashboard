# Git Hooks

repo에 포함된 git hook 모음. 의존성 없이 동작 (bash + grep만).

## 활성화 (1회만)

```bash
git config core.hooksPath .githooks
```

이 명령은 사용자 워크스테이션마다 별도로 실행해야 합니다 (`git config`는 git이 추적 안 함). VM은 자동 배포되는 코드라 commit 안 하므로 활성화 불필요.

## 포함된 hook

### `pre-commit` — 시크릿 패턴 차단

staged diff에서 다음 패턴이 발견되면 commit을 차단:

- `ghp_*`, `github_pat_*` (GitHub PAT)
- `ntn_*` (Notion integration)
- `sk-ant-*` (Anthropic API key)
- `\d{8,}:[A-Za-z0-9_-]{30,}` (Telegram bot token)
- `AKIA[A-Z0-9]{16}` (AWS Access Key)

오탐 시 우회: `git commit --no-verify` (사용 자제)

발견 사례 시 작업 흐름:
1. 시크릿이면 `.env`로 분리하고 `.gitignore` 확인
2. `.env` 자체 commit 시도면 즉시 unstage: `git restore --staged .env`
