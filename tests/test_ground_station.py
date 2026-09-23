"""Offline regressions for actual legacy v3 methods, using synthetic data only."""

import csv
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from ground_station.ground_station_v3 import MAX_POINTS, classify_fix_quality, haversine_m
from ground_station.offline_replay import ReplayStation, replay


def payload(packet=1, altitude=100.0, latitude=0.0, longitude=0.0):
    return (
        f"PKT:{packet},LAT:{latitude:.6f},LON:{longitude:.6f},"
        f"ALT:{altitude:.1f},SAT:10,HDOP:0.90,SPD:0.0"
    )


class GroundStationTests(unittest.TestCase):
    def setUp(self):
        self.station = ReplayStation()

    def send(self, packet=1, altitude=100.0, latitude=0.0, longitude=0.0):
        self.station.handle_line(
            f"DATA,{payload(packet, altitude, latitude, longitude)},RSSI:-50"
        )

    def test_fixed_payload_units(self):
        item = self.station.parse_payload(payload(12, 123.4))
        self.assertTrue(item.has_fix)
        self.assertEqual(item.packet, 12)
        self.assertEqual(item.altitude_m, 123.4)
        self.assertEqual(item.satellites, 10)
        self.assertEqual(item.hdop, 0.9)
        self.assertEqual(item.speed_kmh, 0.0)

    def test_single_line_receiver(self):
        self.send()
        self.assertEqual(self.station.received, 1)
        self.assertEqual(self.station.rssis, [-50])
        self.assertIsNone(self.station.pending)

    def test_two_line_receiver_waits_for_rssi(self):
        self.station.handle_line("Telemetry: " + payload(2))
        self.assertEqual(self.station.received, 0)
        self.station.handle_line("LoRa RSSI: -61 dBm")
        self.assertEqual(self.station.received, 1)
        self.assertEqual(self.station.last_packet, 2)
        self.assertEqual(self.station.rssis, [-61])
        self.assertIsNone(self.station.pending)

    def test_startup_noise_and_unpaired_rssi_are_ignored(self):
        for line in ("Ground station ready", "", "ERROR: radio", "LoRa RSSI: -51 dBm"):
            self.station.handle_line(line)
        self.assertEqual(self.station.received, 0)

    def test_missing_fields_do_not_parse(self):
        self.assertIsNone(self.station.parse_payload("PKT:1,LAT:0.0,LON:0.0"))
        self.assertIsNone(self.station.parse_payload("not telemetry"))

    def test_no_fix_before_first_position(self):
        self.station.handle_line("DATA,PKT:0,NO_FIX,SAT:1,RSSI:-70")
        self.assertEqual(self.station.received, 1)
        self.assertFalse(self.station.using_last_known)
        self.assertIsNone(self.station.current_position)
        self.assertEqual(self.station.vars["position"].get(), "No GPS fix yet")

    def test_no_fix_retains_last_known_position_and_altitude(self):
        self.send(1, 100.0, 0.001, 0.002)
        self.station.handle_line("DATA,PKT:2,NO_FIX,SAT:2,RSSI:-60")
        self.assertTrue(self.station.using_last_known)
        self.assertEqual(self.station.current_position, (0.001, 0.002))
        self.assertEqual(self.station.smoothed_absolute_altitude, 100.0)
        self.assertEqual(len(self.station.latitudes), 1)
        self.assertIn("LAST KNOWN", self.station.vars["fix_quality"].get())

    def test_recovered_fix_replaces_last_known(self):
        self.send(1)
        self.station.handle_line("DATA,PKT:2,NO_FIX,SAT:0,RSSI:-60")
        self.send(3, latitude=0.003, longitude=0.004)
        self.assertFalse(self.station.using_last_known)
        self.assertEqual(self.station.current_position, (0.003, 0.004))

    def test_forward_sequence_gap_loss(self):
        self.send(10)
        self.send(13)
        self.assertEqual(self.station.received, 2)
        self.assertEqual(self.station.missed, 2)
        self.assertEqual(self.station.vars["loss"].get(), "50.00% (2 missed)")

    def test_median_and_ema_smoothing(self):
        self.assertEqual(self.station.smooth_altitude(100.0), (100.0, 0.0))
        self.assertEqual(self.station.smooth_altitude(104.0), (100.5, 0.5))
        self.assertEqual(self.station.smooth_altitude(102.0), (100.875, 0.875))

    def test_fix_quality_thresholds(self):
        cases = [(10, 0.9, "EXCELLENT"), (6, 2.0, "GOOD"),
                 (4, 5.0, "FAIR"), (3, 1.0, "POOR"), (0, None, "UNKNOWN")]
        for satellites, hdop, expected in cases:
            with self.subTest(satellites=satellites, hdop=hdop):
                self.assertEqual(classify_fix_quality(satellites, hdop), expected)

    def test_haversine_synthetic_distance(self):
        self.assertEqual(haversine_m(0.0, 0.0, 0.0, 0.0), 0.0)
        self.assertAlmostEqual(haversine_m(0.0, 0.0, 0.0, 1.0), 111194.9266, places=3)

    def test_plot_histories_are_bounded(self):
        for packet in range(MAX_POINTS + 5):
            self.send(packet)
        self.assertEqual(self.station.received, MAX_POINTS + 5)
        for history in (self.station.alt_times, self.station.relative_altitudes,
                        self.station.rssi_times, self.station.rssis,
                        self.station.latitudes, self.station.longitudes):
            self.assertEqual(len(history), MAX_POINTS)

    def test_csv_distinguishes_raw_missing_from_retained_position(self):
        stream = io.StringIO()
        self.station.writer = csv.writer(stream)
        self.station.log_file = stream
        with patch("ground_station.ground_station_v3.time.monotonic", return_value=1.0):
            self.send(1, latitude=0.001, longitude=0.002)
        with patch("ground_station.ground_station_v3.time.monotonic", return_value=3.0):
            self.station.handle_line("DATA,PKT:2,NO_FIX,SAT:0,RSSI:-60")
        rows = list(csv.reader(io.StringIO(stream.getvalue())))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[1]), 19)
        self.assertEqual(rows[1][2:5], ["", "", ""])
        self.assertEqual(rows[1][5:7], ["0.001", "0.002"])
        self.assertEqual(rows[1][13:17], ["False", "True", "LAST KNOWN", "2.000"])

    def test_synthetic_fixture_end_to_end(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "synthetic_packets.txt"
        station = replay(path)
        self.assertEqual(station.received, 6)
        self.assertEqual(station.missed, 1)
        self.assertEqual(station.vars["loss"].get(), "14.29% (1 missed)")
        self.assertTrue(station.using_last_known)

    def test_documented_legacy_parser_is_permissive(self):
        # Characterization, not endorsement: the legacy regex uses search and
        # does not check coordinate bounds or reject unrelated suffix text.
        item = self.station.parse_payload("prefix " + payload(latitude=91.0) + " suffix")
        self.assertEqual(item.latitude, 91.0)

    def test_documented_legacy_duplicates_are_counted(self):
        self.send(10)
        self.send(10)
        self.assertEqual(self.station.received, 2)
        self.assertEqual(self.station.missed, 0)


if __name__ == "__main__":
    unittest.main()
