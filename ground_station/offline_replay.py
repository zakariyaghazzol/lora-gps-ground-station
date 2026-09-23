"""Replay serial text through the unchanged v3 logic without Tk or hardware.

This adapter supplies in-memory replacements for GUI labels and plotting.
It is a testing/showcase utility, not a second implementation of the protocol.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from pathlib import Path

from .ground_station_v3 import ALTITUDE_MEDIAN_WINDOW, GroundStation


class MemoryValue:
    """The subset of tkinter.StringVar used by the data-processing methods."""

    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class ReplayStation:
    """Run the original methods with no window, serial port, or log file."""

    handle_line = GroundStation.handle_line
    parse_payload = GroundStation.parse_payload
    from_match = staticmethod(GroundStation.from_match)
    smooth_altitude = GroundStation.smooth_altitude
    commit = GroundStation.commit

    def __init__(self) -> None:
        self.pending = None
        self.last_packet = None
        self.received = 0
        self.missed = 0
        self.last_rx = None
        self.start_position = None
        self.current_position = None
        self.last_valid = None
        self.last_fix_monotonic = None
        self.using_last_known = False
        self.last_distance_m = None
        self.altitude_window = deque(maxlen=ALTITUDE_MEDIAN_WINDOW)
        self.smoothed_absolute_altitude = None
        self.altitude_baseline = None
        self.current_relative_altitude = None
        self.max_relative_altitude = None
        self.alt_times = []
        self.relative_altitudes = []
        self.rssi_times = []
        self.rssis = []
        self.latitudes = []
        self.longitudes = []
        self.vars = defaultdict(MemoryValue)
        self.writer = None
        self.log_file = None

    def redraw_plots(self) -> None:
        """Plotting is intentionally disabled in offline validation."""


def replay(path: Path) -> ReplayStation:
    station = ReplayStation()
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip() and not line.lstrip().startswith("#"):
                station.handle_line(line.strip())
    return station


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples" / "synthetic_packets.txt",
        help="Serial-text fixture (default: clearly labeled synthetic example).",
    )
    args = parser.parse_args()
    station = replay(args.input)
    print(f"Received: {station.received}")
    print(f"Sequence gaps: {station.missed}")
    print(f"Legacy loss estimate: {station.vars['loss'].get()}")
    print(f"Using last-known position: {station.using_last_known}")
    print("Offline replay only; no serial device, map, or output log opened.")


if __name__ == "__main__":
    main()
