from __future__ import annotations

import struct
from dataclasses import FrozenInstanceError

import pytest

from internal_classes import Color, Shape


class TestColor:
    def test_default_values(self):
        c = Color()
        assert c.r == 0
        assert c.g == 0
        assert c.b == 0
        assert c.a == 255

    def test_custom_values(self):
        c = Color(255, 128, 64, 200)
        assert c.r == 255
        assert c.g == 128
        assert c.b == 64
        assert c.a == 200

    def test_frozen_cannot_modify(self):
        c = Color(1, 2, 3, 4)
        with pytest.raises(FrozenInstanceError):
            c.r = 10

    def test_post_init_validates_negative(self):
        with pytest.raises(ValueError, match="Color.r"):
            Color(-1, 0, 0, 0)

    def test_post_init_validates_overflow(self):
        with pytest.raises(ValueError, match="Color.g"):
            Color(0, 256, 0, 0)

    def test_post_init_validates_non_int(self):
        with pytest.raises(ValueError, match="Color.b"):
            Color(0, 0, "hello", 0)

    def test_get_struct(self):
        c = Color(1, 2, 3, 4)
        packed = c.get_struct()
        assert packed == struct.pack("BBBB", 1, 2, 3, 4)
        assert len(packed) == 4

    def test_equality(self):
        assert Color(255, 0, 0, 255) == Color(255, 0, 0, 255)
        assert Color(255, 0, 0, 255) != Color(255, 0, 0, 128)


class TestShape:
    def test_basic_shape(self):
        color = Color(255, 0, 0, 255)
        s = Shape(
            type_id=16, x=50, y=50, w=30, h=20, rot_deg=45,
            color=color, is_mask=False,
        )
        assert s.type_id == 16
        assert s.x == 50
        assert s.y == 50
        assert s.w == 30
        assert s.h == 20
        assert s.rot_deg == 45
        assert s.color == color
        assert s.is_mask is False

    def test_frozen_cannot_modify(self):
        s = Shape(1, 0, 0, 0, 0, 0, Color(), False)
        with pytest.raises(FrozenInstanceError):
            s.x = 100

    def test_frozen_color_cannot_modify(self):
        s = Shape(1, 0, 0, 0, 0, 0, Color(1, 2, 3, 4), False)
        with pytest.raises(FrozenInstanceError):
            s.color.r = 100

    def test_equality(self):
        c = Color(255, 0, 0, 255)
        s1 = Shape(16, 50, 50, 30, 20, 45, c, False)
        s2 = Shape(16, 50, 50, 30, 20, 45, c, False)
        assert s1 == s2

    def test_repr(self):
        s = Shape(1, 0, 0, 10, 10, 0, Color(), False)
        r = repr(s)
        assert "Shape" in r
        assert "type_id=1" in r
