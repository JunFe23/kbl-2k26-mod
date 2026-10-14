# KBL 2K26 Mod

NBA 2K26 PC(Steam) 용 KBL 통합 모드. 2026-27 시즌 기준 **안양 정관장 레드부스터스**와 **서울 SK 나이츠** 2개 팀을 먼저 구현한다.
첫 목표는 오프라인 MyNBA 에서 두 팀으로 정상적으로 경기하는 것이다.

현재 단계는 **로스터 데이터 파이프라인**이다. 이 단계는 게임 파일을 전혀 건드리지 않는다.
전체 로드맵은 [docs/PLAN.md](docs/PLAN.md), 외부 도구 조사 결과는 [docs/modding-tools.md](docs/modding-tools.md) 에 있다.

> ⚠️ 모드 작업과 테스트는 **오프라인에서만** 한다. PC 판은 Easy Anti-Cheat 를 쓰므로 온라인 모드와 섞지 않는다.

## 설치
Python 3.12 이상이 필요하다.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 사용법
```powershell
kbl2k validate -w                 # 스키마 + 의미 검증 (오류 시 exit 1, -w 는 경고도 출력)
kbl2k ratings anyang-kgc          # 팀 능력치 산정 표
kbl2k ratings seoul-sk --json     # 22개 능력치 전체를 JSON 으로 출력
kbl2k calibrate 2025-26           # 데이터로 평균/표준편차 재계산 (--write 로 저장)
kbl2k mapping -v                  # 얼굴/유니폼/코트/로고 매핑 진행 현황

# 게임 파일 백업/복구 — 게임 폴더는 읽기만 하고, 백업은 게임 폴더 밖에 저장
kbl2k backup --game-dir "D:\SteamLibrary\steamapps\common\NBA 2K26" --label pre-roster <상대경로...>
kbl2k verify-backup game_backup\<타임스탬프>
kbl2k restore game_backup\<타임스탬프> --game-dir "<게임 폴더>"          # dry-run
kbl2k restore game_backup\<타임스탬프> --game-dir "<게임 폴더>" --apply  # 실제 복구
```

## 구조
```
src/kbl2k/
  schemas/        JSON Schema (draft 2020-12)
  cli.py          명령줄 진입점
  dataset.py      data/ 로딩
  schema.py       스키마 검증
  validate.py     의미 검증 (ID·등번호 중복, 출처 참조, 팀 소속 등)
  ratings.py      능력치 산정 (순수 함수, 규칙은 JSON)
  mapping.py      에셋 ID 매핑 검증·진행 현황
  backup.py       게임 파일 백업/복구 (SHA-256 manifest)
data/
  sources.json            출처 목록 (URL, 조회일)
  teams/*.json            팀 + 선수 로스터
  rules/rating_rules.json 능력치 산정 계수
  mappings/assets.json    얼굴/유니폼/코트/로고 ID 매핑
tests/            pytest
docs/             계획, 도구 조사
```

## 데이터 규칙
- **추정값을 넣지 않는다.** 모르는 값은 `null`, 미확인 선수는 `verification.status: "unverified"` 로 둔다.
- `verified` 로 바꾸려면 `sources` 에 출처가 최소 1개, `checked_at` 에 확인 날짜가 있어야 한다.
- 모든 출처는 `data/sources.json` 에 먼저 등록한다. 검증기는 등록되지 않은 출처 ID 를 거부한다.
- 비율 기록은 0–1 범위다 (38% → `0.38`).
- 능력치는 2K26 속성 22종을 쓴다(25–99). 수동 보정은 `ratings_override` 로 한다.

### 능력치 산정
속성별로 기록·신체 입력의 z-score 를 가중 평균한다.

```
rating = clamp(base + spread·z + league_offset + position_bonus, 25, 99)
```

- 출전 경기가 `min_games` 미만이면 평균 쪽으로 축소한다.
- 3P%·FT% 같은 성공률은 시도 수가 적으면 축소한다.
- 계수는 모두 `data/rules/rating_rules.json` 에 있다.
- 현재 계수는 **잠정값(provisional)** 이다. KBL 기록을 입력한 뒤 `calibrate` 로 보정해야 한다.

## 에셋 매핑
`data/mappings/assets.json` 의 각 항목은 다음과 같다.

```json
{"entity_type": "player", "entity_id": "kgc-...", "asset_type": "face",
 "game_id": null, "file": null, "tool": null, "status": "planned"}
```

- `asset_type`: 선수는 `face`·`portrait`, 팀은 `uniform_home`·`uniform_away`·`uniform_alt`·`court`·`logo`.
- 2K26 파일명/ID 규칙은 아직 검증되지 않았으므로 형식을 강제하지 않는다.
- `verified` 는 게임에서 실제 로드를 확인한 경우에만 쓴다. 이때 `tool` 과 `game_id` 또는 `file` 이 필요하다.
- 검증기는 대상 존재 여부, 중복 매핑, 같은 종류 내 `game_id`·파일 충돌을 검사한다.

## 테스트
```powershell
pytest
ruff check .
```
