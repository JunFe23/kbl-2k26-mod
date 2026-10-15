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
- IFF 는 7z 컨테이너다. 안에 BC7 DDS 텍스처가 들어 있다(OzWolf 소스).

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
