"""SessionFlags bit decode (irsdk_Flags)."""

from irswitch.iracing.session_flags import FLAG_BITS, decode_session_flags


def test_each_documented_bit_has_a_name() -> None:
    for name, bit in FLAG_BITS.items():
        decoded = decode_session_flags(bit)
        assert name in decoded.names
        assert decoded.leftover == 0


def test_combined_yellow_and_checkered() -> None:
    raw = FLAG_BITS["checkered"] | FLAG_BITS["yellow"]
    decoded = decode_session_flags(raw)
    assert decoded.names == ("checkered", "yellow")
    assert decoded.checkered is True
    assert decoded.yellow is True
    assert decoded.green is False
    assert decoded.leftover == 0


def test_unknown_leftover_ignored() -> None:
    stray = 0x00000001 | 0x00200000  # checkered + unnamed
    decoded = decode_session_flags(stray)
    assert decoded.names == ("checkered",)
    assert decoded.leftover == 0x00200000
    assert decode_session_flags(None).names == ()
    assert decode_session_flags(True).names == ()
