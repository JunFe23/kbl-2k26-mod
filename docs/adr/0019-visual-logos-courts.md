# 0019. 비주얼 1단계 — 로고·코트를 mods 폴더 IFF 로 교체

- 상태: 승인 (진행 중)
- 날짜: 2026-10-15

## 맥락
- 정관장·SK 는 Chicago Bulls·Atlanta Hawks 자리를 쓴다(ADR-0015). 그래서 두 팀의 로고·코트 파일을 바꾸면 된다.
- 대상 파일: 게임 manifest 와 OzWolf 설정(Configuration.json)이 일치한다.

  | 팀 (자리) | 로고 | 코트 바닥 |
  |---|---|---|
  | 정관장 (Bulls) | `logos/logo003.iff` | `levels/arena_003_int_floor.iff` |
  | SK (Hawks) | `logos/logo009.iff` | `levels/arena_009_int_floor.iff` |

- 2K26 은 게임 폴더의 `mods` 폴더에서 대체 IFF 를 읽는 것으로 알려져 있다.
  - 근거: OzWolf README, 2kspecialist 설치 안내. 이 프로젝트에서는 아직 검증하지 않았다.
- IFF 는 **ZIP 컨테이너**다(7-Zip 으로 확인). 안에 텍스처 설명(`*.TXTR`)과 DDS 텍스처가 들어 있다.

## 결정
- 도구: **OzWolf/nba2k26-custom-mynba v1.1.0**
  - SHA-256 `c7588c1dca43d2074dfc37ffc9dfd319d647b5b5d9d53de2287e1b16ec5ddadd`, GitHub digest 와 대조한다.
  - 의존 도구: Microsoft texconv, 7-Zip(7z.exe + 7z.dll). 도구 폴더에 함께 둔다.
  - 위치: `D:\2K Tools\CustomMyNBA\` (프로젝트·게임 폴더 밖)
  - 다운로드·실행은 사용자가 한다(ADR-0013). Claude 는 해시·결과물을 확인한다.
- 이미지: 사용자가 준비한다(상표 — Claude 가 내려받지 않음). `assets_private/` 에서만 다루고 공개 저장소에 커밋하지 않는다(ADR-0006).
  - 로고 1024×1024 PNG, 투명 배경
  - 코트 8192×4096 PNG, OzWolf 템플릿 기반으로 **사용자가 직접 디자인**
- 게임 반영: 생성된 IFF 를 `E:\...\NBA 2K26\mods\logos\`, `mods\levels\` 에 복사한다.
  - 원본 아카이브는 건드리지 않는다.
  - 복사 전후로 `kbl2k game snapshot/diff` 를 한다. 되돌리기 = `mods` 폴더에서 해당 파일 삭제
- 순서: 로고로 mods 방식을 먼저 검증한 뒤 코트를 한다.

## 결과
- 로고가 게임에 반영되는지, EAC 켠 일반 실행에서도 되는지 확인한다(`mods` 는 EAC 와 무관하다는 주장이 있으나 미검증).

## 진행 (2026-10-15)
- OzWolf v1.1.0 해시를 확인했다. 실행 시 AhnLab V3 가 검사 경고를 띄웠으나 차단하지는 않았다.
- 로고 변환: `kbl2k assets logo`
  - SK 는 SVG 렌더링
  - 정관장은 JPG 의 바깥 흰 배경만 제거하고, 로고 실루엣 안쪽 틈은 흰색으로 채웠다
- 생성: `logo003.iff`(정관장/Bulls), `logo009.iff`(SK/Hawks)
  - 각 ZIP 안에 `logo.TXTR` + `logo.2df327256b936ada.dds`(1024² BC7+mip)
- 게임 반영: `NBA 2K26\mods\logos\` 에 복사했다. 스냅샷 비교 결과 추가 2 / 삭제 0 / 변경 0
  - 기준 스냅샷: `20261015-121436-before-mods-logos`
- 되돌리기: `mods\logos\logo003.iff`, `logo009.iff` 삭제
- 확인할 것: 게임 화면에 새 로고가 나오는가, 일반(EAC) 실행에서도 되는가

## 코트 (2026-10-15)
- 템플릿: OzWolf Export Templates → `templates.7z`(실제 ZIP) 안의 `court_floor.psd` 8192×4096.
  - 위에서 본 전체 코트이고, 캔버스 좌표가 곧 코트 위치다. 코트 안쪽 x 975~7223, y 437~3660, 센터 (4096, 2048).
  - 레이어(바깥 색, 키, 선 10종, 나무 바닥, 그림자·긁힘·요철)를 psd-tools 로 각각 PNG 로 꺼냈다.
    위치: `D:\2K Tools\CustomMyNBA\templates\court_layers\` (저장소 밖)
- 합성: `kbl2k assets court <팀> <출력> --layers ... --logo ...`, 디자인 값은 `data/visuals/courts.json`
  - 실제 경기장 사진 썸네일을 참고한 근사치다: 밝은 원목, 빨간 키·바깥 띠, 센터 로고, 사이드라인·베이스라인 글자
  - NBA 로고 레이어는 쓰지 않는다.
- 출력: OzWolf 입력 규칙대로 `teams\RedBoosters\court_floor.png`, `teams\Knights\court_floor.png`
- 다음: 사용자 확인 → OzWolf 에서 IFF 생성(사용자) → 스냅샷 → `mods\levels\` 복사
  - 게임 안에서는 경기장(stadium)만 편집하고 코트 바닥 편집 화면에는 들어가지 않는다(OzWolf README: 들어가면 커스텀 바닥이 덮어써짐).
- 게임 반영 (2026-10-15): OzWolf Generate Mods 결과 `arena_003_int_floor.iff`, `arena_009_int_floor.iff`(각 ZIP 36개 항목, 약 39MB)를
  `NBA 2K26\mods\levels\` 에 복사했다. 스냅샷 비교: 추가 2 / 삭제 0 / 변경 0
  - 기준 스냅샷: `20261015-145601-before-mods-levels`
  - 되돌리기: `mods\levels\` 의 두 파일 삭제
  - 로고는 다시 생성됐지만(해시만 다름) 이미 확인된 기존 파일을 유지했다.
- 게임 확인 (2026-10-15): 정관장 코트가 Bulls 홈 경기에 나온다(사용자 스크린샷).
  - 문제: 중앙선 없음 → 템플릿 'Center Line' 레이어가 psd-tools 로 렌더링되지 않았다(빈 이미지).
    중앙선을 직접 그리고(10px, y 438~3659), 로고는 선 위에 얹도록 순서를 바꿨다. 재생성 후 Generate Mods → 재복사 필요.
- 경기 시작 화면의 팀 마크·약어(ATL/CHI):
  - 3D 로고는 별도 에셋 `logos/logo003_3d.iff`, `logo003_3d_mirror.iff`(Hawks 는 009)이다. 3D 모델이라 OzWolf 로는 못 바꾼다 → 조사 과제.
  - 약어는 팀 레코드 CITYSHORTNAME(+0x338)으로 추정한다. 커스텀 로스터에서는 재로드 시 되돌아가므로(ADR-0018) 세션마다 `venuelab apply` 로 다시 써야 한다(확인 필요).
- 코트 v2(중앙선) 반영: 게임 `mods\levels\` 두 파일 교체, 스냅샷 비교 변경 2 (기준 `20261015-150814-before-court-v2`)
