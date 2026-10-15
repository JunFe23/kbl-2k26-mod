"""VenueLab 일괄 입력 로직 테스트 (가짜 probe, 게임·외부 도구 실행 없음)."""

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import GUARD, make_player, make_team

from kbl2k.venuelab import (
    BATCH_WORKER,
    BATCH_WRITE,
    DURABILITY_FIELDS,
    OWNER_TABLE_CATALOG,
    RATING_FIELD_MAP,
    READ_BYTES,
    VenueLabError,
    WriteOp,
    apply_plan,
    birth_read_requests,
    build_plan,
    check_gate,
    display_to_raw,
    encode_name,
    game_name,
    plan_birth_writes,
    plan_writes,
    raw_to_display,
    team_slots,
)

BASE = 0xBD5BB068
ALL_KEYS = sorted({k for ks in RATING_FIELD_MAP.values() for k in ks})


def fake_model(
    raw=150, jersey_u16=25712, weight=209.0, height=20320, first="Matas", last="Buzelis"
):
    """실제 2K26 모델 구조를 흉내 낸 최소 모델 (docs/2k26-player-fields.md)."""
    reg = []
    off = 0x3E4
    for k in ALL_KEYS:
        if k in ("rating_driving_layup", "rating_post_fade"):
            continue
        reg.append(
            {
                "key": k,
                "type": "rating_u8",
                "offset_int": off,
                "raw_rating": raw,
                "write_enabled": True,
                "value": raw,
            }
        )
        off += 1
    # 실제 기록값: driving_layup 컨테이너 0xED07(raw 180=85), post_fade 0x18ED(raw 99=58)
    reg += [
        {
            "key": "rating_driving_layup",
            "type": "rating_u8_bitfield",
            "offset_int": 0x3E1,
            "start_bit": 6,
            "length": 8,
            "raw_rating": 180,
            "container_u16": 0xED07,
            "write_enabled": True,
        },
        {
            "key": "rating_post_fade",
            "type": "rating_u8_bitfield",
            "offset_int": 0x3E2,
            "start_bit": 6,
            "length": 8,
            "raw_rating": 99,
            "container_u16": 0x18ED,
            "write_enabled": True,
        },
        {
            "key": "jersey",
            "type": "u16_bitfield",
            "offset_int": 0x10D,
            "value": jersey_u16,
            "write_enabled": True,
        },
        {
            "key": "weight",
            "type": "float32",
            "offset_int": 0x100,
            "value": weight,
            "write_enabled": True,
        },
        {
            "key": "appearance_height_cm",
            "type": "ushort_div100",
            "offset_int": 0,
            "address": "0xBEAC5498",
            "value": height,
            "write_enabled": True,
        },
    ]
    return {
        "status": "ok",
        "player": {
            "player_base": hex(BASE),
            "first_name": first,
            "last_name": last,
            "field_registry": reg,
        },
    }


def target(**kw):
    t = {
        "ratings": {},
        "jersey": None,
        "weight_lb": None,
        "height_cm": None,
        "first_name": None,
        "last_name": None,
    }
    t.update(kw)
    return t


# --- 변환 ---


@pytest.mark.parametrize("display, raw", [(25, 0), (85, 180), (58, 99), (99, 222), (120, 222)])
def test_display_raw(display, raw):
    assert display_to_raw(display) == raw
    if display <= 99:
        assert raw_to_display(raw) == display


def test_rating_map_matches_documented_2k26_fields():
    """매핑이 실제 게임에서 확인한 rating 필드 목록과 정확히 일치해야 한다."""
    doc = (Path(__file__).resolve().parents[1] / "docs" / "2k26-player-fields.md").read_text(
        "utf-8"
    )
    documented = set(re.findall(r"`(rating_[a-z_]+)`", doc))
    from kbl2k.venuelab import GAME_MANAGED_FIELDS

    assert documented and set(ALL_KEYS) | set(GAME_MANAGED_FIELDS) == documented
    assert not set(ALL_KEYS) & set(GAME_MANAGED_FIELDS)
    assert len(ALL_KEYS) == 51 and len(DURABILITY_FIELDS) == 16


def test_encode_name():
    b = encode_name("Kim")
    assert len(b) == 40 and b.startswith("Kim".encode("utf-16-le")) and b[6:] == bytes(34)
    with pytest.raises(VenueLabError):
        encode_name("X" * 20)


@pytest.mark.parametrize(
    "kw, expected",
    [
        (dict(name_ko="김낙현", name_en="KIM NAK HYEON", nationality="KR"), ("Nakhyeon", "Kim")),
        (dict(name_ko="이민서", name_en="Lee Min Seo", nationality="KR"), ("Minseo", "Lee")),
        (
            dict(name_ko="데이본 리드", name_en="Davon Reed", player_type="foreign"),
            ("Davon", "Reed"),
        ),
        (dict(name_ko="에디 다니엘", name_en="EDI DANIEL", nationality="KR"), ("Edi", "Daniel")),
        (dict(name_ko="렌즈 아반도", name_en="Rhenz Joseph Abando"), ("Rhenz Joseph", "Abando")),
    ],
)
def test_game_name(kw, expected):
    p = make_player("test-x1", player_type=kw.pop("player_type", "domestic"), **kw)
    n = game_name(p)
    assert (n.first, n.last) == expected and not n.needs_review


def test_game_name_flags_initials_and_uppercase_three_words():
    assert game_name(
        make_player("test-x1", name_ko="김세창", name_en="KIM S C", player_type="domestic")
    ).needs_review
    p = make_player(
        "test-x1",
        name_ko="프레디",
        name_en="MBUYI FREDDY MUTEBA",
        player_type="domestic",
        nationality="CD",
    )
    assert game_name(p).needs_review


def test_game_name_override():
    p = make_player("test-x1", name_en="KIM S C", game_name={"first": "Sechang", "last": "Kim"})
    assert game_name(p) == ("Sechang", "Kim", False, "") or game_name(p).first == "Sechang"


# --- 계획 ---


def test_build_plan_uses_game_roster_order(rules):
    team = make_team(
        players=[copy.deepcopy(GUARD)], game_roster=["test-g1"], nba_slot="Chicago Bulls"
    )
    plan = build_plan([team, make_team("test-b")], rules)
    assert len(plan["teams"]) == 1
    p = plan["teams"][0]["players"][0]
    assert p["jersey"] == 3 and p["weight_lb"] == round(75 * 2.2046226218, 1)
    assert set(p["ratings"]) == set(ALL_KEYS)
    assert all(25 <= v <= 99 for v in p["ratings"].values())


# --- 쓰기 연산 ---


def test_no_ops_when_already_equal():
    m = fake_model(raw=150)
    t = target(
        ratings={k: 75 for k in ALL_KEYS if k not in ("rating_driving_layup", "rating_post_fade")}
    )
    assert plan_writes(m, t) == []


def test_u8_rating_op():
    ops = plan_writes(fake_model(raw=150), target(ratings={"rating_steal": 99}))
    (op,) = ops
    reg = {e["key"]: e for e in fake_model()["player"]["field_registry"]}
    assert op == WriteOp("rating_steal", BASE + reg["rating_steal"]["offset_int"], "u8", 150, 222)


def test_packed_bitfield_matches_real_game_write():
    # 실제 게임 기록: driving_layup 85→99 일 때 컨테이너 0xED07 → 0xF787
    (op,) = plan_writes(fake_model(), target(ratings={"rating_driving_layup": 99}))
    assert op.kind == "bytes" and op.address == BASE + 0x3E1
    assert op.expected == bytes([0x07, 0xED, 0x18])
    assert int.from_bytes(op.new[:2], "little") == 0xF787
    assert op.new[2] == 0x18  # post_fade 상위 비트 보존


def test_packed_both_fields_one_write():
    (op,) = plan_writes(
        fake_model(), target(ratings={"rating_driving_layup": 99, "rating_post_fade": 99})
    )
    v = int.from_bytes(op.new, "little")
    assert (v >> 6) & 0xFF == 222 and (v >> 14) & 0xFF == 222


def test_packed_inconsistent_containers_rejected():
    m = fake_model()
    for e in m["player"]["field_registry"]:
        if e["key"] == "rating_post_fade":
            e["container_u16"] = 0x1800
    with pytest.raises(VenueLabError, match="컨테이너"):
        plan_writes(m, target(ratings={"rating_driving_layup": 99}))


def test_jersey_only_changes_bits_3_to_9():
    (op,) = plan_writes(fake_model(jersey_u16=0x6470), target(jersey=25))
    assert op.kind == "u16" and op.expected == 0x6470
    assert (op.new & 0x3F8) >> 3 == 25 and op.new & ~0x3F8 == 0x6470 & ~0x3F8


def test_weight_and_height_ops():
    ops = {o.label: o for o in plan_writes(fake_model(), target(weight_lb=180.8, height_cm=199.0))}
    assert ops["weight"].kind == "float32" and ops["weight"].new == 180.8
    assert (
        ops["appearance_height_cm"].address == 0xBEAC5498
        and ops["appearance_height_cm"].new == 19900
    )


def test_name_ops_need_read():
    ops = plan_writes(fake_model(), target(first_name="Jameel", last_name="Buzelis"))
    (op,) = ops
    assert op.label == "first_name" and op.needs_read and op.address == BASE + 0x28


def test_unknown_field_and_bad_status():
    with pytest.raises(VenueLabError):
        plan_writes(fake_model(), target(ratings={"rating_nope": 50}))
    with pytest.raises(VenueLabError):
        plan_writes({"status": "process_not_found"}, target())


def test_cli_args():
    assert WriteOp("x", 0x10, "u8", 1, 2).cli_args()[-4:] == [
        "--direct-expected-old-u8",
        "1",
        "--direct-new-u8",
        "2",
    ]
    a = WriteOp("n", 0x10, "bytes", b"\x01", b"\x02").cli_args()
    assert "--allow-memory-write" in a and a[-3:] == ["01", "--direct-new-hex", "02"]


# --- 실행 흐름 ---


def test_gate():
    check_gate(["System", "NBA2K26.exe"])
    with pytest.raises(VenueLabError, match="안티치트"):
        check_gate(["NBA2K26.exe", "EasyAntiCheat.exe"])
    with pytest.raises(VenueLabError, match="실행 중이 아닙니다"):
        check_gate(["System"])


def catalog(display="Chicago Bulls", n=3):
    slots = [
        {"slot": i + 1, "pointer": hex(BASE + i * 1176), "player": {"display_name": f"P{i}"}}
        for i in range(n)
    ]
    return {
        "status": "ok",
        "teams": [
            {"team": {"display": display}, "slots": slots},
            {"team": {"display": "Atlanta Hawks"}, "slots": []},
        ],
    }


def test_team_slots():
    assert len(team_slots(catalog(), "Chicago Bulls")) == 3
    with pytest.raises(VenueLabError, match="찾지 못했습니다"):
        team_slots(catalog(), "Seoul SK")


class FakeProbe:
    """카탈로그·모델·일괄 쓰기를 흉내. 이름 칸은 'Old' 가 들어 있다고 가정."""

    OLD_NAME_HEX = "4f006c0064" + "00" * 35

    def __init__(self, cat):
        self.cat, self.calls, self.batches, self.reads = cat, [], [], []
        # 생년월일 컨테이너: 2004년(+0x10A u16) / 12월(+0x343 bit4~7) / 25일(+0x10C bit1~5)
        self.read_hex = [(0xF000 | 2004).to_bytes(2, "little").hex(), "c3", f"{(25 << 1) | 1:02x}"]

    def __call__(self, args):
        self.calls.append(args)
        if args[0] in (OWNER_TABLE_CATALOG, "--bootstrap-team-slot-roster-catalog"):
            return self.cat
        if args[0] == "--inspect-player-base-roster-model":
            return fake_model(last="Old")
        if args[0] == READ_BYTES:
            self.reads.append(json.loads(args[1]))
            return {"results": list(self.read_hex)}
        if args[0] == BATCH_WRITE:
            ops = json.loads(args[1])
            self.batches.append(ops)
            out = []
            for o in ops:
                if o["needs_read"]:
                    out.append(
                        {"status": "write_readback_ok", "used_expected_old_hex": self.OLD_NAME_HEX}
                    )
                else:
                    out.append({"status": "write_readback_ok"})
            return {"results": out}
        raise AssertionError(args)


def plan1(n=1):
    return {
        "teams": [
            {
                "nba_slot": "Chicago Bulls",
                "players": [
                    dict(target(ratings={"rating_steal": 99}, last_name="Kim"), name_ko=f"선수{i}")
                    for i in range(n)
                ],
            }
        ]
    }


def test_apply_dry_run_never_writes():
    probe = FakeProbe(catalog())
    rep = apply_plan(plan1(), probe, write=False, processes=["NBA2K26.exe"])
    assert not any(c[0] == "--direct-guarded-write" for c in probe.calls)
    assert rep.count("planned") == 1 and rep.count("dry_run") == 2


def test_apply_writes_one_batch_per_player():
    probe = FakeProbe(catalog())
    rep = apply_plan(plan1(), probe, write=True, processes=["NBA2K26.exe"])
    assert len(probe.batches) == 1
    (batch,) = probe.batches
    assert [o["needs_read"] for o in batch] == [False, True]  # steal, last_name
    assert batch[0]["kwargs"]["value_kind"] == "u8" and batch[0]["kwargs"]["new_u8"] == 222
    assert rep.count("write_readback_ok") == 2
    name_ev = [e for e in rep.events if e.get("op", {}).get("label") == "last_name"][0]
    assert name_ev["op"]["expected"] == FakeProbe.OLD_NAME_HEX


FAKE_VENUELAB = """
MEM = {}
def direct_guarded_write(executable, *, address, value_kind, expected_old_hex="", new_hex="", **kw):
    cur = MEM.get(address)
    if value_kind == "bytes":
        exp, new = bytes.fromhex(expected_old_hex), bytes.fromhex(new_hex)
        if cur != exp:
            return {"status": "rejected", "actual_old_hex": cur.hex(" ")}
        MEM[address] = new
        return {"status": "write_readback_ok", "after_hex": new.hex(" ")}
    if cur != kw["expected_old_u8"]:
        return {"status": "rejected"}
    MEM[address] = kw["new_u8"]
    return {"status": "write_readback_ok"}
MEM[0x10] = "Old".encode("utf-16-le") + bytes(34)
MEM[0x50] = "New".encode("utf-16-le") + bytes(34)
MEM[0x20] = 150
"""


def test_batch_worker_runs_against_fake_venuelab(tmp_path):
    """실제 BATCH_WORKER 코드를 가짜 VenueLab 모듈로 실행."""
    from kbl2k.venuelab import op_kwargs

    (tmp_path / "roster_live_memory_probe.py").write_text(FAKE_VENUELAB, "utf-8")
    ops = [
        WriteOp("steal", 0x20, "u8", 150, 222),
        WriteOp("steal_again_stale", 0x20, "u8", 150, 99),  # 이전값 불일치 → 거부
        WriteOp("last_name", 0x10, "bytes", None, encode_name("Kim"), needs_read=True),
        WriteOp("same_name", 0x50, "bytes", None, encode_name("New"), needs_read=True),
    ]
    ops_file, out_file = tmp_path / "ops.json", tmp_path / "out.json"
    ops_file.write_text(
        json.dumps([{"kwargs": op_kwargs(o), "needs_read": o.needs_read} for o in ops])
    )
    subprocess.run(
        [sys.executable, "-c", BATCH_WORKER, str(tmp_path), str(ops_file), str(out_file)],
        check=True,
        cwd=tmp_path,
    )
    res = json.loads(out_file.read_text("utf-8"))
    assert [r["status"] for r in res] == [
        "write_readback_ok",
        "rejected",
        "write_readback_ok",
        "unchanged",
    ]
    assert res[2]["used_expected_old_hex"] == ("Old".encode("utf-16-le") + bytes(34)).hex()


FAKE_READ_VENUELAB = """
MEM = bytes(range(256))
def find_processes(exe):
    return [{"pid": 1}]
def read_process_bytes(pid, address, length):
    if address >= 250:
        return {"ok": False, "error": "unreadable"}
    return {"ok": True, "data": MEM[address:address + length]}
"""


def test_read_worker_runs_against_fake_venuelab(tmp_path):
    """실제 READ_WORKER 코드를 가짜 VenueLab 모듈로 실행(읽기만)."""
    from kbl2k.venuelab import READ_WORKER

    (tmp_path / "roster_live_memory_probe.py").write_text(FAKE_READ_VENUELAB, "utf-8")
    reqs, out_file = tmp_path / "reqs.json", tmp_path / "out.json"
    reqs.write_text(json.dumps([{"address": 0x10, "length": 2}, {"address": 252, "length": 1}]))
    subprocess.run(
        [sys.executable, "-c", READ_WORKER, str(tmp_path), str(reqs), str(out_file)],
        check=True,
        cwd=tmp_path,
    )
    assert json.loads(out_file.read_text("utf-8")) == ["1011", None]


def test_apply_refuses_with_eac():
    with pytest.raises(VenueLabError):
        apply_plan(
            plan1(),
            FakeProbe(catalog()),
            write=True,
            processes=["NBA2K26.exe", "EasyAntiCheat_EOS.exe"],
        )


def test_apply_warns_when_fewer_slots():
    rep = apply_plan(plan1(n=5), FakeProbe(catalog(n=2)), write=False, processes=["NBA2K26.exe"])
    assert rep.count("warning") == 1 and rep.count("planned") == 2


def dup_catalog(idx_a, idx_b):
    base, stride = 0x1000, 5672

    def team(i, who):
        return {
            "team_pointer": hex(base + i * stride),
            "team": {"display": "Chicago Bulls", "abbr": "CHI"},
            "slots": [{"slot": 1, "pointer": hex(BASE), "player": {"display_name": who}}],
        }

    return {
        "status": "ok",
        "owner_tables": {"Team": {"base": hex(base), "stride": stride}},
        "teams": [team(idx_a, "Modern"), team(idx_b, "Classic")],
    }


def test_select_team_prefers_current_nba_index():
    from kbl2k.venuelab import select_team, team_index

    cat = dup_catalog(3, 45)
    entry, decision = select_team(cat, "Chicago Bulls")
    assert team_index(cat, entry) == 3 and "현역" in decision
    assert entry["slots"][0]["player"]["display_name"] == "Modern"


def test_select_team_ambiguous_when_both_current_or_unknown():
    from kbl2k.venuelab import select_team

    with pytest.raises(VenueLabError, match="모호함"):
        select_team(dup_catalog(3, 4), "Chicago Bulls")
    cat = dup_catalog(3, 45)
    del cat["owner_tables"]
    with pytest.raises(VenueLabError, match="모호함"):
        select_team(cat, "Chicago Bulls")


def test_apply_saves_catalog_and_logs_selection(tmp_path):
    path = tmp_path / "cat.json"
    msgs = []
    rep = apply_plan(
        plan1(),
        FakeProbe(catalog()),
        processes=["NBA2K26.exe"],
        catalog_path=path,
        progress=msgs.append,
    )
    assert path.is_file() and len(msgs) == 3
    assert any(e["stage"] == "team" and e["status"] == "selected" for e in rep.events)


def test_read_catalog_falls_back_when_owner_table_unusable():
    from kbl2k.venuelab import read_catalog

    bogus = {"status": "ok", "teams": [{"team": {"display": "Team 0x262CD09E0"}, "slots": []}]}
    good = catalog()
    calls = []

    def probe(args):
        calls.append(args[0])
        return bogus if args[0] == OWNER_TABLE_CATALOG else good

    cat, tried = read_catalog(probe)
    assert cat is good and calls == [OWNER_TABLE_CATALOG, "--bootstrap-team-slot-roster-catalog"]
    assert tried[0]["usable"] is False and tried[1]["usable"] is True


def test_apply_stops_when_no_usable_catalog():
    bogus = {"status": "ok", "teams": [{"team": {"display": "Team 0x1"}, "slots": []}]}
    with pytest.raises(VenueLabError, match="제대로 읽지 못했습니다"):
        apply_plan(plan1(), lambda a: bogus, processes=["NBA2K26.exe"])


def team_entry(display="Chicago Bulls", city="Chicago", nick="Bulls", abbr="CHI", ptr=0x5000):
    return {
        "team_pointer": hex(ptr),
        "team": {"display": display, "city": city, "nickname": nick, "abbr": abbr},
        "slots": [{"slot": 1, "pointer": hex(BASE), "player": {"display_name": "P0"}}],
    }


def test_plan_team_writes_offsets_and_lengths():
    from kbl2k.venuelab import plan_team_writes

    ident = {"city": "Anyang", "name": "Red Boosters", "abbr": "JKJ"}
    ops = {o.label: o for o in plan_team_writes(team_entry(), ident)}
    assert ops["team_name"].address == 0x5000 + 0x2E2 and len(ops["team_name"].new) == 50
    assert ops["team_city"].address == 0x5000 + 0x314 and len(ops["team_city"].new) == 36
    assert ops["team_abbr"].address == 0x5000 + 0x338 and len(ops["team_abbr"].new) == 14
    assert ops["team_name"].new.startswith("Red Boosters".encode("utf-16-le"))
    assert all(o.needs_read for o in ops.values())


def test_plan_team_writes_skips_equal_and_none():
    from kbl2k.venuelab import plan_team_writes

    done = team_entry("Anyang Red Boosters", "Anyang", "Red Boosters", "JKJ")
    assert plan_team_writes(done, {"city": "Anyang", "name": "Red Boosters", "abbr": "JKJ"}) == []
    assert plan_team_writes(team_entry(), None) == []


def test_abbr_too_long_rejected():
    from kbl2k.venuelab import plan_team_writes

    with pytest.raises(VenueLabError):
        plan_team_writes(team_entry(), {"city": "A", "name": "B", "abbr": "TOOLONG"})


def test_renamed_team_found_by_new_name():
    from kbl2k.venuelab import select_team_any, team_display_names

    cat = {
        "status": "ok",
        "teams": [
            team_entry("Anyang Red Boosters", "Anyang", "Red Boosters", "JKJ"),
            team_entry("Atlanta Hawks", "Atlanta", "Hawks", "ATL", 0x6000),
        ],
    }
    plan_team = {
        "nba_slot": "Chicago Bulls",
        "identity": {"city": "Anyang", "name": "Red Boosters", "abbr": "JKJ"},
    }
    entry, decision = select_team_any(cat, team_display_names(plan_team))
    assert entry["team"]["abbr"] == "JKJ" and "Anyang Red Boosters" in decision
    with pytest.raises(VenueLabError):
        select_team_any(cat, ["Chicago Bulls"])


def test_apply_dry_run_includes_team_ops():
    cat = {
        "status": "ok",
        "teams": [team_entry(), team_entry("Atlanta Hawks", "Atlanta", "Hawks", "ATL", 0x6000)],
    }
    plan = plan1()
    plan["teams"][0]["identity"] = {"city": "Anyang", "name": "Red Boosters", "abbr": "JKJ"}
    rep = apply_plan(plan, FakeProbe(cat), processes=["NBA2K26.exe"])
    team_ops = [e for e in rep.events if e.get("stage") == "op" and e.get("slot") == 0]
    assert {e["op"]["label"] for e in team_ops} == {"team_name", "team_city", "team_abbr"}


def test_diff_team_captures_groups_and_decodes_text():
    from kbl2k.venuelab import diff_team_captures

    a = bytearray(64)
    b = bytearray(64)
    a[0:10] = "Bulls".encode("utf-16-le")
    b[0:10] = "Kites".encode("utf-16-le")
    b[40] = 1  # 플래그 하나
    d = diff_team_captures(a.hex(" "), b.hex())
    assert [x["offset"] for x in d] == ["+0x0", "+0x28"]
    assert d[0]["before_text"] == "Bulls" and d[0]["after_text"] == "Kites"
    assert d[1]["length"] == 1 and d[1]["before"] == "00" and d[1]["after"] == "01"


def test_capture_team_uses_selected_pointer():
    from kbl2k.venuelab import capture_team

    calls = []

    def probe(args):
        calls.append(args)
        if args[0] == OWNER_TABLE_CATALOG:
            return {
                "status": "ok",
                "teams": [
                    team_entry(),
                    team_entry("Atlanta Hawks", "Atlanta", "Hawks", "ATL", 0x6000),
                ],
            }
        return {"status": "ok", "raw_hex": "00 01", "sha256": "x"}

    cap = capture_team(probe, ["Chicago Bulls"], "t1", processes=["NBA2K26.exe"])
    assert cap["team_pointer"] == "0x5000" and cap["raw_hex"] == "00 01"
    assert calls[-1][:3] == ["--capture-team-record-state", "--team-pointer", "0x5000"]


def test_alias_finds_relocated_team():
    from kbl2k.venuelab import select_team_any, team_display_names

    cat = {"status": "ok", "teams": [team_entry("Denver Bulls", "Denver", "Bulls", "DEN")]}
    t = {"nba_slot": "Chicago Bulls", "identity": None}
    entry, _ = select_team_any(cat, team_display_names(t, {"Chicago Bulls": ["Denver Bulls"]}))
    assert entry["team"]["city"] == "Denver"


def test_parse_aliases():
    from kbl2k.cli import parse_aliases

    assert parse_aliases(["Chicago Bulls=Denver Bulls", "Atlanta Hawks = X Y"]) == {
        "Chicago Bulls": ["Denver Bulls"],
        "Atlanta Hawks": ["X Y"],
    }
    with pytest.raises(SystemExit):
        parse_aliases(["nope"])


# --- 생년월일 (ADR-0018 분석 2) ---


def test_plan_birth_writes_keeps_other_bits():
    containers = [0xF000 | 2004, 0xC3, (25 << 1) | 1]
    ops, current, problem = plan_birth_writes(BASE, "1996-03-11", containers)
    assert problem == "" and current == {"birth_year": 2004, "birth_month": 12, "birth_day": 25}
    by = {o.label: o for o in ops}
    assert by["birth_year"].kind == "u16" and by["birth_year"].address == BASE + 0x10A
    assert by["birth_year"].new == 0xF000 | 1996
    assert by["birth_month"].kind == "u8" and by["birth_month"].address == BASE + 0x343
    assert by["birth_month"].new == (3 << 4) | 0x03
    assert by["birth_day"].address == BASE + 0x10C and by["birth_day"].new == (11 << 1) | 1


def test_plan_birth_writes_skips_when_already_equal():
    ops, _, problem = plan_birth_writes(BASE, "2004-12-25", [2004, 0xC0, 25 << 1])
    assert ops == [] and problem == ""


def test_plan_birth_writes_refuses_implausible_current():
    ops, current, problem = plan_birth_writes(BASE, "1996-03-11", [2004, 0x00, 25 << 1])
    assert ops == [] and current["birth_month"] == 0 and "birth_month" in problem


def test_birth_read_requests():
    assert birth_read_requests(BASE) == [
        {"address": BASE + 0x10A, "length": 2},
        {"address": BASE + 0x343, "length": 1},
        {"address": BASE + 0x10C, "length": 1},
    ]


def test_apply_writes_birth_date():
    plan = plan1()
    plan["teams"][0]["players"][0]["birth_date"] = "1996-03-11"
    probe = FakeProbe(catalog())
    rep = apply_plan(plan, probe, write=True, processes=["NBA2K26.exe"])
    (batch,) = probe.batches
    labels = [o["kwargs"]["label"] for o in batch]
    assert labels[-3:] == ["birth_year", "birth_month", "birth_day"]
    ev = [e for e in rep.events if e.get("stage") == "birth"][0]
    assert ev["status"] == "checked" and ev["current"]["birth_year"] == 2004


def test_apply_skips_birth_when_format_unexpected():
    plan = plan1()
    plan["teams"][0]["players"][0]["birth_date"] = "1996-03-11"
    probe = FakeProbe(catalog())
    probe.read_hex[1] = "00"  # 월 = 0 → 형식 의심
    rep = apply_plan(plan, probe, write=True, processes=["NBA2K26.exe"])
    (batch,) = probe.batches
    assert not any(o["kwargs"]["label"].startswith("birth") for o in batch)
    assert [e for e in rep.events if e.get("stage") == "birth"][0]["status"] == "skipped"


def test_apply_teams_only_skips_players():
    plan = plan1()
    probe = FakeProbe(catalog())
    rep = apply_plan(plan, probe, write=False, processes=["NBA2K26.exe"], teams_only=True)
    assert not any(c[0] == "--inspect-player-base-roster-model" for c in probe.calls)
    assert rep.count("planned") == 0
