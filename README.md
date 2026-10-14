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

# 2K26 포지션 직접 입력 (엑셀)
kbl2k positions export -o positions.csv   # primary/secondary 열 채우기
kbl2k positions import positions.csv --dry-run
kbl2k positions import positions.csv

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
  positions.py    KBL(G/F/C) ↔ 2K(PG…C) 포지션, CSV 입출력
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
- URL 이 없는 출처(사용자 제보 등)는 `url: null` 로 등록한다. `official: true` 출처는 URL 이 필수다.

### 포지션
| 필드 | 값 | 성격 |
|---|---|---|
| `position_kbl` | `G` / `F` / `C` | KBL 공식 표기 (사실 데이터) |
| `positions` | `PG` `SG` `SF` `PF` `C` 중 최대 2개 `[주, 보조]` | 2K26 에 넣을 값 (모드 설계값, 직접 입력) |

- 2K 시리즈 로스터는 5포지션 체계다. 2K26 에서도 같은지는 로스터 에디터 확정 후 최종 확인한다.
- `positions export` 로 만든 CSV 의 `suggested` 열에 KBL 포지션에 맞는 후보(G→PG/SG, F→SF/PF, C→C)가 나온다.
- 주 포지션이 후보와 다르면 경고만 하고 허용한다(예: F 를 C 로 쓰는 경우).
- `positions import` 는 CSV 에 오류가 하나라도 있으면 아무것도 바꾸지 않는다.
- CSV 에 없는 선수는 바뀌지 않는다.
- primary 를 비우면 '미정'(빈 배열)이 된다.
- 엑셀에서 저장할 때는 **CSV UTF-8** 형식을 쓴다.

### 로스터 상태
`roster_status` 를 생략하면 정상(active)이다.

```json
"roster_status": {"state": "injured", "since": null, "expected_return": null, "note": "골타박상, 약 2주"}
"roster_status": {"state": "replacement", "replaces": "kgc-rashawn-thomas", "note": "일시 대체 외국인"}
```

검증기는 다음을 확인한다.
- `replaces` 가 같은 팀 선수인지 (오류)
- 자기 자신을 대체하지 않는지 (오류)
- 대체 대상이 `injured` 상태인지 (아니면 경고)

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

## 공개 저장소 주의
이 저장소는 공개(public)다.
- KBL·구단 로고, 유니폼, 선수 얼굴 텍스처 등 상표권·초상권 에셋은 `assets_private/` 에 두며 커밋하지 않는다.
- 이미지 파일(`*.png`, `*.psd`, `*.tga`)과 게임 원본 파일(`*.iff`, `*.ROS`)은 `.gitignore` 로 차단되어 있다.
- 커밋 이메일은 GitHub noreply 주소를 쓴다(이 저장소의 로컬 git 설정).
