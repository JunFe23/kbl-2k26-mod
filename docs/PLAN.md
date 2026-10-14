# 개발 작업 계획

목표: NBA 2K26 PC(Steam) 오프라인 MyNBA 에서 **안양 정관장 vs 서울 SK** 경기가 정상 진행되는 것.
범위: 2026-27 KBL 시즌, 2개 팀 시범 구현 → 이후 10개 구단 확장.

## 원칙
- 결정사항은 [docs/adr/](adr/README.md) 에 ADR 로 남긴다.
- 원본 게임 파일을 직접 수정하지 않는다. 불가피하면 `kbl2k backup` → 적용 → 복구 리허설 순서를 지킨다.
- 검증되지 않은 선수 정보·파일 포맷을 만들어내지 않는다. 모르는 값은 `null`, 출처는 `data/sources.json`.
- 외부 도구는 [modding-tools.md](modding-tools.md) 체크리스트를 통과한 것만 쓴다.
- 모든 변경은 Git 커밋, `pytest` + `kbl2k validate` 통과 상태 유지.

## 단계

### 1단계 — 로스터 데이터 파이프라인 ✅ (이번 작업)
- [x] 프로젝트 구조, pyproject, Git
- [x] JSON Schema: player / team / sources / asset_mapping / rating_rules / attributes
- [x] `kbl2k validate` — 스키마 + 의미 검증(등번호·ID 중복, 출처 참조, 팀 소속)
- [x] 능력치 산정 모듈 (`ratings.py`) + 규칙 파일 + `calibrate`
- [x] 에셋 매핑 구조 + 진행 현황(`kbl2k mapping`)
- [x] 게임 파일 백업/복구(`kbl2k backup / verify-backup / restore`)
- [x] pytest 단위 테스트
- [x] 정관장·SK 로스터 1차 입력(공식 출처 기반, 미확인 값은 null)

### 2단계 — 데이터 보강
- [x] KBL 공식 기록 수집 도구(`kbl2k fetch`) — 2021-22~2025-26 선수별 이력, 2025-26 리그 전체
- [x] 외국인 신규 선수 2025-26 해외 기록 입력(리드·무니: B.League, 토마스: LBA·FIBA Europe Cup)
- [x] 해외 리그 보정값(`league_offsets`) 결정 — ADR-0008
- [ ] 미확인 필드(신장·체중·생년월일·포지션) 보완, 선수별 `verified` 전환
- [ ] 외국인/아시아쿼터 선수 2026-27 등록 확인
- [x] 10개 구단 기록으로 `kbl2k calibrate 2025-26 --write` (기록 지표 평균/표준편차)
- [x] 신장·체중 기준값 보정(리그 전체 신체 정보 수집)
- [x] 전체 수준 1차 결정: 현실 반영(워니≈75) — ADR-0012
- [ ] 게임 내 테스트 후 전체 수준 확정 → `provisional: false`
- [ ] 능력치 결과 검토(포지션별 분포, OVR 범위) 및 `ratings_override` 수동 보정

### 3단계 — 도구 검증 (게임 쓰기 직전 단계)
- [x] 설치 게임 확인(`kbl2k game info`): Steam 빌드 24237529, 기존 모드 없음
- [x] 2K26 에셋 파일명 규칙 확인(게임 manifest): 얼굴 `char/sig/png{ID}`, 로고 `logos/logo{ID}`, 코트 `levels/arena_{ID}_int_floor`, 확장팀 유니폼 존재
- [x] 기준 스냅샷(게임 폴더·세이브 폴더) + 변경 감시 도구(`kbl2k game snapshot/diff`)
- [ ] 검증 절차 승인(ADR-0013)
- [ ] 로스터 에디터 후보(2KVenueLab 등) 설치·체크리스트 검증
- [ ] 에디터의 import/export 포맷 실측 → 문서화 (추측 금지)
- [ ] 2K26 능력치 목록을 에디터 화면과 대조 → `attributes.schema.json` 확정
- [ ] 대체할 NBA 팀 슬롯 결정 → `team.nba_slot`

### 4단계 — 로스터 게임 반영 (첫 목표)
- [ ] 백업 → 에디터 어댑터(`kbl2k export <tool>`)로 두 팀 로스터·능력치 적용
- [ ] 오프라인 MyNBA: 두 팀 선택 → 경기 1회 완료 확인
- [ ] 복구 리허설

### 5단계 — 비주얼
- [ ] 팀 로고 → 유니폼(홈/원정) → 코트 → 선수 얼굴(사이버페이스/포트레이트)
- [ ] 각 에셋 `assets.json` 에 `game_id`/`file`/`tool` 기록, 게임 내 확인 후 `verified`

### 6단계 — 확장·배포
- [ ] 나머지 8개 구단
- [ ] 패치 대응 절차(게임 업데이트 후 매핑 재검증)
- [ ] 저작권·초상권 검토 후 배포 여부 결정
