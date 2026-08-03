# (은퇴) VM 배포 규칙 — Oracle VM retired 2026-08-03

Oracle VM(144.24.70.224)은 2026-08-03 은퇴했다(인스턴스 Stop, 1개월 관찰 후 Terminate 예정).
텔레그램 봇 4종·타이머 전부 **맥미니 launchd** 상주 — 재시작은
`sudo launchctl kickstart -k system/com.antigravity.<이름>` (16:00~17:00 KST 재시작 회피 유지).

- VM 전용 파일(systemd 유닛·deploy.sh) = `scripts/vm_legacy/` (비실행 보관)
- 상태 데이터 백업 = `vm_state_260803.tar.gz` (SHA-256 manifest·복원 테스트 완료) —
  맥미니 `~/backups/vm_retirement/` + 노트북 `D:\backups\vm_retirement_260803\`
- 은퇴 직전 repo 태그 = `pre-vm-retirement-20260803`
- 재구축 runbook·인스턴스 OCID = 메모리 `project_vm_retirement.md`
