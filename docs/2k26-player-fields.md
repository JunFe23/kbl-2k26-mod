# NBA 2K26 선수 레코드 필드 (2KVenueLab 2.15 기준)

- 출처: 2KVenueLab 2.15 가 쓰기 직전 남긴 선수 모델(`roster_workbench/backups/players/*.json`)
  - Matas Buzelis, Steam 빌드 24237529, 2026-10-15
- 게임 내 확인:
  - `rating_driving_layup` 85→99 쓰기 → MyNBA 저장 → 재실행 후 유지 확인 (사용자, 2026-10-15)
  - 나머지 필드는 VenueLab 이 `confirmed_editable` 로 표시한 것이고, 이 프로젝트에서 따로 확인하지는 않았다.
- 오프셋은 `playerBase` 기준이다. 게임 업데이트 때 바뀔 수 있다.

## 인코딩
| type | 규칙 |
|---|---|
| `rating_u8` | 1바이트 raw. **표시값 = raw / 3 + 25** (raw = (표시값 − 25) × 3, 25~99 → 0~222) |
| `rating_u8_bitfield` | u16 컨테이너의 bit 6 부터 8bit 가 raw. 인접 필드와 바이트를 공유한다 → 쓰기 전에 반드시 최신 값을 다시 읽는다 |
| `float32` (weight) | 파운드 단위 실수 |
| `u16_bitfield` (jersey) | 인코딩된 u16 (예: 14 → 0x6470) |
| `ushort_div100` | Appearance Data 의 u16 / 100 (신장·윙스팬 cm) |

## 필드 목록
| key | 이름 | 오프셋 | 형식 | 쓰기 |
|---|---|---|---|---|
| `weight` | Weight | `+0x100` | float32 | 예 |
| `jersey` | Jersey | `+0x10D` | u16_bitfield | 예 |
| `current_team_pointer` | Current Team Pointer | `+0x60` | ptr64 | 아니오 |
| `contract_team_pointer` | Contract Team Pointer | `+0x68` | ptr64 | 아니오 |
| `appearance_data_pointer` | Appearance Data Pointer | `+0x78` | ptr64 | 아니오 |
| `face_id` | Face ID | `+0x108` | u16 | 아니오 |
| `portrait_id` | Portrait ID | `+0x328` | u32 | 아니오 |
| `headshot_raw` | Headshot Raw | `+0x3D5` | u8_raw_bitfield | 아니오 |
| `rating_driving_layup` | Driving Layup | `+0x3E1` | rating_u8_bitfield (bit 6, 8bit) | 예 |
| `rating_post_fade` | Post Fade | `+0x3E2` | rating_u8_bitfield (bit 6, 8bit) | 예 |
| `rating_post_hook` | Post Hook | `+0x3E4` | rating_u8 | 예 |
| `rating_post_moves` | Post Moves | `+0x3E5` | rating_u8 | 예 |
| `rating_draw_foul` | Draw Foul | `+0x3E6` | rating_u8 | 예 |
| `rating_close_shot` | Close Shot | `+0x3E7` | rating_u8 | 예 |
| `rating_midrange` | Midrange Shot | `+0x3E8` | rating_u8 | 예 |
| `rating_three_point` | 3pt Shot | `+0x3E9` | rating_u8 | 예 |
| `rating_free_throw` | Free Throw | `+0x3EA` | rating_u8 | 예 |
| `rating_ball_control` | Ball Control | `+0x3EB` | rating_u8 | 예 |
| `rating_passing_iq` | Passing IQ | `+0x3EC` | rating_u8 | 예 |
| `rating_pass_accuracy` | Pass Accuracy | `+0x3ED` | rating_u8 | 예 |
| `rating_offensive_rebound` | Offensive Rebound | `+0x3EE` | rating_u8 | 예 |
| `rating_defensive_rebound` | Defensive Rebound | `+0x3EF` | rating_u8 | 예 |
| `rating_interior_defense` | Interior Defense | `+0x3F0` | rating_u8 | 예 |
| `rating_perimeter_defense` | Perimeter Defense | `+0x3F1` | rating_u8 | 예 |
| `rating_pass_perception` | Pass Perception | `+0x3F2` | rating_u8 | 예 |
| `rating_block` | Block | `+0x3F3` | rating_u8 | 예 |
| `rating_steal` | Steal | `+0x3F4` | rating_u8 | 예 |
| `rating_defensive_consistency` | Defensive Consistency | `+0x3F5` | rating_u8 | 예 |
| `rating_help_defense_iq` | Help Defense IQ | `+0x3F6` | rating_u8 | 예 |
| `rating_standing_dunk` | Standing Dunk | `+0x3F7` | rating_u8 | 예 |
| `rating_driving_dunk` | Driving Dunk | `+0x3F8` | rating_u8 | 예 |
| `rating_speed` | Speed | `+0x3F9` | rating_u8 | 예 |
| `rating_speed_with_ball` | Speed with Ball | `+0x3FA` | rating_u8 | 예 |
| `rating_vertical` | Vertical | `+0x3FB` | rating_u8 | 예 |
| `rating_strength` | Strength | `+0x3FC` | rating_u8 | 예 |
| `rating_stamina` | Stamina | `+0x3FD` | rating_u8 | 예 |
| `rating_hustle` | Hustle | `+0x3FE` | rating_u8 | 예 |
| `rating_agility` | Agility | `+0x3FF` | rating_u8 | 예 |
| `rating_shot_iq` | Shot IQ | `+0x400` | rating_u8 | 예 |
| `rating_offensive_consistency` | Offensive Consistency | `+0x401` | rating_u8 | 예 |
| `rating_intangibles` | Intangibles | `+0x402` | rating_u8 | 예 |
| `rating_potential` | Potential | `+0x403` | rating_u8 | 예 |
| `rating_head_durability` | Head Durability | `+0x404` | rating_u8 | 예 |
| `rating_neck_durability` | Neck Durability | `+0x405` | rating_u8 | 예 |
| `rating_back_durability` | Back Durability | `+0x406` | rating_u8 | 예 |
| `rating_left_shoulder_durability` | Left Shoulder Durability | `+0x407` | rating_u8 | 예 |
| `rating_right_shoulder_durability` | Right Shoulder Durability | `+0x408` | rating_u8 | 예 |
| `rating_left_elbow_durability` | Left Elbow Durability | `+0x409` | rating_u8 | 예 |
| `rating_right_elbow_durability` | Right Elbow Durability | `+0x40A` | rating_u8 | 예 |
| `rating_left_hip_durability` | Left Hip Durability | `+0x40B` | rating_u8 | 예 |
| `rating_right_hip_durability` | Right Hip Durability | `+0x40C` | rating_u8 | 예 |
| `rating_left_knee_durability` | Left Knee Durability | `+0x40D` | rating_u8 | 예 |
| `rating_right_knee_durability` | Right Knee Durability | `+0x40E` | rating_u8 | 예 |
| `rating_left_ankle_durability` | Left Ankle Durability | `+0x40F` | rating_u8 | 예 |
| `rating_right_ankle_durability` | Right Ankle Durability | `+0x410` | rating_u8 | 예 |
| `rating_left_foot_durability` | Left Foot Durability | `+0x411` | rating_u8 | 예 |
| `rating_right_foot_durability` | Right Foot Durability | `+0x412` | rating_u8 | 예 |
| `rating_misc_durability` | Misc Durability | `+0x413` | rating_u8 | 예 |
| `rating_passing_vision` | Passing Vision | `+0x414` | rating_u8 | 예 |
| `rating_hands` | Hands | `+0x415` | rating_u8 | 예 |
| `appearance_height_cm` | Appearance Height (cm) | `Appearance+0x0` | ushort_div100 | 예 |
| `appearance_wingspan` | Appearance Wingspan | `Appearance+0x2` | ushort_div100 | 예 |
| `appearance_trunk_length` | Trunk Length | `Appearance+0x4` | float32 | 예 |
| `appearance_shoulder_length` | Shoulder Width | `Appearance+0x8` | float32 | 예 |
| `appearance_arm_scale` | Arm Scale | `Appearance+0xC` | float32 | 아니오 |
| `appearance_neck_length` | Neck Length | `Appearance+0x10` | float32 | 예 |

## 생년월일 (블루프린트 Vitals, ADR-0018 분석 2)
VenueLab 2.15 의 선수 모델(field_registry)에는 없다. 블루프린트(`nba2k26_player_blueprint.json`)와
쓰기 감사(`nba2k26_blueprint_writability_audit.json`, `write_readback_ok`)에서 가져왔다.

| key | 오프셋 | 컨테이너 | 비트 |
|---|---|---|---|
| Birth Year | `+0x10A` | u16 | 0~11 (12비트) |
| Birth Month | `+0x343` | u8 | 4~7 (4비트) |
| Birth Day | `+0x10C` | u8 | 1~5 (5비트) |

- 값 형식(연도 그대로, 월 1~12, 일 1~31)은 **추정**이다. 그래서 `venuelab apply` 는
  쓰기 전에 현재 값을 읽고, 이 범위로 해석되지 않으면 그 선수의 생년월일을 쓰지 않는다.
- 같은 바이트의 다른 비트(예: +0x10C 의 bit 0·6·7)는 유지한다.
- 읽기는 VenueLab 의 `read_process_bytes`(ReadProcessMemory)만 쓴다.
