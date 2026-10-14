# NBA 2K26 PC 모딩 도구 조사 (2026-10-14 기준)

> 표기: **[확인]** 직접 페이지 확인 · **[요약]** 검색 결과 요약만 확인(원문 미열람) · **[미확인]** 근거 부족/구버전 정보
>
> NLSC(nba-live.com) 원문 페이지는 조사 시점에 접속이 차단(403/연결 거부)되어 대부분 **[요약]** 수준이다.
> 아래 어떤 도구도 아직 이 프로젝트에서 **호환성 검증을 하지 않았다.** 사용 전 아래 체크리스트를 통과해야 한다.

## 결론
- 2K26 PC 주요 도구는 **비공개 소스**이며 GitHub 가 아닌 NLSC Downloads / Ko-fi / Discord 로 배포된다.
- GitHub 에는 신뢰할 만한 2K26 오픈소스 로스터 에디터가 없다.
- 어떤 도구도 로스터 import/export 포맷(CSV/JSON 컬럼)을 공개 문서로 제공하지 않는다
  → 이 프로젝트의 JSON 이 **원천 데이터(source of truth)** 이고, 게임 반영은 도구 확정 후 별도 어댑터로 구현한다.

## 로스터 / 데이터 편집
| 도구 | 배포 | 2K26 | 기능 | 비고 | 근거 |
|---|---|---|---|---|---|
| 2KVenueLab (SexCurryBeats) | NLSC Downloads, 무료 | 지원(2K11–2K26) | IFF 뷰어/익스포터, 아카이브, 패키지 staging/restore, 로스터 에디터 | 최신 버전(1.4/1.5) 불명확, 라이선스 불명 | [요약] https://www.nba-live.com/tag/tool/ |
| Immerse – External Roster Editor | NLSC 포럼, Dribble 계정 필요 | 부분 지원 | 능력치 프리셋, 일괄 편집, 이적 | 오프셋 일부만 2K26 지원 | [요약] https://forums.nba-live.com/viewtopic.php?p=2100085 |
| jek-archives/nba2k26editor | GitHub | 불명 | JS 웹앱 + Python 스크립트 | 라이선스·README 없음 | [확인] GitHub API |
| mryangyeahfun/NBA2K-Roster-Editor | GitHub | 불명 | changelog.json 만 공개 | 라이선스·README 없음 | [확인] GitHub API |
| Cheat Engine 테이블 | — | 검증된 2K26 테이블 없음 | — | itch.io "Cheat Menu" 류는 악성코드 위험 → 사용 금지 | [미확인] |

## 검토한 GitHub 도구: OzWolf/nba2k26-custom-mynba (2026-10-15, 소스 직접 확인)
- 저장소: https://github.com/OzWolf/nba2k26-custom-mynba
  - Apache-2.0, C# 콘솔 앱, 최신 v1.1.0 (2026-05-15)
  - ★1, 릴리스 다운로드 123회
- 용도: **로스터 에디터가 아니다.** 로고·코트 바닥·유니폼 텍스처를 IFF 로 만드는 도구다(비주얼 단계용).
- 동작 [확인 — 소스]:
  - 자기 폴더의 `./mods/logos`, `./mods/levels`, `./work`, `./teams` 와 `%APPDATA%\NBA2K26CustomMyNBA\leagues.json` 에만 쓴다.
  - 게임 폴더는 건드리지 않는다. 사용자가 결과 IFF 를 게임의 `mods` 폴더로 직접 복사한다.
  - IFF 생성 방식: 내장 템플릿 IFF(logo.iff, arena_floor.iff)를 복사한다. PNG 를 texconv 로 BC7 DDS 로 변환해 7-Zip 으로 IFF 안에 넣는다.
    - → **IFF 는 7z 형식 컨테이너**라는 근거다.
  - 외부 의존성: Microsoft texconv, 7-Zip
- 팀 슬롯 매핑 [소스 Configuration.json, 게임 내 미확인]:
  - 36팀(NBA 30 + 확장 6)
  - 예: 76ers = `logo000.iff` / `arena_000_int_floor.iff`
  - 확장팀: Kansas City Knights, Nashville Stars, Pittsburgh Force, San Diego Surf, Virginia Storm, Vancouver Ravens
- 위험 요소:
  - 릴리스 exe 는 서명이 없고 1.2GB(게임 에셋 템플릿 내장)다.
  - exe 가 공개 소스로 빌드된 것인지 확인할 수 없다.
  - 템플릿 IFF 가 저장소에 없어 직접 빌드할 수 없다.
- 판정: 비주얼 단계(5단계)에서 후보로 쓴다. 쓸 때는 다음을 지킨다.
  - GitHub digest 와 SHA-256 을 대조한다.
  - Windows Defender 로 검사한다.
  - 프로젝트·게임 폴더 밖의 전용 폴더에서 실행한다.
  - 게임 `mods` 에 복사하기 전후로 `kbl2k game snapshot/diff` 를 한다.

## 검토한 도구: bird556/NBA-2K26-Roster-Editor (2026-10-15, 소스 직접 확인)
- 저장소: https://github.com/bird556/NBA-2K26-Roster-Editor
  - Electron/JavaScript, 라이선스 없음, ★1
  - 커밋은 2026-05-26 하루뿐, 릴리스 없음
- 설명은 "오프라인 로스터/세이브 파일 편집기"다.
- **실제로는 동작하지 않는 초기 뼈대다** [확인 — 소스]:
  - `rosterParser.js` 와 `rosterWriter.js` 가 모두 "real parsing/serialisation not yet implemented" 오류를 던진다.
  - 화면은 `mockData.js` 의 가짜 데이터만 표시한다.
  - 게임 경로는 하드코딩되어 있고, 로스터 폴더명도 미확인(TODO)이다.
- 판정: **사용 불가.** 다만 파일 기반(메모리 편집 아님) 접근이라, 완성되면 다시 검토할 가치는 있다.

## 검토한 사이트: 2kspecialist.net (2026-10-15)
- 성격: NBA 2K 모드 모음 블로그다. 다른 모더의 사이버페이스·코트·유니폼·로스터 등을 재배포한다.
  - 작성자는 게시물별로 표기한다. 예: "BrodieShai-Fr"
- 다운로드: 각 게시물의 "PROCEED TO DOWNLOAD" → 사이트 내부 중간 페이지 → RAR 파일
  - 최종 파일 호스트는 확인하지 못했다.
- 설치 방법 [게시물 본문]: RAR 압축을 풀고 `mods` 폴더를 게임 폴더(`steamapps\common\NBA 2K26`)에 복사한다. 모드 매니저는 필요 없다.
  - → OzWolf 도구 README 와 같은 방식이다. **2K26 은 게임 폴더의 `mods` 폴더에서 대체 파일을 읽는다**는 근거가 2개로 늘었다(게임 내 확인은 아직).
- KBL 관련 콘텐츠: 없다. 사이버페이스는 NBA 선수용이다.
- 온라인·안티치트 경고: 게시물에 없다.
- 판정:
  - KBL 선수 얼굴의 직접 출처로는 쓸 수 없다.
  - `mods` 폴더 구조와 사이버페이스 파일 구성(`char/sig/png{ID}*`)을 익히는 참고 자료로는 쓸 만하다.
  - 받을 때는 RAR 을 Defender 로 검사한다.
  - 게임 `mods` 에 복사하기 전후로 `kbl2k game snapshot/diff` 를 한다.
  - 재배포 사이트이므로 원작자 표기와 배포 허용 여부를 확인한다.

## 텍스처 / 모델 / 로딩
| 도구 | 2K26 | 내용 | 근거 |
|---|---|---|---|
| Looyh – NBA 2K26 File Explorer | 지원 | 게임 아카이브 탐색·검색·추출, VCUIELEMENT 뷰어 | [요약] |
| Looyh – modded-IFF fixer | 지원 | 패치 1.4 이후 압축 포맷 검사가 엄격해져 깨진 커스텀 IFF 복구 | [요약] |
| IFF Data Processing Tool | 2K25/2K26 | IFF 편집 | [요약] https://forums.nba-live.com/viewtopic.php?p=2101524 |
| NBA 2K Hook (Looyh) | 2K23/2K24만 확인 | 플러그인 스크립트 로더 | [요약] |
| Modium (모드 매니저) | 주장됨 | 원클릭 설치/우선순위, 오프라인 전용, 암호화 팩 | [요약/미확인] — 쓰기 내용 검증 불가 |

- 모드 로딩: 가이드들은 `steamapps\common\NBA 2K26` 에 `.iff` 또는 `mods` 폴더를 둔다고 설명한다. **원본을 덮어쓰지 않는다는 공식 근거는 찾지 못했다** [미확인]
  → 어떤 방식이든 적용 전에 `kbl2k backup` 으로 대상 파일을 백업한다.
- 게임 패치 시 수정 파일이 덮어써질 수 있다. 2K25 모드 대부분은 2K26 에서 동작하지 않는다.

## 이 PC 의 설치 정보 [확인] (2026-10-14, `kbl2k game info`)
| 항목 | 값 |
|---|---|
| 설치 폴더 | `E:\game\steam\steamapps\common\NBA 2K26` (약 102GB) |
| Steam appid / 빌드 | 3472040 / **24237529** (마지막 업데이트 2026-08-15) |
| 실행 파일 | `NBA2K26.exe` — 2K Games, Inc. 서명 유효 |
| EAC 실행기 | `start_protected_game.exe` — EasyAntiCheat Oy 서명 유효 |
| `mod.exe` (8.4MB) | **서명·버전 정보 없음.** 게임 파일과 같은 시각(2026-07-19 12:58)에 생성됨. SHA-256 `1dc099413119c1852b681b4bd5166811ab9b6a85a4d599871bb109b03e9b0e14`. 정체 미확인 → 실행하지 않음 |
| 세이브/로스터 | `E:\game\steam\userdata\<SteamID>\3472040` (Steam 클라우드 동기화 대상) |
| 그래픽 설정 | `%LOCALAPPDATA%\2K Sports\NBA 2K26` |
| 기존 모드 | 없음 (`mods` 폴더 없음, 기준 스냅샷 162개 파일) |

## 에셋 파일명 규칙 [확인 — build 24237529 의 게임 manifest 에서 직접 확인]
게임 루트의 `manifest` 는 아카이브(0A, 0B…) 안의 에셋 목록(`경로,아카이브,오프셋,크기`, 589,895개)이다.

| 에셋 | 2K26 규칙 | 수 / ID 범위 |
|---|---|---|
| 얼굴(사이버페이스) | `char/sig/png{ID}.iff` (+ `png{ID}_geo_hair_*`, `_config_*` 등 부속) | 3,127개 / 35~9986 |
| 포트레이트 | `player_images/chr_g{ID}.iff`, `chr_r{N}_a{N}.iff` | 2,171개(g) |
| 로고 | `logos/logo{ID}.iff` (+ `_wm`, `_wm_alt`, `_secondary`, `_white`, `_mural` 등) | 406개 / 0~1089 |
| 코트 | `levels/arena_{ID}_int.iff`, `levels/arena_{ID}_int_floor.iff` | 106개 / 0~924 |
| 유니폼(메뉴) | `frontend_uniforms/u{N}{팀약어}_{N}_home/away.iff` | 예: `u#phi_#_home` |
| 유니폼(텍스처) | `clothing/clothing_resource_u{N}{팀약어}_{N}_home/away_jersey_tiled.iff` | |
| 확장팀 유니폼 | `frontend_uniforms/expansion{1~36}_home/away.iff` | 36쌍 → **MyNBA 확장팀용 에셋 존재** |

- 2K14/2K24 의 `png{ID}` 얼굴 규칙은 2K26 에도 그대로다. 단 경로가 `char/sig/` 아래다.
- 2K11 시절의 `s*`/`f*`/`uh*` 규칙은 2K26 에 해당하지 않는다.
- 위 규칙은 **파일이 존재함**을 확인한 것이다.
  - 커스텀 파일이 어떤 방식(mods 폴더 등)으로 로드되는지는 아직 미확인이다.
  - 그래서 `asset_mapping` 의 `verified` 는 여전히 게임 내 로드 확인 후에만 쓴다.

## 능력치 이름
2K26 MyPLAYER 속성 22종을 사용한다. 출처는 팬 사이트(https://hoopsgamers.com/nba-2k26-attributes)이다 **[확인]**.
- Finishing: Close Shot, Driving Layup, Driving Dunk, Standing Dunk, Post Control
- Shooting: Mid-Range Shot, Three-Point Shot, Free Throw
- Playmaking: Pass Accuracy, Ball Handle, Speed With Ball
- Defense: Interior Defense, Perimeter Defense, Steal, Block
- Rebounding: Offensive Rebound, Defensive Rebound
- Physicals: Speed, Agility, Strength, Vertical, Stamina

로스터 전용 속성(Hands, Shot IQ, Pass IQ, Help Defense IQ, Lateral Quickness, Hustle, Durability, Potential 등)은 2K26 에서 확인되지 않아 제외했다 **[미확인]**. 로스터 에디터를 확정한 뒤 게임 내 목록과 대조해 추가한다.

## 안티치트 / 안전
- PC 판은 Easy Anti-Cheat 를 사용한다 **[요약]** https://support.nba2k.com/hc/en-us/articles/42216723600659-NBA-2K-Anti-Cheat-on-PC
- 온라인 상태에서 편집 도구를 쓰다 제재된 사례 보고가 있다 **[요약]** https://www.nba-live.com/tff-5-unfortunate-barriers-modding/
- **모드 작업과 테스트는 오프라인 MyNBA 에서만 한다.** EAC 우회 실행 옵션은 2K25 기준 정보이므로 [미확인].
- 이 계정은 MyTEAM 등 온라인 모드를 사용한 기록이 있다(userdata 캐시). 다음을 지킨다.
  - 메모리 편집형 에디터(실행 중인 게임에 붙는 방식)는 온라인 접속 상태에서 절대 쓰지 않는다.
  - 커스텀 로스터 세이브는 Steam 클라우드로 동기화된다. 필요하면 테스트 기간에 클라우드 동기화를 끈다.

## 외부 도구 호환성 검증 체크리스트
도구를 실제 게임 파일에 쓰기 전에 모두 통과해야 한다. 절차의 근거는 docs/adr/0013 이다.
0. 도구 설치·실행 **전** 기준 스냅샷을 만든다.
   - `kbl2k game snapshot --label before-<도구>`
   - 세이브 폴더도 기록한다: `kbl2k game snapshot --dir <userdata 경로> --label before-<도구>-save`
1. 배포처가 NLSC Downloads 또는 제작자 공식 채널인지 확인한다. 파일 SHA-256 을 기록한다.
2. 도구 버전과 대상 게임 패치 버전(Steam 빌드)이 일치하는지 확인. `assets.json` 의 `game_version` 에 기록.
3. 백신 검사. 관리자 권한을 요구하면 이유 확인.
4. 도구가 쓰는 파일 목록을 파악 → `kbl2k backup` 으로 해당 파일 백업 → `kbl2k verify-backup` 확인.
5. 오프라인 상태에서 MyNBA 를 새로 시작해 로드·경기 1회 확인.
6. `kbl2k restore --apply` 로 원상 복구가 실제로 되는지 확인(복구 리허설).
7. 도구 사용 후 `kbl2k game diff <before 스냅샷>` 으로 실제로 바뀐 파일을 확인한다.
   - 게임 폴더에서 바뀌면 안 되는 파일(아카이브, exe)이 바뀌었으면 즉시 복구하고 사용을 중단한다.
8. 결과를 아래 표에 기록한다.

| 도구 | 버전 | SHA-256 | 게임 빌드 | 결과 | 날짜 |
|---|---|---|---|---|---|
| (미검증) | | | 24237529 | | |

## 2K26 세이브 파일 형식 [확인 — 이 PC, 2026-10-15]
- 위치: `E:\game\steam\userdata\<SteamID>\3472040\remote\` (Steam 클라우드 동기화 대상)
- 파일 목록: `UserData`, `Settings`, `CreatedPlayers`, `MyCAREER0001`, `RosterDescriptions`, `SaveDescriptions`, `CareerModeBuilds` 등
- 모든 파일이 `EBNH` 매직 + 8바이트(파일별 상이) + 8바이트(3종) + 암호화 본문 구조다.
  - 엔트로피는 약 8.0, 크기는 8의 배수다.
- 결론: 로스터·세이브 파일은 **암호화**되어 있어 파일 기반 편집이 불가하다.
  - 2K26 에디터가 모두 메모리 편집 방식인 이유로 보인다.
  - 자세한 판단은 docs/adr/0014 를 본다.
- 2KVenueLab 2.15 다운로드 정보: https://forums.nba-live.com/downloads.php?view=detail&df_id=13923
  - `2K VenueLab 2.15.zip`, MD5 `fb5e5bc97ce31d85de60093520b3711b` (2026-07-22)
  - 본 사이트(www.nba-live.com)는 접속 불가, 포럼 주소는 접속 가능(2026-10-15)
  - 2K26 로스터 편집은 메모리 편집이며 "EAC 끄고 오프라인 실행"이 필요하다(제작자 안내).
  - 새 선수 생성과 CSV 가져오기는 아직 지원하지 않는다. 기존 선수를 덮어쓰는 방식이다.
