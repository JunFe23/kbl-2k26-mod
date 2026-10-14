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

## 에셋 파일명 규칙 (2K26 미검증)
| 에셋 | 알려진 규칙 | 해당 버전 | 근거 |
|---|---|---|---|
| 얼굴(사이버페이스) | `png####.iff` (+ `face*.iff`), 파일 1개 = 사이버페이스 1개, 생성 선수는 미사용 CF ID 필요 | 2K14/2K24 | [요약] https://forums.nba-live.com/viewtopic.php?p=2005948 |
| 유니폼 | `u*` (예 `uh005.iff`), 레트로 `r*` | 2K11 | [미확인] |
| 경기장/코트 | `s*` 경기장, `f*` 코트 바닥 | 2K11 | [미확인] |
| 로고 | `logo*` | 2K11 | [미확인] |

→ `asset_mapping.schema.json` 은 이 규칙을 **강제하지 않는다.** 2K26 에서 실제 로드를 확인한 뒤에만 `status: verified` 로 기록한다.

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

## 외부 도구 호환성 검증 체크리스트
도구를 실제 게임 파일에 쓰기 전에 모두 통과해야 한다.
1. 배포처가 NLSC Downloads 또는 제작자 공식 채널인지 확인. 파일 SHA-256 기록.
2. 도구 버전과 대상 게임 패치 버전(Steam 빌드)이 일치하는지 확인. `assets.json` 의 `game_version` 에 기록.
3. 백신 검사. 관리자 권한을 요구하면 이유 확인.
4. 도구가 쓰는 파일 목록을 파악 → `kbl2k backup` 으로 해당 파일 백업 → `kbl2k verify-backup` 확인.
5. 오프라인 상태에서 MyNBA 를 새로 시작해 로드·경기 1회 확인.
6. `kbl2k restore --apply` 로 원상 복구가 실제로 되는지 확인(복구 리허설).
7. 결과를 아래 표에 기록.

| 도구 | 버전 | SHA-256 | 게임 빌드 | 결과 | 날짜 |
|---|---|---|---|---|---|
| (미검증) | | | | | |
