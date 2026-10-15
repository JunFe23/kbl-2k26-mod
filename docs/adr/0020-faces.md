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

## 시범: 변준형 (2026-10-15)
- 자리 번호(게임 메모리 읽기, `game_backup/venuelab/face_ids.json`): Bulls 3번 = 얼굴 8000(원래 Isaac Okoro), 초상화 9804.
  - 얼굴 번호 1(기본 얼굴)인 자리: 한승희, 에디 다니엘 → 따로 확인 필요.
- 사진: kbl.or.kr `files/kbl/players-photo/{kbl_player_id}.png` (470×609, 투명 배경, 사용자 승인) → `assets_private/reference/faces/`
- 생성: `kbl2k.face`(mediapipe 0.10 FaceMesh 478점 + scikit-image 구간별 아핀), 이마는 눈썹 위에서 자르고 원래 선수 턱수염은 피부색으로 메움.
- 묶기: `kbl2k.iffpack` — 원본 IFF + `<Binary>.dds`(texconv BC7 전체 mip).
- 게임 반영: `mods/char/sig/png8000_config_default.iff`, `mods/player_images/chr_g9804.iff` 추가(스냅샷 `20261015-200845-before-face-byun`).
  - 되돌리기: 두 파일 삭제.
- 알려진 한계: 머리카락(오코로 레게 머리)·머리 형태는 원래 선수 것.
- 게임 확인: 초상화 교체 성공, 얼굴 그림도 바뀜(사용자). 레게 머리 때문에 다른 사람처럼 보임.
- 머리카락 시험: 짧은 직모 + 같은 파일 체계(hair_01)인 페이튼 프리처드(8015)의 geo_hair_01·geo_hair_01_tangentspace·item_hair_01 을
  png8000_* 이름으로 mods 에 넣음(스냅샷 `20261015-201730-before-hair-byun`). 후보 얼굴 번호: `game_backup/venuelab/donor_candidates.json`.
- 머리카락 교체 성공(사용자 확인: 레게 머리 → 짧은 머리). 머리색: 프리처드 hair_color_o(갈색)를 평균 (30,27,26) 흑갈색으로
  채널 비율 조정(알파 유지) → item_hair_01 에 DDS 로 넣음(스냅샷 `20261015-212230-before-hair-black`).
- 결론(방식 확정 후보): 얼굴 그림 = 사진 변형, 머리카락 = 비슷한 머리 모양의 NBA 선수 파일을 같은 이름 체계로 복사 + 색 조정, 초상화 = 사진.
- 게임 확인(스크린샷): 얼굴·짧은 머리 반영. "머리가 비어 보임" → 원인: 피부색 보정이 두피에 그려진 머리카락까지 밝혔음.
  v2: 눈썹 위 두피의 어두운 털은 밝히지 않고 흑갈색으로 칠함(목·턱 그림자는 제외). 스냅샷 `20261015-*-before-face-byun-v2`.
