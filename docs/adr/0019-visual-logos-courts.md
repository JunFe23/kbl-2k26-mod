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
- 확인 (2026-10-15): 코트 v2 중앙선 표시, 경기 시작 화면 약어가 JKJ/SK 로 나온다(세션마다 `venuelab apply` 후, 사용자 확인).
  → 약어는 팀 레코드 CITYSHORTNAME(+0x338)에서 온다. 세션용 빠른 명령 `venuelab apply --apply --teams-only` 추가.

## 유니폼 (2026-10-15, 진행 중)
- 목표: 2026-27 실제 유니폼과 거의 같게(사용자 요청). 참고: 정관장 공식 스토어(redboostersstore.com) 홈·원정 앞뒤 사진(브라우저로 보기만 함).
- 방식: CustomMyNBA(OzWolf) — 4096² 그림을 로고 칸 IFF 로 넣고, 게임 유니폼 편집기에서 배율 4.40·위치 (-0.34, 0.17)로 저지 전체에 씌운다.
  - 원본 저지 텍스처 교체는 보류: VenueLab 로 TXTR 설명은 꺼냈지만 실제 픽셀(.tld)은 풀리지 않는다.
- 전개도 보정 시험: 템플릿 영역 색칠 + 256px 격자 이미지를 정관장 홈 자리로 생성 → `logo005_secondary_5.iff`(NBA Secondary 목록)
  - 게임 `mods\logos\` 에 추가. 스냅샷: 추가 1 (기준 `20261015-152350-before-uniform-test`)
- 슈팅저지: Bulls/Hawks 전용 `clothing_resource_tshirt_ss_nba_pregame_core_003/009_color_tex.iff` 존재. 픽셀 데이터를 풀 수 없어 보류(별도 분석).
- 보정 결과 (게임 격자 시험): 템플릿 영역 그대로 맞는다. 앞판 가운데 x 2723, 게임 번호 중심 앞 y≈980·뒤 y≈780, 뒤 이름 y≈270,
  허리띠 초록이 반바지 허리밴드에 정확히 놓인다. 전개도 맨 위(y≈0~50)가 앞 V넥 끝 높이다.
- 참고 사진: 정관장 스토어 26-27 홈·원정 앞뒤 4장(사용자 승인 후 다운로드) → `assets_private/reference/kgc_2627/`
- 생성기: `kbl2k assets uniform <키>` (src/kbl2k/uniform.py, 설정 data/visuals/uniforms.json)
  - 사진을 팔레트 색으로 분류 → 번호·이름·글자 자리 메움 → 전개도로 옮김 → 글자·스폰서는 사진 마스크로 다시 얹음
  - 가슴 위 스폰서는 V넥보다 위라 전개도 밖으로 잘려서 아래로 150 내렸다. 뒤 DOORA 도 130 내렸다. 뒤 KBL 로고는 공간이 없어 뺐다.
  - 반바지 사진이 없어 단색 + RB 로고로 만들었다(추정 디자인).
- 유니폼 v1 반영: 홈 `logo005_secondary_5.iff`(교체), 원정 `logo006_secondary.iff`(추가, NBA Secondary 목록). 기준 스냅샷 `20261015-155328-before-kgc-uniform-v1`
- v1 게임 확인: 앞·옆·뒤 배치 정상. 다만
  - 그림은 몸에 **투영**된다 → 템플릿 BELT 구역이 반바지 중간 높이에 놓인다. v2 에서 BELT 를 반바지 색으로 바꿨다.
  - 그림 맨 위가 V넥 끝 높이라 어깨끈·목 옆은 유니폼 바탕색이 보인다 → 게임에서 바탕색으로 맞춘다(홈 검정, 원정 흰색).
- 유니폼 v2 반영: 홈·원정 두 파일 교체. 기준 스냅샷 `20261015-160155-before-kgc-uniform-v2`
- v2 게임 확인: 뒤판 글자가 왼쪽으로 쏠림 → 뒤판 가운데는 x≈835(등번호 중심, 템플릿 뒤 NBA 로고 위치). v3 에서
  뒤판을 사진 등 가운데(x 512) 기준으로 3856~1749 에 넓게 그리고, 사진 옆선 바깥은 읽지 않게 했다.
  얹을 글자의 원래 자리를 가장자리까지 넓혀 지워 잔상을 없앴다. EVERY'TIME 200 위로, 뒤 DOORA 100 아래로.
  게임 크기는 4.40 으로 맞춘다(4.38 이면 전체가 밀린다).
- 유니폼 v3 반영: 홈·원정 교체. 기준 스냅샷 `20261015-161700-before-kgc-uniform-v3`
- v3 게임 확인: 옆판 글자가 반바지까지 내려옴 → 게임 허리선은 전개도 y≈1780. v4 에서 `waist_uv` 1780 아래는 반바지 색,
  옆판은 허리선에서 끝내고 글자는 y 650~1700 에 넣었다.
- 유니폼 v4 반영: 홈·원정 교체. 기준 스냅샷 `20261015-162714-before-kgc-uniform-v4`
- v4 게임 확인: 거의 맞음. 앞 글자 양끝이 옆구리로 넘어감 → v5 에서 JUNG KWAN JANG·EVERY'TIME 85%(overlay `scale`).
  그림이 닿지 않는 어깨끈·목 주변은 바탕색으로 맞춘다: 홈 검정(사진도 어깨가 검정)·테두리 흰색, 원정 흰색·테두리 빨강/검정.
  더 정확히 하려면 게임 이미지 Y 를 올리고 디자인 전체를 내리는 방법이 있다(추가 시험 필요).
- 유니폼 v5 반영: 홈·원정 교체. 기준 스냅샷 `20261015-163402-before-kgc-uniform-v5`
- v5 게임 확인 (사용자): 거의 맞음. **게임 이미지 설정 = 크기 4.40, 이동 X -0.30, Y 0.17** (CustomMyNBA 안내의 -0.34 보다 -0.30 이 가운데).
  남은 것: 바탕색(홈 검정·흰 테두리, 원정 흰색·빨강/검정 테두리), 원정 게임 확인.
- SK 26-27 유니폼 (2026-10-15): knightsmall.com 레플리카 홈·원정 도안(앞 1200² + 상세 1350×13169, 사용자 승인 다운로드)
  → `assets_private/reference/sk_2627/`. 상세 이미지에서 앞·뒤 도안을 잘라 썼다(`*_front_d.png`, `*_back_d.png`).
  - 생성기 확장: 세로 기준점 여러 개(구간별 선형), 컬러 로고를 원래 색으로 얹기(overlay `mode: photo`), 옆판 줄무늬(`stripes`).
  - 흰/빨간 옆줄은 옆판에 넣었다(앞판 경계를 줄 안쪽으로 잡아야 가로세로 배율이 맞는다).
  - 뒤: 실제는 목 아래 요크·별·KBL·SK broadband 다음에 이름이 오지만 게임 이름은 목 바로 아래(y≈270) →
    기준점 [[200,-15],[300,80],[366,185],[470,270],[705,777],...] 로 위쪽을 압축했다.
  - 반바지 사진 없음 → 단색 + Knights 엠블럼(추정).
- SK 유니폼 v1 반영: 홈 `logo017_secondary.iff`, 원정 `logo018_secondary.iff`(추가, NBA Secondary 목록). 기준 스냅샷 `20261015-180646-before-sk-uniform-v1`
