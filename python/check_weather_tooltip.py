"""Guard the weather tooltip's table layout in weather.py.

The tooltip is Pango markup in a monospace font, so alignment is done with
padding. What has to hold: every row of the forecast has its columns at the same
cell offset (across all days), numbers are right-aligned with their heading, a
junk or absurd reading becomes a dash or is clamped instead of widening a column
or crashing the module, and text from wttr.in cannot inject markup.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys
import unittest

REPO_ROOT = pathlib.Path(os.environ.get("REPO_ROOT", "."))
SCRIPT = REPO_ROOT / "Configs" / ".local" / "lib" / "hyde" / "weather.py"

spec = importlib.util.spec_from_file_location("hyde_weather", SCRIPT)
assert spec and spec.loader
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

TAG = re.compile(r"<[^>]+>")


def plain(text: str) -> str:
    return TAG.sub("", text)


def hour(time="900", code="119", c="18", f="64", desc="Cloudy", **chances):
    base = {
        "time": time,
        "weatherCode": code,
        "weatherDesc": [{"value": desc}],
        "tempC": c,
        "tempF": f,
        "chanceofovercast": "50",
        "chanceofrain": "5",
        "chanceofsunshine": "0",
        "chanceofwindy": "1",
        "chanceoffog": "0",
        "chanceoffrost": "0",
        "chanceofsnow": "0",
        "chanceofthunder": "0",
    }
    base.update(chances)
    return base


def day(hourly, date="2026-09-30"):
    return {
        "date": date,
        "maxtempC": "27",
        "maxtempF": "81",
        "mintempC": "9",
        "mintempF": "48",
        "astronomy": [{"sunrise": "07:25 AM", "sunset": "07:06 PM"}],
        "hourly": hourly,
    }


def report(days, **current):
    cur = {
        "temp_C": "24", "temp_F": "75", "FeelsLikeC": "21", "FeelsLikeF": "70",
        "windspeedKmph": "11", "windspeedMiles": "7", "humidity": "42",
        "weatherCode": "119", "weatherDesc": [{"value": "Cloudy "}],
    }
    cur.update(current)
    return {
        "current_condition": [cur],
        "weather": days,
        "nearest_area": [{"areaName": [{"value": "Testville"}], "country": [{"value": "Nowhere"}]}],
    }


class Table(unittest.TestCase):
    def setUp(self):
        w.temp_unit, w.windspeed_unit, w.weather_lang = "c", "km/h", "en"

    def rows(self, days, now=0, n=3):
        """Forecast lines that start with a (possibly padded) hour digit or dash."""
        text = plain(w.build_forecast(report(days), now, n))
        return [ln for ln in text.splitlines() if re.match(r"^\s*(\d|–)", ln)], text

    def test_columns_line_up_across_days_and_rows(self):
        d1 = day([hour("0"), hour("900"), hour("2100", desc="Moderate or heavy rain shower")])
        d2 = day([hour("1200", c="-7", f="19"), hour("1500", chanceofrain="100")], "2026-10-01")
        rows, _ = self.rows([d1, d2])
        offsets = {tuple(m.end() for m in re.finditer(r"\d+%", ln)) for ln in rows}  # numbers are right-aligned: compare where they end
        self.assertEqual(len(offsets), 1, "percent columns differ between rows")
        ends = {re.search(r"[\d–]+°C", ln).end() for ln in rows}
        self.assertEqual(len(ends), 1, "temperature column is not right-aligned")

    def test_hours_have_no_leading_zero_and_align_right(self):
        rows, _ = self.rows([day([hour("0"), hour("300"), hour("1200"), hour("2100")])])
        firsts = [re.match(r"^(\s*)(\d+)", ln) for ln in rows]
        self.assertEqual([m.group(2) for m in firsts], ["0", "3", "12", "21"])
        self.assertEqual(len({len(m.group(1)) + len(m.group(2)) for m in firsts}), 1)

    def test_headings_end_where_their_numbers_end(self):
        _, text = self.rows([day([hour("900", c="-7")])])
        lines = text.splitlines()
        head = next(ln for ln in lines if "Temp" in ln)
        row = next(ln for ln in lines if "-7°C" in ln)
        self.assertEqual(head.index("Temp") + len("Temp"), row.index("°C") + len("°C"))
        self.assertEqual(head.index("Rain") + len("Rain"), row.index("5%") + len("5%"))

    def test_temperatures_are_clamped(self):
        rows, _ = self.rows([day([hour(c="150"), hour(c="-200"), hour(c="12.6")])])
        joined = "\n".join(rows)
        self.assertIn("99°C", joined)
        self.assertIn("-99°C", joined)
        self.assertIn("13°C", joined)
        self.assertNotIn("150", joined)

    def test_fahrenheit_uses_f_fields_and_wider_range(self):
        w.temp_unit = "f"
        rows, _ = self.rows([day([hour(f="101"), hour(f="250"), hour(f="-5")])])
        joined = "\n".join(rows)
        self.assertIn("101°F", joined)
        self.assertIn("199°F", joined)
        self.assertNotIn("°C", joined)
        ends = {re.search(r"-?\d+°F", ln).end() for ln in rows}
        self.assertEqual(len(ends), 1)

    def test_percentages_are_clamped(self):
        rows, _ = self.rows([day([hour(chanceofrain="150", chanceofwindy="-5")])])
        self.assertIn("100%", rows[0])
        self.assertNotIn("150", rows[0])
        self.assertNotIn("-5", rows[0])

    def test_junk_values_become_dashes_not_crashes(self):
        for junk in ("abc", "", None, "nan", "inf", "-inf", [], {}, True, "12abc"):
            with self.subTest(junk=junk):
                h = hour(c=junk, f=junk, chanceofrain=junk, chanceofovercast=junk)
                rows, _ = self.rows([day([h])])
                self.assertEqual(len(rows), 1)
                self.assertIn("–", rows[0])

    def test_missing_fields_do_not_crash(self):
        bare = {"time": "900"}
        for d in (day([bare]), day([]), {"date": "x"}, {}, day("not a list"), day([None, 5, "x"])):
            with self.subTest(day=d):
                w.build_forecast(report([d]), 0, 3)
        d = day([hour()])
        del d["astronomy"]
        self.assertIn("🌅 <b>–</b>", w.build_forecast(report([d]), 0, 3))
        d["astronomy"] = [{"sunrise": "garbage"}]
        w.build_forecast(report([d]), 0, 3)  # unparsable time passes through, no crash

    def test_empty_and_short_day_lists(self):
        self.assertEqual(w.build_forecast(report([]), 0, 3), "")
        self.assertEqual(w.build_forecast(report([day([hour()])]), 0, 0), "")
        text = w.build_forecast(report([day([hour()])]), 0, 3)  # asks for 3, has 1
        self.assertEqual(text.count("<b>Today"), 1)
        self.assertNotIn("Tomorrow", text)

    def test_only_requested_days_are_shown(self):
        days = [day([hour()], f"2026-10-0{i}") for i in range(1, 4)]
        text = w.build_forecast(report(days), 0, 2)
        self.assertIn("Tomorrow, 2026-10-02", text)
        self.assertNotIn("2026-10-03", text)

    def test_past_slots_of_today_are_dropped_at_the_boundary(self):
        today = day([hour(t) for t in ("0", "600", "900", "1200", "1500")])
        tomorrow = day([hour("0"), hour("300")], "2026-10-01")
        rows, _ = self.rows([today, tomorrow], now=11)
        # 9 is exactly now-2 -> kept; 6 and 0 dropped; tomorrow untouched
        self.assertEqual([ln.split()[0] for ln in rows], ["9", "12", "15", "0", "3"])
        rows, _ = self.rows([today, tomorrow], now=0)
        self.assertEqual(len(rows), 7)
        rows, _ = self.rows([today, tomorrow], now=23)
        self.assertEqual([ln.split()[0] for ln in rows], ["0", "3"])

    def test_unparsable_slot_time_is_shown_with_a_dash_not_dropped(self):
        for t in ("2500", "-100", "abc", None, "", "2400"):
            with self.subTest(t=t):
                rows, _ = self.rows([day([hour(t)])], now=20)
                self.assertEqual(len(rows), 1)
                self.assertTrue(rows[0].lstrip().startswith("–"))

    def test_markup_in_descriptions_is_escaped(self):
        text = w.build_forecast(report([day([hour(desc="Rain & <b>hail</b>")])]), 0, 3)
        self.assertIn("Rain &amp; &lt;b&gt;hail&lt;/b&gt;", text)
        facts = w.build_facts(report([day([hour()])], weatherDesc=[{"value": "<i>x</i> & y"}]))
        self.assertIn("&lt;i&gt;x&lt;/i&gt; &amp; y", facts)

    def test_wide_characters_count_two_cells(self):
        rows, _ = self.rows([day([hour(desc="晴れ"), hour("1200", desc="Clear")])])
        starts = {w._width(ln[: ln.index("%") - 3]) for ln in rows}  # up to the clouds number
        self.assertEqual(len(starts), 1)
        self.assertEqual(w._width("晴れ"), 4)
        self.assertEqual(w._width("é"), 1)  # combining accent

    def test_rare_events_have_no_commas_and_three_spaces_between(self):
        h = hour(chanceoffog="57", chanceofthunder="3", chanceoffrost="0")
        rows, text = self.rows([day([h])])
        self.assertIn("Fog 57%   Thunder 3%", rows[0])
        self.assertNotIn(",", rows[0])

    def test_rare_event_junk_is_ignored(self):
        rows, _ = self.rows([day([hour(chanceoffog="abc", chanceofsnow="nan")])])
        self.assertNotIn("Fog", rows[0])
        self.assertNotIn("Snow", rows[0])

    def test_no_trailing_whitespace_on_table_lines(self):
        _, text = self.rows([day([hour(), hour("1200", chanceoffog="9")])])
        for ln in text.splitlines():
            self.assertEqual(ln, ln.rstrip())

    def test_summary_line_is_bold_and_unit_aware(self):
        text = w.build_forecast(report([day([hour()])]), 0, 3)
        self.assertIn("<b>Today, 2026-09-30</b>", text)
        self.assertIn("⬆️ <b>27°C</b> ⬇️ <b>9°C</b> 🌅 <b>07:25</b> 🌇 <b>19:06</b>", text)
        w.temp_unit = "f"
        self.assertIn("⬆️ <b>81°F</b> ⬇️ <b>48°F</b>", w.build_forecast(report([day([hour()])]), 0, 3))


class Facts(unittest.TestCase):
    def setUp(self):
        w.temp_unit, w.windspeed_unit, w.weather_lang = "c", "km/h", "en"

    def test_values_start_in_one_column_and_labels_have_no_colon(self):
        lines = w.build_facts(report([])).splitlines()[1:]
        parsed = [re.match(r"(\S+(?: \S+)*) {3,}(\S.*)$", ln) for ln in lines]
        self.assertTrue(all(parsed), lines)
        self.assertEqual(len({m.start(2) for m in parsed}), 1)
        self.assertEqual([m.group(1) for m in parsed], ["Feels like", "Location", "Wind", "Humidity"])

    def test_headline_has_single_spaces(self):
        self.assertEqual(w.build_facts(report([])).splitlines()[0], "<b>Cloudy 24°C</b>")

    def test_wind_has_a_space_before_the_unit(self):
        self.assertIn("11 km/h", w.build_facts(report([])))
        w.windspeed_unit = "mph"
        self.assertIn("7 mph", w.build_facts(report([])))

    def test_missing_or_junk_fields(self):
        facts = w.build_facts(report([], humidity=None, windspeedKmph="x", FeelsLikeC="??"))
        self.assertIn("Humidity     –", facts)
        self.assertIn("Wind         –", facts)
        self.assertIn("Feels like   –", facts)
        w.temp_unit = "f"
        cur = report([])["current_condition"][0]
        del cur["FeelsLikeF"]
        w.get_feels_like(cur)  # no KeyError

    def test_humidity_boundaries(self):
        for raw, shown in (("0", "0%"), ("100", "100%"), ("101", "100%"), ("-1", "0%")):
            with self.subTest(raw=raw):
                self.assertIn(f"  {shown}", w.build_facts(report([], humidity=raw)))


if __name__ == "__main__":
    unittest.main()
