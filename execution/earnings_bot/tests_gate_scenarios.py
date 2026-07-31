"""게이트 기능 검증 — 실제 사고 시나리오 재현."""
import sys

sys.path.insert(0, "execution/earnings_bot")
import transcript_gate as G

FAIL = 0


def expect(name, result, want_ok):
    global FAIL
    ok = result.ok == want_ok
    if not ok:
        FAIL += 1
    print("  [%s] %-46s ok=%-5s %s"
          % ("PASS" if ok else "★FAIL", name, result.ok,
             (" | ".join(result.reasons))[:80]))


# ── 시나리오 1: IBM 날조 (가이던스 기사 + 만들어낸 CEO 발언) ──────────
ibm_article = (
    "International Business Machines (NYSE:IBM) Updates Q2 2026 Earnings Guidance "
    "Written by MarketBeat July 14, 2026. Key Points: IBM lowered its Q2 2026 outlook, "
    "guiding for EPS of $2.93 and revenue of $17.2 billion. Analysts praised CEO "
    "Arvind Krishna's execution. Read Arvind Krishna's Letter to IBM Investors. "
    "Morgan Stanley upgraded IBM from equal weight to overweight. " * 40)
ibm_fabricated = ("## 경영진 발표\n\n**Arvind Krishna - 최고경영자**\n\n"
                  "IBM은 2026년 2분기 실적 가이던스를 하향 조정했습니다. 2분기 EPS를 $2.93, "
                  "매출을 $17.2 billion으로 제시했으며...")
print("시나리오 1 — IBM 가이던스 기사 + 날조 번역")
expect("수집 게이트(URL 기사 + 짧은 원문)",
       G.check_collect("https://www.marketbeat.com/instant-alerts/ibm-updates-q2-2026-earnings-guidance-2026-07-14/",
                       ibm_article, "", "2026-07-22"), False)
expect("화자 귀속 역대조(이름은 원문에 있으나 3인칭 서술)",
       G.check_speaker_attribution(ibm_article, ibm_fabricated), False)

# ── 시나리오 2: 작년 같은 분기 전문 (MSFT) ──────────────────────────
msft_body = ("Image source: The Motley Fool. Date Wednesday, July 30, 2025, at 9:30 p.m. ET. "
             "Call participants: Satya Nadella. Operator: Welcome to the call. "
             "Satya Nadella: Thank you for joining us today. " * 500)
print("\n시나리오 2 — 작년(2025) 콜이 2026 공시에 붙음")
expect("URL 연도 stale",
       G.check_source("https://www.fool.com/earnings/call-transcripts/2025/08/05/microsoft-msft-q4-2025-earnings-call-transcript/",
                      "2026-07-29"), False)
expect("본문 vintage(12개월 차)",
       G.check_body(msft_body, "", "2026-07-29"), False)

# ── 시나리오 3: 보도자료 (SYK) ──────────────────────────────────────
pr_body = ("Press release. Date: April 30, 2026. Stryker reports first quarter 2026 "
           "operating results. Portage, Michigan - Stryker (NYSE:SYK) reported operating "
           "results for the first quarter. Net sales increased 11.9%. " * 200)
print("\n시나리오 3 — 실적 보도자료가 전문으로 수집됨")
expect("발화 구조 없음",
       G.check_body(pr_body, "", "2026-04-30"), False)

# ── 시나리오 4: 직전 분기 콜 (AAPL) ────────────────────────────────
print("\n시나리오 4 — 직전 분기(1월) 콜이 4월 공시에 붙음")
expect("URL 날짜 3개월 차",
       G.check_source("https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                      "2026-04-30"), False)

# ── 시나리오 5: sentinel ────────────────────────────────────────────
print("\n시나리오 5 — 모델이 sentinel 로 거부")
expect("NOT_A_TRANSCRIPT 검출",
       G.check_translation("x" * 30000, "NOT_A_TRANSCRIPT"), False)

# ── 시나리오 6: 정상 전문은 통과해야 한다 ──────────────────────────
good_body = ("Operator: Good afternoon and welcome to the Apple Q3 fiscal year 2026 earnings "
             "conference call. Tim Cook: Thank you for joining us today. Revenue was $109.4 "
             "billion. Kevan Parekh: Our gross margin was 50.1%. "
             "Operator: Our first question comes from Amit Daryanani. " * 400)
# 실측 번역 비율: 정상 0.49~0.55 (META 0.52 / AAPL 0.55 / GEV 0.49),
#                 오염 0.03~0.08 (IBM 0.08 / TEL 0.03) → 임계 0.25
good_kr = ("## 경영진 발표\n\n**Tim Cook - 최고경영자**\n\n오늘 함께해 주셔서 감사합니다. "
           "매출은 1,094억 달러로 전년 대비 16% 증가했습니다.\n\n"
           "**Kevan Parekh - 최고재무책임자**\n\n매출총이익률은 50.1%였습니다. "
           "영업비용은 191억 달러입니다.\n\n" * 260)
print("\n시나리오 6 — 정상 전문(오탐 확인)")
expect("수집 게이트 통과",
       G.check_collect("https://www.fool.com/earnings/call-transcripts/2026/07/30/apple-aapl-q3-2026/",
                       good_body, "", "2026-07-30"), True)
expect("번역 출력 게이트 통과",
       G.check_translation(good_body, good_kr), True)

print("\n결과: %s" % ("전부 통과" if FAIL == 0 else f"★{FAIL}건 실패"))
sys.exit(1 if FAIL else 0)
