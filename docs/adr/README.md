# 아키텍처 결정 기록 (ADR)

중요한 결정은 여기에 남긴다. 한 파일에 결정 하나를 적는다. 번호는 바꾸지 않는다.
결정이 바뀌면 새 ADR 을 쓰고, 이전 ADR 의 상태를 `대체됨(→ NNNN)` 으로 바꾼다.

형식: `NNNN-제목.md` — 상태 / 날짜 / 맥락 / 결정 / 결과

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-json-source-of-truth.md) | JSON 원천 데이터와 게임 파일 비수정 원칙 | 승인 |
| [0002](0002-no-unverified-data.md) | 미검증 데이터 금지와 출처 필수 | 승인 |
| [0003](0003-official-source-priority.md) | 공식 자료 불일치 시 KBL 값 우선 | 승인 |
| [0004](0004-positions.md) | KBL 포지션과 2K 포지션 분리 | 승인 |
| [0005](0005-roster-status.md) | 부상·대체 선수 표현 | 승인 |
| [0006](0006-public-repository.md) | 공개 저장소, noreply 이메일, 에셋 비공개 | 승인 |
| [0007](0007-kbl-stats-collection.md) | KBL 공식 사이트 API 로 기록 수집 | 승인 |
| [0008](0008-league-offsets.md) | 해외 리그 보정값 | 승인(잠정값) |
| [0009](0009-reed-rating-basis.md) | 데이본 리드 능력치 기준 기록 = B.League B1 | 승인 |
| [0010](0010-rating-model.md) | 능력치 산정 모델 | 승인 |
| [0011](0011-long-absence-players.md) | 장기 미출전 국내 선수 처리 | 승인 |
| [0012](0012-rating-scale-realistic.md) | 전체 능력치 수준 = 현실 반영 | 시험 중 |
| [0013](0013-editor-verification-procedure.md) | 로스터 에디터 검증 절차 | 승인 |
| [0014](0014-roster-editing-route.md) | 로스터 편집 경로 — 파일 기반 자체 도구 중단 | 승인 대기 |
