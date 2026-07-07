# Architecture Wiki Index

_Generated from `architecture/registry.json` · projects: antigravity · v1 — 113 components._

Updated: 2026-07-07

## By domain

### 국내 시장 (27)
- [Daily Disclosures DART+KIND (16:30)](gha-daily-disclosures.md) — GHA
- [Daily KOFIA Stats + NPS (17:30 평일)](gha-daily-kofia.md) — GHA
- [Daily KRX Index Valuation (18:30 평일)](gha-daily-krx-valuation.md) — GHA
- [DART 공시 (fetch_disclosures.py)](src-dart-disclosures.md) — Source
- [ETF 구성종목 수집 (collect_etf_daily.py)](src-etf-collect.md) — Source
- [ETF 구성종목 수집 타이머 (etf-collect 16:30)](timer-etf-collect.md) — Timer
- [ETF 수집 재시도 타이머 (etf-collect-retry 18:00)](timer-etf-collect-retry.md) — Timer
- [etf.html (ETF 구성종목)](page-etf.md) — Page
- [etf_data.db (ETF 구성종목 SQLite)](store-etf-db.md) — Store
- [KIND 거래소 공시 (fetch_kind_disclosures.py)](src-kind-disclosures.md) — Source
- [KOSIS 시계열 레지스트리 (fetch_kosis_series.py)](src-kosis-series.md) — Source
- [KPX 육지 SMP (fetch_smp_kpx.py)](src-smp-kpx.md) — Source
- [KRX 지수 밸류에이션 (fetch_krx_valuation.py)](src-krx-valuation.md) — Source
- [market_alert.html (투자유의종목)](page-market-alert.md) — Page
- [SEIBro TOP50 (fetch_seibro_data.py)](src-seibro.md) — Source
- [seibro.html (SEIBro)](page-seibro.md) — Page
- [stock_master.json (종목마스터)](store-stock-master.md) — Dataset
- [국민연금 적립금 (fetch_nps_fund.py)](src-nps-fund.md) — Source
- [금투협 예탁금/신용잔고 (fetch_kofia_stats.py)](src-kofia.md) — Source
- [액티브 ETF 변동 (active_etf_changes.py)](src-active-etf.md) — Source
- [액티브 ETF 변동 알림 타이머 (19:00)](timer-etf-active-alert.md) — Timer
- [외국인 보유비중 (fetch_krx_foreign.py)](src-krx-foreign.md) — Source
- [종목마스터 갱신 (update_stock_master.py)](src-stock-master.md) — Source
- [종목마스터 주간 갱신 타이머 (토 09:00)](timer-update-stock-master.md) — Timer
- [투자유의 생성기 (create_market_alert.py)](src-create-market-alert.md) — Source
- [투자자별 수급 (fetch_investor_trading.py)](src-investor-trading.md) — Source
- [한국 수출 매출 추정 대시보드](ext-export-dashboard.md) — External

### 해외 · 매크로 (21)
- [Daily ECOS BOK (17:40 평일)](gha-daily-ecos.md) — GHA
- [Daily FRED US Macro (07:50 화~토)](gha-daily-fred.md) — GHA
- [Daily Market Crawl (23:00)](gha-daily-crawl.md) — GHA
- [Daily Taiwan Monthly Revenue (23:20)](gha-daily-taiwan-revenue.md) — GHA
- [Daily Universe yfinance (18:30 + 07:00)](gha-daily-universe.md) — GHA
- [dataset.csv (시장 시계열 통합)](store-dataset-csv.md) — Dataset
- [ECOS 한국 매크로 33종 (fetch_ecos_data.py)](src-ecos.md) — Source
- [FRED 미국 매크로 36종 (fetch_fred_data.py)](src-fred.md) — Source
- [hotels.html (호텔 ADR, 동결)](page-hotels.md) — Page
- [market.html (마켓 대시보드)](page-market.md) — Page
- [taiwan.html (대만 월매출)](page-taiwan.md) — Page
- [taiwan_revenue.csv (대만 월매출)](store-taiwan-revenue-csv.md) — Dataset
- [universe.html (Universe)](page-universe.md) — Page
- [universe.json / universe_history.json](store-universe-json.md) — Dataset
- [universe_lab.html (Universe Lab)](page-universe-lab.md) — Page
- [대만 월매출 (fetch_taiwan_revenue.py)](src-taiwan-revenue.md) — Source
- [마스터 시장 크롤러 (market_crawler.py)](src-market-crawler.md) — Source
- [월별 수익률 11지수 (fetch_monthly_returns.py)](src-monthly-returns.md) — Source
- [유니버스 수집 (fetch_universe.py)](src-universe.md) — Source
- [일본 CAPEX 지표 (fetch_japan_capex.py)](src-japan-capex.md) — Source
- [호텔 ADR 타이머 (12:00, 은퇴)](timer-hotel-adr.md) — Timer

### 반도체 · 테크 (6)
- [KODEX 섹터 비중 (fetch_kodex_sectors.py)](src-kodex-sectors.md) — Source
- [KODEX 섹터 타이머 (23:30, +KOSIS/일본capex 편승)](timer-kodex-sectors.md) — Timer
- [SemiAnalysis 소스 (sources/semianalysis.py)](src-semianalysis.md) — Source
- [SiliconData 지수 3종 (fetch_silicondata_index.py)](src-silicondata.md) — Source
- [TrendForce 소스 (sources/trendforce.py)](src-trendforce.md) — Source
- [다나와 DRAM 최저가 (fetch_danawa_price.py)](src-danawa.md) — Source

### 포트폴리오 · WRAP (17)
- [contribution_data.json](store-contribution-data.md) — Dataset
- [Featured KIS 수집 타이머 (15:50, 신고가)](timer-featured-kis.md) — Timer
- [Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)](src-featured-kis.md) — Source
- [featured.html (Featured TOP)](page-featured.md) — Page
- [featured_data.json / newhigh_20d.json](store-featured-data.md) — Dataset
- [fee_revenue.json (수수료 매출)](store-fee-revenue.md) — Dataset
- [Finalize Pending Orders + AUM (16:00)](gha-finalize-orders.md) — GHA
- [orders/ (pending_orders · aum_pending)](store-orders-pending.md) — Store
- [portfolio_data.json](store-portfolio-data.md) — Dataset
- [Recalculate Wrap NAV (xlsx push 트리거)](gha-recalc-wrap-nav.md) — GHA
- [Sisyphe-Bot (펀드/일상 텔레그램 봇)](bot-sisyphe.md) — Bot
- [wrap.html (WRAP 대시보드)](page-wrap.md) — Page
- [Wrap_NAV.xlsx (랩 운용 원장)](store-wrap-nav-xlsx.md) — Store
- [기여도 데이터 (create_contribution_data.py)](src-create-contribution-data.md) — Source
- [기준가 엔진 (calculate_wrap_nav.py)](src-calculate-wrap-nav.md) — Source
- [수익률 계산 (calculate_returns.py)](src-calculate-returns.md) — Source
- [포트폴리오 표 생성 (create_portfolio_tables.py)](src-create-portfolio-tables.md) — Source

### 뉴스 · 리서치 (13)
- [Earnings Calendar Sync (07:00)](gha-earnings-calendar-sync.md) — GHA
- [earnings.db (실적봇 상태)](store-earnings-db.md) — Store
- [Generic Source Pipeline (execution/sources/)](src-generic-pipeline.md) — Source
- [Notion (실적·리서치 퍼블리시 대상)](ext-notion.md) — External
- [RA_Sisyphe_bot (리서치 알림 봇)](bot-ra-sisyphe.md) — Bot
- [Research Notes 봇](bot-research-notes.md) — Bot
- [research_notes.db + media/ (리서치봇)](store-research-notes-db.md) — Store
- [sources_state/ + kna_state.json](store-sources-state.md) — Store
- [실적 캘린더 sync (earnings_calendar_sync.py)](src-earnings-calendar-sync.md) — Source
- [실적봇 타이머 (earnings-bot)](timer-earnings-bot.md) — Timer
- [실적봇 파이프라인 (execution/earnings_bot/)](src-earnings-pipeline.md) — Source
- [원전 뉴스 KNA/KNEISS (sources/kna.py)](src-kna-kneiss.md) — Source
- [해외 기업 IR/뉴스룸 (sources/foreign_ir.py)](src-foreign-ir.md) — Source

### 개인 · 가족 (4)
- [SeonyuDuo repo (가족 영상 · 운동봇 연동)](ext-seonyuduo-repo.md) — External
- [Sisyphe 가계부/운동 대시보드 + 투자일지 시트](ext-sisyphe.md) — External
- [선유듀오 운동봇 (@SeonyuDuo_bot)](bot-seonyuduo-exercise.md) — Bot
- [투자일지 시장데이터 (fetch_journal_data.py)](src-journal-data.md) — Source

### 운영 · 인프라 (25)
- [architecture.html (아키텍처)](page-architecture.md) — Page
- [catch-up 러너 (부팅 시 놓친 잡 복구)](daemon-catchup.md) — Infra
- [Claude Code Action (@claude 이벤트)](gha-claude-code.md) — GHA
- [Daily Data Health Check (11:00)](gha-daily-health-check.md) — GHA
- [GHA 잡 흡수 layer (launchd Phase 2 초안)](launchd-gha-phase2.md) — Infra
- [GitHub (정본 repo · Pages · Actions)](infra-github.md) — Infra
- [Google Workspace (Sheets · Calendar · Drive)](ext-google-workspace.md) — External
- [heartbeats.json (Phase 2 워치독 인터페이스)](store-heartbeats.md) — Store
- [index.html (랜딩)](page-index.md) — Page
- [landing_highlights.json](store-landing-highlights.md) — Dataset
- [repo 동기화 (git-pull */5)](daemon-git-pull.md) — Watcher
- [UPS (무정전 전원, 맥미니 대비)](infra-ups.md) — Infra
- [Wrap_NAV 워처 (watch_wrap_nav.py)](watcher-wrap-nav.md) — Watcher
- [대시보드 생성기 (create_dashboard.py)](src-create-dashboard.md) — Source
- [랜딩 하이라이트 생성 (create_landing_highlights.py)](src-landing-highlights.md) — Source
- [랜딩 하이라이트 타이머 (18:45)](timer-landing-highlights.md) — Timer
- [비활성 워크플로 (weather · calendar · portfolio-report)](gha-disabled.md) — GHA
- [외부 데이터 API/소스 집합](ext-data-apis.md) — External
- [일일 셀프체크 다이제스트 (08:50, dead-man's switch)](daemon-daily-selfcheck.md) — Timer
- [작업용 노트북 (ASUS Vivobook, Windows)](infra-laptop.md) — Infra
- [차트 렌더러 (draw_charts + draw_wrap_charts)](src-draw-charts.md) — Source
- [컴퓨트 호스트 (Oracle VM → 맥미니)](infra-vm-macmini.md) — Infra
- [크래시 루프 워처 (*/5)](daemon-crash-watcher.md) — Watcher
- [텔레그램 (알림·상호작용 채널)](infra-telegram.md) — Infra
- [휴면 push-트리거 워크플로 (backfill · merge-ddr5)](gha-dormant-push.md) — GHA

## By type

### Bot (4)
- [RA_Sisyphe_bot (리서치 알림 봇)](bot-ra-sisyphe.md) — 상시 (내부 잡 05:10~21:00), active
- [Research Notes 봇](bot-research-notes.md) — 상시 (이벤트 드리븐), active
- [Sisyphe-Bot (펀드/일상 텔레그램 봇)](bot-sisyphe.md) — 상시 (내부 잡 05:00~23:00), active
- [선유듀오 운동봇 (@SeonyuDuo_bot)](bot-seonyuduo-exercise.md) — 상시 (06:00 다이제스트 등), active

### Timer (10)
- [ETF 구성종목 수집 타이머 (etf-collect 16:30)](timer-etf-collect.md) — 16:30 매일, active
- [ETF 수집 재시도 타이머 (etf-collect-retry 18:00)](timer-etf-collect-retry.md) — 18:00 매일, active
- [Featured KIS 수집 타이머 (15:50, 신고가)](timer-featured-kis.md) — 15:50 매일, active
- [KODEX 섹터 타이머 (23:30, +KOSIS/일본capex 편승)](timer-kodex-sectors.md) — 23:30 매일, active
- [랜딩 하이라이트 타이머 (18:45)](timer-landing-highlights.md) — 18:45 매일, active
- [실적봇 타이머 (earnings-bot)](timer-earnings-bot.md) — 08:00 매일, active
- [액티브 ETF 변동 알림 타이머 (19:00)](timer-etf-active-alert.md) — 19:00 매일, active
- [일일 셀프체크 다이제스트 (08:50, dead-man's switch)](daemon-daily-selfcheck.md) — 08:50 매일, planned
- [종목마스터 주간 갱신 타이머 (토 09:00)](timer-update-stock-master.md) — 토 09:00, active
- [호텔 ADR 타이머 (12:00, 은퇴)](timer-hotel-adr.md) — 12:00 매일 (disabled), retired

### GHA (15)
- [Claude Code Action (@claude 이벤트)](gha-claude-code.md) — 이벤트 (@claude PR/이슈), active
- [Daily Data Health Check (11:00)](gha-daily-health-check.md) — 11:00 매일, active
- [Daily Disclosures DART+KIND (16:30)](gha-daily-disclosures.md) — 16:30 매일, active
- [Daily ECOS BOK (17:40 평일)](gha-daily-ecos.md) — 17:40 평일, active
- [Daily FRED US Macro (07:50 화~토)](gha-daily-fred.md) — 07:50 화~토, active
- [Daily KOFIA Stats + NPS (17:30 평일)](gha-daily-kofia.md) — 17:30 평일, active
- [Daily KRX Index Valuation (18:30 평일)](gha-daily-krx-valuation.md) — 18:30 평일, active
- [Daily Market Crawl (23:00)](gha-daily-crawl.md) — 23:00 매일 (+ execution/** push 트리거), active
- [Daily Taiwan Monthly Revenue (23:20)](gha-daily-taiwan-revenue.md) — 23:20 매일, active
- [Daily Universe yfinance (18:30 + 07:00)](gha-daily-universe.md) — 18:30 / 07:00 매일, active
- [Earnings Calendar Sync (07:00)](gha-earnings-calendar-sync.md) — 07:00 매일, active
- [Finalize Pending Orders + AUM (16:00)](gha-finalize-orders.md) — 16:00 매일, active
- [Recalculate Wrap NAV (xlsx push 트리거)](gha-recalc-wrap-nav.md) — push 트리거 (Wrap_NAV.xlsx), active
- [비활성 워크플로 (weather · calendar · portfolio-report)](gha-disabled.md) — retired
- [휴면 push-트리거 워크플로 (backfill · merge-ddr5)](gha-dormant-push.md) — push 트리거 (사실상 휴면), frozen

### Page (12)
- [architecture.html (아키텍처)](page-architecture.md) — 수동 관리, active
- [etf.html (ETF 구성종목)](page-etf.md) — 생성=18:30 Featured 2차, active
- [featured.html (Featured TOP)](page-featured.md) — 생성=Featured 잡(16:20/18:30/08:30), active
- [hotels.html (호텔 ADR, 동결)](page-hotels.md) — frozen
- [index.html (랜딩)](page-index.md) — 생성=여러 잡, active
- [market.html (마켓 대시보드)](page-market.md) — 생성=여러 잡, active
- [market_alert.html (투자유의종목)](page-market-alert.md) — 생성=16:05 / 23:00 (sisyphe-bot), active
- [seibro.html (SEIBro)](page-seibro.md) — 생성=여러 잡, active
- [taiwan.html (대만 월매출)](page-taiwan.md) — 생성=23:20 (gha-daily-taiwan-revenue), active
- [universe.html (Universe)](page-universe.md) — 생성=여러 잡, active
- [universe_lab.html (Universe Lab)](page-universe-lab.md) — 생성=여러 잡, active
- [wrap.html (WRAP 대시보드)](page-wrap.md) — 생성=여러 잡, active

### Dataset (9)
- [contribution_data.json](store-contribution-data.md) — 23:00 재생성, active
- [dataset.csv (시장 시계열 통합)](store-dataset-csv.md) — 다수 잡 append, active
- [featured_data.json / newhigh_20d.json](store-featured-data.md) — Featured 잡 + 15:50, active
- [fee_revenue.json (수수료 매출)](store-fee-revenue.md) — 수동 입력, active
- [landing_highlights.json](store-landing-highlights.md) — 18:45 갱신, active
- [portfolio_data.json](store-portfolio-data.md) — 체인 재생성, active
- [stock_master.json (종목마스터)](store-stock-master.md) — 토 09:00 갱신, active
- [taiwan_revenue.csv (대만 월매출)](store-taiwan-revenue-csv.md) — 23:20 갱신, active
- [universe.json / universe_history.json](store-universe-json.md) — 18:30 / 07:00 갱신, active

### Store (7)
- [earnings.db (실적봇 상태)](store-earnings-db.md) — 08:00 갱신, active
- [etf_data.db (ETF 구성종목 SQLite)](store-etf-db.md) — 16:30 / 18:00 갱신, active
- [heartbeats.json (Phase 2 워치독 인터페이스)](store-heartbeats.md) — 각 GHA 잡 성공 시, planned
- [orders/ (pending_orders · aum_pending)](store-orders-pending.md) — 사용자 입력 + 16:00 finalize, active
- [research_notes.db + media/ (리서치봇)](store-research-notes-db.md) — 이벤트 시, active
- [sources_state/ + kna_state.json](store-sources-state.md) — 소스 폴링 시, active
- [Wrap_NAV.xlsx (랩 운용 원장)](store-wrap-nav-xlsx.md) — 사용자 편집 + finalize, active

### Infra (7)
- [catch-up 러너 (부팅 시 놓친 잡 복구)](daemon-catchup.md) — 부팅 시 1회, planned
- [GHA 잡 흡수 layer (launchd Phase 2 초안)](launchd-gha-phase2.md) — 이관 후 각 잡 스케줄, planned
- [GitHub (정본 repo · Pages · Actions)](infra-github.md) — 상시, active
- [UPS (무정전 전원, 맥미니 대비)](infra-ups.md) — planned
- [작업용 노트북 (ASUS Vivobook, Windows)](infra-laptop.md) — 상시, active
- [컴퓨트 호스트 (Oracle VM → 맥미니)](infra-vm-macmini.md) — 상시, active
- [텔레그램 (알림·상호작용 채널)](infra-telegram.md) — 상시, active

### External (6)
- [Google Workspace (Sheets · Calendar · Drive)](ext-google-workspace.md) — active
- [Notion (실적·리서치 퍼블리시 대상)](ext-notion.md) — active
- [SeonyuDuo repo (가족 영상 · 운동봇 연동)](ext-seonyuduo-repo.md) — active
- [Sisyphe 가계부/운동 대시보드 + 투자일지 시트](ext-sisyphe.md) — active
- [외부 데이터 API/소스 집합](ext-data-apis.md) — active
- [한국 수출 매출 추정 대시보드](ext-export-dashboard.md) — planned

### Source (40)
- [DART 공시 (fetch_disclosures.py)](src-dart-disclosures.md) — 16:30 (gha-daily-disclosures), active
- [ECOS 한국 매크로 33종 (fetch_ecos_data.py)](src-ecos.md) — 17:40 평일 (gha-daily-ecos), active
- [ETF 구성종목 수집 (collect_etf_daily.py)](src-etf-collect.md) — 16:30 / 18:00 (etf-collect 타이머), active
- [Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)](src-featured-kis.md) — 15:50 (featured-kis 타이머), active
- [FRED 미국 매크로 36종 (fetch_fred_data.py)](src-fred.md) — 07:50 화~토 (gha-daily-fred), active
- [Generic Source Pipeline (execution/sources/)](src-generic-pipeline.md) — 상시 (ra-sisyphe 등록), active
- [KIND 거래소 공시 (fetch_kind_disclosures.py)](src-kind-disclosures.md) — 16:30 (gha-daily-disclosures), active
- [KODEX 섹터 비중 (fetch_kodex_sectors.py)](src-kodex-sectors.md) — 23:30 (kodex 타이머), active
- [KOSIS 시계열 레지스트리 (fetch_kosis_series.py)](src-kosis-series.md) — 23:30 (kodex 타이머 편승), active
- [KPX 육지 SMP (fetch_smp_kpx.py)](src-smp-kpx.md) — 23:00 (crawler 내부), active
- [KRX 지수 밸류에이션 (fetch_krx_valuation.py)](src-krx-valuation.md) — 18:30 평일 (gha-daily-krx-valuation), active
- [SEIBro TOP50 (fetch_seibro_data.py)](src-seibro.md) — 23:00 (daily_crawl), active
- [SemiAnalysis 소스 (sources/semianalysis.py)](src-semianalysis.md) — 09:00 / 21:00 (ra-sisyphe), active
- [SiliconData 지수 3종 (fetch_silicondata_index.py)](src-silicondata.md) — 23:00 (crawler 내부), active
- [TrendForce 소스 (sources/trendforce.py)](src-trendforce.md) — 08:00 (ra-sisyphe), active
- [국민연금 적립금 (fetch_nps_fund.py)](src-nps-fund.md) — 17:30 평일 (gha-daily-kofia), active
- [금투협 예탁금/신용잔고 (fetch_kofia_stats.py)](src-kofia.md) — 17:30 평일 (gha-daily-kofia), active
- [기여도 데이터 (create_contribution_data.py)](src-create-contribution-data.md) — 23:00 (daily_crawl), active
- [기준가 엔진 (calculate_wrap_nav.py)](src-calculate-wrap-nav.md) — 체인 (finalize/recalc/crawl), active
- [다나와 DRAM 최저가 (fetch_danawa_price.py)](src-danawa.md) — 23:00 (daily_crawl), active
- [대만 월매출 (fetch_taiwan_revenue.py)](src-taiwan-revenue.md) — 23:20 (gha-daily-taiwan-revenue), active
- [대시보드 생성기 (create_dashboard.py)](src-create-dashboard.md) — 체인 말단 (여러 잡), active
- [랜딩 하이라이트 생성 (create_landing_highlights.py)](src-landing-highlights.md) — 18:45 (landing-highlights 타이머), active
- [마스터 시장 크롤러 (market_crawler.py)](src-market-crawler.md) — 23:00 (daily_crawl), active
- [수익률 계산 (calculate_returns.py)](src-calculate-returns.md) — 체인 (finalize/recalc/crawl), active
- [실적 캘린더 sync (earnings_calendar_sync.py)](src-earnings-calendar-sync.md) — 07:00 (GHA) + 15:00 (VM cron), active
- [실적봇 파이프라인 (execution/earnings_bot/)](src-earnings-pipeline.md) — 08:00 (earnings-bot 타이머), active
- [액티브 ETF 변동 (active_etf_changes.py)](src-active-etf.md) — 19:00 (etf-active-alert) / 18:30 (etf.html), active
- [외국인 보유비중 (fetch_krx_foreign.py)](src-krx-foreign.md) — 23:00 (daily_crawl), active
- [원전 뉴스 KNA/KNEISS (sources/kna.py)](src-kna-kneiss.md) — 18:00 (ra-sisyphe), active
- [월별 수익률 11지수 (fetch_monthly_returns.py)](src-monthly-returns.md) — 23:00 (daily_crawl), active
- [유니버스 수집 (fetch_universe.py)](src-universe.md) — 18:30 / 07:00 (gha-daily-universe), active
- [일본 CAPEX 지표 (fetch_japan_capex.py)](src-japan-capex.md) — 23:30 (kodex 타이머 편승), active
- [종목마스터 갱신 (update_stock_master.py)](src-stock-master.md) — 토 09:00 (update-stock-master 타이머), active
- [차트 렌더러 (draw_charts + draw_wrap_charts)](src-draw-charts.md) — 23:00 (daily_crawl), active
- [투자유의 생성기 (create_market_alert.py)](src-create-market-alert.md) — 16:05 / 23:00 (sisyphe-bot), active
- [투자일지 시장데이터 (fetch_journal_data.py)](src-journal-data.md) — 16:10 (sisyphe-bot), active
- [투자자별 수급 (fetch_investor_trading.py)](src-investor-trading.md) — 장 마감 후 (sisyphe-bot), active
- [포트폴리오 표 생성 (create_portfolio_tables.py)](src-create-portfolio-tables.md) — 체인 (finalize/recalc/crawl), active
- [해외 기업 IR/뉴스룸 (sources/foreign_ir.py)](src-foreign-ir.md) — 07:30 / 20:00 (ra-sisyphe), active

### Watcher (3)
- [repo 동기화 (git-pull */5)](daemon-git-pull.md) — */5분, active
- [Wrap_NAV 워처 (watch_wrap_nav.py)](watcher-wrap-nav.md) — 상시, active
- [크래시 루프 워처 (*/5)](daemon-crash-watcher.md) — */5분, planned

## By project

### antigravity (113)
- [architecture.html (아키텍처)](page-architecture.md) — Page
- [catch-up 러너 (부팅 시 놓친 잡 복구)](daemon-catchup.md) — Infra
- [Claude Code Action (@claude 이벤트)](gha-claude-code.md) — GHA
- [contribution_data.json](store-contribution-data.md) — Dataset
- [Daily Data Health Check (11:00)](gha-daily-health-check.md) — GHA
- [Daily Disclosures DART+KIND (16:30)](gha-daily-disclosures.md) — GHA
- [Daily ECOS BOK (17:40 평일)](gha-daily-ecos.md) — GHA
- [Daily FRED US Macro (07:50 화~토)](gha-daily-fred.md) — GHA
- [Daily KOFIA Stats + NPS (17:30 평일)](gha-daily-kofia.md) — GHA
- [Daily KRX Index Valuation (18:30 평일)](gha-daily-krx-valuation.md) — GHA
- [Daily Market Crawl (23:00)](gha-daily-crawl.md) — GHA
- [Daily Taiwan Monthly Revenue (23:20)](gha-daily-taiwan-revenue.md) — GHA
- [Daily Universe yfinance (18:30 + 07:00)](gha-daily-universe.md) — GHA
- [DART 공시 (fetch_disclosures.py)](src-dart-disclosures.md) — Source
- [dataset.csv (시장 시계열 통합)](store-dataset-csv.md) — Dataset
- [Earnings Calendar Sync (07:00)](gha-earnings-calendar-sync.md) — GHA
- [earnings.db (실적봇 상태)](store-earnings-db.md) — Store
- [ECOS 한국 매크로 33종 (fetch_ecos_data.py)](src-ecos.md) — Source
- [ETF 구성종목 수집 (collect_etf_daily.py)](src-etf-collect.md) — Source
- [ETF 구성종목 수집 타이머 (etf-collect 16:30)](timer-etf-collect.md) — Timer
- [ETF 수집 재시도 타이머 (etf-collect-retry 18:00)](timer-etf-collect-retry.md) — Timer
- [etf.html (ETF 구성종목)](page-etf.md) — Page
- [etf_data.db (ETF 구성종목 SQLite)](store-etf-db.md) — Store
- [Featured KIS 수집 타이머 (15:50, 신고가)](timer-featured-kis.md) — Timer
- [Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)](src-featured-kis.md) — Source
- [featured.html (Featured TOP)](page-featured.md) — Page
- [featured_data.json / newhigh_20d.json](store-featured-data.md) — Dataset
- [fee_revenue.json (수수료 매출)](store-fee-revenue.md) — Dataset
- [Finalize Pending Orders + AUM (16:00)](gha-finalize-orders.md) — GHA
- [FRED 미국 매크로 36종 (fetch_fred_data.py)](src-fred.md) — Source
- [Generic Source Pipeline (execution/sources/)](src-generic-pipeline.md) — Source
- [GHA 잡 흡수 layer (launchd Phase 2 초안)](launchd-gha-phase2.md) — Infra
- [GitHub (정본 repo · Pages · Actions)](infra-github.md) — Infra
- [Google Workspace (Sheets · Calendar · Drive)](ext-google-workspace.md) — External
- [heartbeats.json (Phase 2 워치독 인터페이스)](store-heartbeats.md) — Store
- [hotels.html (호텔 ADR, 동결)](page-hotels.md) — Page
- [index.html (랜딩)](page-index.md) — Page
- [KIND 거래소 공시 (fetch_kind_disclosures.py)](src-kind-disclosures.md) — Source
- [KODEX 섹터 비중 (fetch_kodex_sectors.py)](src-kodex-sectors.md) — Source
- [KODEX 섹터 타이머 (23:30, +KOSIS/일본capex 편승)](timer-kodex-sectors.md) — Timer
- [KOSIS 시계열 레지스트리 (fetch_kosis_series.py)](src-kosis-series.md) — Source
- [KPX 육지 SMP (fetch_smp_kpx.py)](src-smp-kpx.md) — Source
- [KRX 지수 밸류에이션 (fetch_krx_valuation.py)](src-krx-valuation.md) — Source
- [landing_highlights.json](store-landing-highlights.md) — Dataset
- [market.html (마켓 대시보드)](page-market.md) — Page
- [market_alert.html (투자유의종목)](page-market-alert.md) — Page
- [Notion (실적·리서치 퍼블리시 대상)](ext-notion.md) — External
- [orders/ (pending_orders · aum_pending)](store-orders-pending.md) — Store
- [portfolio_data.json](store-portfolio-data.md) — Dataset
- [RA_Sisyphe_bot (리서치 알림 봇)](bot-ra-sisyphe.md) — Bot
- [Recalculate Wrap NAV (xlsx push 트리거)](gha-recalc-wrap-nav.md) — GHA
- [repo 동기화 (git-pull */5)](daemon-git-pull.md) — Watcher
- [Research Notes 봇](bot-research-notes.md) — Bot
- [research_notes.db + media/ (리서치봇)](store-research-notes-db.md) — Store
- [SEIBro TOP50 (fetch_seibro_data.py)](src-seibro.md) — Source
- [seibro.html (SEIBro)](page-seibro.md) — Page
- [SemiAnalysis 소스 (sources/semianalysis.py)](src-semianalysis.md) — Source
- [SeonyuDuo repo (가족 영상 · 운동봇 연동)](ext-seonyuduo-repo.md) — External
- [SiliconData 지수 3종 (fetch_silicondata_index.py)](src-silicondata.md) — Source
- [Sisyphe 가계부/운동 대시보드 + 투자일지 시트](ext-sisyphe.md) — External
- [Sisyphe-Bot (펀드/일상 텔레그램 봇)](bot-sisyphe.md) — Bot
- [sources_state/ + kna_state.json](store-sources-state.md) — Store
- [stock_master.json (종목마스터)](store-stock-master.md) — Dataset
- [taiwan.html (대만 월매출)](page-taiwan.md) — Page
- [taiwan_revenue.csv (대만 월매출)](store-taiwan-revenue-csv.md) — Dataset
- [TrendForce 소스 (sources/trendforce.py)](src-trendforce.md) — Source
- [universe.html (Universe)](page-universe.md) — Page
- [universe.json / universe_history.json](store-universe-json.md) — Dataset
- [universe_lab.html (Universe Lab)](page-universe-lab.md) — Page
- [UPS (무정전 전원, 맥미니 대비)](infra-ups.md) — Infra
- [wrap.html (WRAP 대시보드)](page-wrap.md) — Page
- [Wrap_NAV 워처 (watch_wrap_nav.py)](watcher-wrap-nav.md) — Watcher
- [Wrap_NAV.xlsx (랩 운용 원장)](store-wrap-nav-xlsx.md) — Store
- [국민연금 적립금 (fetch_nps_fund.py)](src-nps-fund.md) — Source
- [금투협 예탁금/신용잔고 (fetch_kofia_stats.py)](src-kofia.md) — Source
- [기여도 데이터 (create_contribution_data.py)](src-create-contribution-data.md) — Source
- [기준가 엔진 (calculate_wrap_nav.py)](src-calculate-wrap-nav.md) — Source
- [다나와 DRAM 최저가 (fetch_danawa_price.py)](src-danawa.md) — Source
- [대만 월매출 (fetch_taiwan_revenue.py)](src-taiwan-revenue.md) — Source
- [대시보드 생성기 (create_dashboard.py)](src-create-dashboard.md) — Source
- [랜딩 하이라이트 생성 (create_landing_highlights.py)](src-landing-highlights.md) — Source
- [랜딩 하이라이트 타이머 (18:45)](timer-landing-highlights.md) — Timer
- [마스터 시장 크롤러 (market_crawler.py)](src-market-crawler.md) — Source
- [비활성 워크플로 (weather · calendar · portfolio-report)](gha-disabled.md) — GHA
- [선유듀오 운동봇 (@SeonyuDuo_bot)](bot-seonyuduo-exercise.md) — Bot
- [수익률 계산 (calculate_returns.py)](src-calculate-returns.md) — Source
- [실적 캘린더 sync (earnings_calendar_sync.py)](src-earnings-calendar-sync.md) — Source
- [실적봇 타이머 (earnings-bot)](timer-earnings-bot.md) — Timer
- [실적봇 파이프라인 (execution/earnings_bot/)](src-earnings-pipeline.md) — Source
- [액티브 ETF 변동 (active_etf_changes.py)](src-active-etf.md) — Source
- [액티브 ETF 변동 알림 타이머 (19:00)](timer-etf-active-alert.md) — Timer
- [외국인 보유비중 (fetch_krx_foreign.py)](src-krx-foreign.md) — Source
- [외부 데이터 API/소스 집합](ext-data-apis.md) — External
- [원전 뉴스 KNA/KNEISS (sources/kna.py)](src-kna-kneiss.md) — Source
- [월별 수익률 11지수 (fetch_monthly_returns.py)](src-monthly-returns.md) — Source
- [유니버스 수집 (fetch_universe.py)](src-universe.md) — Source
- [일본 CAPEX 지표 (fetch_japan_capex.py)](src-japan-capex.md) — Source
- [일일 셀프체크 다이제스트 (08:50, dead-man's switch)](daemon-daily-selfcheck.md) — Timer
- [작업용 노트북 (ASUS Vivobook, Windows)](infra-laptop.md) — Infra
- [종목마스터 갱신 (update_stock_master.py)](src-stock-master.md) — Source
- [종목마스터 주간 갱신 타이머 (토 09:00)](timer-update-stock-master.md) — Timer
- [차트 렌더러 (draw_charts + draw_wrap_charts)](src-draw-charts.md) — Source
- [컴퓨트 호스트 (Oracle VM → 맥미니)](infra-vm-macmini.md) — Infra
- [크래시 루프 워처 (*/5)](daemon-crash-watcher.md) — Watcher
- [텔레그램 (알림·상호작용 채널)](infra-telegram.md) — Infra
- [투자유의 생성기 (create_market_alert.py)](src-create-market-alert.md) — Source
- [투자일지 시장데이터 (fetch_journal_data.py)](src-journal-data.md) — Source
- [투자자별 수급 (fetch_investor_trading.py)](src-investor-trading.md) — Source
- [포트폴리오 표 생성 (create_portfolio_tables.py)](src-create-portfolio-tables.md) — Source
- [한국 수출 매출 추정 대시보드](ext-export-dashboard.md) — External
- [해외 기업 IR/뉴스룸 (sources/foreign_ir.py)](src-foreign-ir.md) — Source
- [호텔 ADR 타이머 (12:00, 은퇴)](timer-hotel-adr.md) — Timer
- [휴면 push-트리거 워크플로 (backfill · merge-ddr5)](gha-dormant-push.md) — GHA
