"""MyNBA 이전 도시 이름 쓰기 (가짜 데이터)."""

import pytest

from kbl2k.venuelab import (
    CITY_NAME_OFFSET,
    VenueLabError,
    city_name,
    encode_city_name,
    plan_city_write,
)

CITY_PTR = 0xC7FD2F60
CITY_ID = bytes.fromhex("99 00 ed 01 53 1e 4c 0f 24 62 13 38 7b 8a 65 f2")  # 도시 레코드 +0x38


def city_raw(name=b"Virginia Beach"):
    b = bytearray(0x80)
    b[0:6] = "VIR".encode("utf-16-le")
    b[CITY_NAME_OFFSET : CITY_NAME_OFFSET + len(name)] = name
    b[0x38:0x48] = CITY_ID
    return bytes(b)


def team_raw(city_id=CITY_ID[8:] + CITY_ID[:8]):
    b = bytearray(5672)
    b[0xE98:0xEA8] = city_id
    b[0xFD0:0xFD8] = CITY_PTR.to_bytes(8, "little")
    return bytes(b)


def test_plan_city_write():
    op = plan_city_write(team_raw(), city_raw(), "Anyang")
    assert op.address == CITY_PTR + 0x0E and op.kind == "bytes"
    assert op.expected == b"Virginia Beach\0\0\0\0" and op.new == b"Anyang" + bytes(12)
    assert city_name(city_raw()) == "Virginia Beach"


def test_plan_city_write_unchanged():
    assert plan_city_write(team_raw(), city_raw(b"Anyang"), "Anyang") is None


def test_plan_city_write_refuses_id_mismatch_or_not_relocated():
    with pytest.raises(VenueLabError):
        plan_city_write(team_raw(city_id=bytes(16)), city_raw(), "Anyang")
    with pytest.raises(VenueLabError):
        plan_city_write(team_raw(city_id=CITY_ID), city_raw(), "Anyang")  # 순서 반대 아님


def test_encode_city_name_limits():
    with pytest.raises(VenueLabError):
        encode_city_name("안양")
    with pytest.raises(VenueLabError):
        encode_city_name("A" * 18)
    assert len(encode_city_name("Seoul")) == 18
