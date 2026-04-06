from __future__ import annotations

"""Tests for the Bushnell Shot Analysis CSV parser."""

from datetime import date
from decimal import Decimal

import pytest

from app.parsers.bushnell_sa import BushnellShotAnalysisParser

SAMPLE_SA_CSV = """Shot Analysis
7i,
,Date,Time,Carry,unk1,Apex,Offline,unk2,Landing Angle,unk3,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,unk4,Smash Factor,Attack Angle,Club Path,Face to Path,unk5,Dynamic Loft,unk6,unk7,unk8,Face Angle
1,03-18-2026,10:30:00,155.2,,82.1,3.4 L,,42.1,,107.2,22.5,1.2 L,168 R,5220 R,5224,3.1 R,,1.43,2.3 UP,2.1 O-I,1.3 L,,24.1,,,,0.8 L
2,03-18-2026,10:31:00,162.1,,85.6,1.2 R,,43.5,,109.8,21.3,0.5 R,105 L,4945 L,4950,1.2 L,,1.48,1.8 UP,0.3 I-O,0.2 R,,23.2,,,,0.5 R
3,03-18-2026,10:32:00,148.9,,78.3,8.1 L,,40.2,,105.1,24.1,2.8 L,458 R,5572 R,5580,5.2 R,,1.42,3.1 UP,4.2 O-I,2.1 L,,25.8,,,,2.1 L
Average,,,155.40,,82.00,,,41.93,,107.37,22.63,,,,5251.33,,,1.44,,,,,,,,
3h,
,Date,Time,Carry,unk1,Apex,Offline,unk2,Landing Angle,unk3,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,unk4,Smash Factor,Attack Angle,Club Path,Face to Path,unk5,Dynamic Loft,unk6,unk7,unk8,Face Angle
1,03-18-2026,10:45:00,185.9,,92.3,2.1 L,,38.2,,128.2,16.5,0.8 L,188 R,4670 R,4674,2.3 R,,1.42,1.2 UP,1.5 O-I,0.7 L,,18.1,,,,0.3 L
2,03-18-2026,10:46:00,192.4,,98.1,3.2 R,,40.1,,130.8,21.0,1.1 R,120 L,5220 L,5224,0.5 L,,1.47,0.5 UP,0.8 I-O,0.3 R,,22.3,,,,1.2 R
Average,,,189.15,,95.20,,,39.15,,129.50,18.75,,,,4949.00,,,1.45,,,,,,,,
"""

MULTI_DATE_SA_CSV = """Shot Analysis
7i,
,Date,Time,Carry,unk1,Apex,Offline,unk2,Landing Angle,unk3,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,unk4,Smash Factor,Attack Angle,Club Path,Face to Path,unk5,Dynamic Loft,unk6,unk7,unk8,Face Angle
1,03-18-2026,10:30:00,155.2,,82.1,3.4 L,,42.1,,107.2,22.5,1.2 L,168 R,5220 R,5224,3.1 R,,1.43,2.3 UP,2.1 O-I,1.3 L,,24.1,,,,0.8 L
2,03-19-2026,10:31:00,162.1,,85.6,1.2 R,,43.5,,109.8,21.3,0.5 R,105 L,4945 L,4950,1.2 L,,1.48,1.8 UP,0.3 I-O,0.2 R,,23.2,,,,0.5 R
"""


class TestBushnellSAParser:
    """Test suite for BushnellShotAnalysisParser."""

    def setup_method(self) -> None:
        self.parser = BushnellShotAnalysisParser()

    # ── Detection ──

    def test_detect_valid(self) -> None:
        assert self.parser.detect(SAMPLE_SA_CSV) is True

    def test_detect_invalid_dr_format(self) -> None:
        assert self.parser.detect("Dates,03-18-2026,Place,,Player,,") is False

    def test_detect_invalid_session_format(self) -> None:
        assert self.parser.detect("user@example.com\n7i, \n") is False

    def test_detect_empty(self) -> None:
        assert self.parser.detect("") is False

    # ── Session structure ──

    def test_parse_returns_single_session_same_date(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        assert len(sessions) == 1

    def test_parse_groups_by_date(self) -> None:
        sessions = self.parser.parse(MULTI_DATE_SA_CSV, "test.csv")
        assert len(sessions) == 2

    def test_session_metadata(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        s = sessions[0]
        assert s.source_format == "bushnell_sa"
        assert s.session_date == date(2026, 3, 18)
        assert "test.csv" in s.source_file

    # ── Shot count ──

    def test_shot_count_skips_average(self) -> None:
        """Should parse 5 data rows, skipping Average rows."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        assert len(sessions[0].shots) == 5

    # ── Club normalization ──

    def test_club_normalization(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        clubs = {s.club_name for s in sessions[0].shots}
        assert "7 Iron" in clubs
        assert "3 Hybrid" in clubs
        assert "7i" not in clubs
        assert "3h" not in clubs

    # ── Numeric fields ──

    def test_ball_speed(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.ball_speed_mph == Decimal("107.2")

    def test_carry_distance(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.carry_yards == Decimal("155.2")

    def test_launch_angle(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.launch_angle_deg == Decimal("22.5")

    def test_apex(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.apex_feet == Decimal("82.1")

    def test_spin_rate(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.spin_rate_rpm == 5224

    def test_smash_factor(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.smash_factor == Decimal("1.43")

    def test_landing_angle(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.landing_angle_deg == Decimal("42.1")

    # ── Suffix direction parsing ──

    def test_offline_left(self) -> None:
        """'3.4 L' should parse to -3.4 (left of target)."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.offline_yards == Decimal("-3.4")

    def test_offline_right(self) -> None:
        """'1.2 R' should parse to 1.2 (right of target)."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[1]
        assert shot.offline_yards == Decimal("1.2")

    def test_launch_direction_left(self) -> None:
        """'1.2 L' should parse to -1.2."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.launch_direction_deg == Decimal("-1.2")

    def test_launch_direction_right(self) -> None:
        """'0.5 R' should parse to 0.5."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[1]
        assert shot.launch_direction_deg == Decimal("0.5")

    def test_attack_angle_up(self) -> None:
        """'2.3 UP' → 2.3 (positive = hitting up, standard golf convention)."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.attack_angle_deg == Decimal("2.3")

    def test_club_path_out_to_in(self) -> None:
        """'2.1 O-I' should parse to -2.1 (out-to-in is negative)."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.club_path_deg == Decimal("-2.1")

    def test_club_path_in_to_out(self) -> None:
        """'0.3 I-O' should parse to 0.3 (in-to-out is positive)."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[1]
        assert shot.club_path_deg == Decimal("0.3")

    def test_face_angle_left(self) -> None:
        """'0.8 L' should parse to -0.8."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.face_angle_deg == Decimal("-0.8")

    def test_face_angle_right(self) -> None:
        """'0.5 R' should parse to 0.5."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[1]
        assert shot.face_angle_deg == Decimal("0.5")

    # ── Spin axis sign convention ──

    def test_spin_axis_right(self) -> None:
        """'3.1 R' with left_negative=False: R grouped with right_dirs → -number.
        Matches PWA convention."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.spin_axis_deg == Decimal("-3.1")

    def test_spin_axis_left(self) -> None:
        """'1.2 L' with left_negative=False: L grouped with left_dirs → +number.
        Matches PWA convention."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[1]
        assert shot.spin_axis_deg == Decimal("1.2")

    # ── Club speed should NOT be extracted ──

    def test_no_club_speed_in_sa_format(self) -> None:
        """Shot Analysis format does not include club speed."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        for shot in sessions[0].shots:
            assert shot.club_speed_mph is None

    # ── Dynamic loft and face-to-path ──

    def test_dynamic_loft(self) -> None:
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.dynamic_loft_deg == Decimal("24.1")

    def test_face_to_path(self) -> None:
        """'1.3 L' should parse to -1.3."""
        sessions = self.parser.parse(SAMPLE_SA_CSV, "test.csv")
        shot = sessions[0].shots[0]
        assert shot.face_to_path_deg == Decimal("-1.3")

    # ── Edge cases ──

    def test_parse_empty(self) -> None:
        assert self.parser.parse("", "empty.csv") == []

    def test_parse_header_only(self) -> None:
        content = "Shot Analysis\n7i,\n,Date,Time,Carry\n"
        result = self.parser.parse(content, "header.csv")
        assert result == []

    def test_zero_carry_filtered_out(self) -> None:
        """Shots with carry <= 0 should be skipped."""
        content = """Shot Analysis
7i,
,Date,Time,Carry,unk1,Apex,Offline,unk2,Landing Angle,unk3,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,unk4,Smash Factor,Attack Angle,Club Path
1,03-18-2026,10:30:00,0,,0,0,,0,,0,0,0,0,0,0,0,,0,0,0
"""
        result = self.parser.parse(content, "zero.csv")
        assert result == []

    def test_unparseable_date_falls_back_to_today(self) -> None:
        """If the date column can't be parsed, fall back to today's date."""
        content = """Shot Analysis
7i,
,Date,Time,Carry,unk1,Apex,Offline,unk2,Landing Angle,unk3,Ball Speed,Launch Angle,Launch Direction,Side Spin,Back Spin,Spin Rate,Spin Axis,unk4,Smash Factor,Attack Angle,Club Path,Face to Path,unk5,Dynamic Loft,unk6,unk7,unk8,Face Angle
1,BADDATE,10:30:00,155.2,,82.1,3.4 L,,42.1,,107.2,22.5,1.2 L,168 R,5220 R,5224,3.1 R,,1.43,2.3 UP,2.1 O-I,1.3 L,,24.1,,,,0.8 L
"""
        result = self.parser.parse(content, "baddate.csv")
        assert len(result) == 1
        assert result[0].session_date == date.today()
        assert len(result[0].shots) == 1
