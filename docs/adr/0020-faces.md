# 0020. 선수 얼굴 — 텍스처 교체 방식(외부 작업)

- 상태: 제안 (시범 1명 → 확대)
- 날짜: 2026-10-15

## 맥락
- 사용자 요구: 30명 얼굴을 게임 안에서 손으로 만들지 않고 외부에서 작업한다.
- 우리 외국인 선수 중 2K26 에 실제 얼굴이 있는 선수는 없다(카탈로그 검색).
- 웹 조사(2026-10): 2K26 용 공개 얼굴 제작 문서·UV 템플릿 없음. Mr.Star Model Tool(유료 가능성, 메시 편집),
  Cyberface Mixer(Modium·온라인 인증 → 제외), 스트리밍 텍스처(.tld/.mip0) 해독 공개 도구 없음.
- 직접 확인한 것 (게임 파일은 읽기만):
  - 얼굴 파일 구성: `char/sig/png{ID}.iff`(머리 SCNE·모프), `png{ID}_config_*.iff`(얼굴 텍스처 TXTR:
    face_color_o, face_normal_o, wrinkle, bentnormal, detailnormal), `png{ID}_geo_hair_*.iff`(머리카락)
  - 메뉴 초상화: `player_images/chr_g{ID}.iff`(TXTR 하나, 512×512 BC7, 투명 배경 머리·어깨), `chr_r{ID}_a1~a3`
  - VenueLab 2.15 의 `venue_viewer_core` 텍스처 해독 함수로 .tld/.mip0 를 풀 수 있다 →
    초상화(chr_g1411)와 얼굴 color(png1015 face_color_o, 1024² BC7)를 PNG 로 꺼냈다.
    최상위 mip 은 별도 .mip0 에 있고, MemoryOffset 없는 세그먼트의 MemorySize·InflatedSize 로 해독한다.
  - CustomMyNBA 로고 IFF 는 원본 TXTR 를 그대로 두고 같은 이름의 `.dds` 를 함께 넣는다 → 게임이 그 DDS 를 읽는다
    (로고·코트·유니폼에서 검증).
- 얼굴 color 텍스처는 정면 얼굴이 가운데, 귀가 양옆, 목이 아래인 펼친 배치다.

## 결정 (제안)
- 3D 얼굴: 각 선수 자리의 기존 Face ID(원래 NBA 선수 얼굴)의 메시·머리카락은 그대로 두고 **face_color 텍스처만 교체**한다.
  - KBL 공식 정면 사진 → 얼굴 랜드마크(눈·코·입·턱선) 정렬 → 기존 텍스처의 얼굴 영역에 맞춰 변형 → 나머지(두피·귀·목)는 피부색으로 보정
  - `mods/char/sig/png{ID}_config_*.iff` = 원본 TXTR + 우리 DDS
  - 한계: 머리 형태·머리카락·normal(굴곡)은 원래 선수 것이다.
- 메뉴 초상화: `mods/player_images/chr_g{ID}.iff` = 원본 TXTR + KBL 사진으로 만든 512² DDS.
- 순서: 초상화 1명 + 얼굴 1명 시범 → 게임 확인 → 30명 확대.
- 사진: KBL 공식 사이트 프로필 사진. 내려받기 전 사용자 승인. `assets_private/` 에만 둔다(커밋 금지).
- 위험: 텍스처 교체가 게임 저장·온라인에 영향 없음(mods 폴더 방식). 되돌리기 = mods 파일 삭제.
