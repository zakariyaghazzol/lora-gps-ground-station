from __future__ import annotations

import csv
import math
import os
import queue
import re
import statistics
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk

import serial
from serial.tools import list_ports
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

APP_TITLE = "LoRa GPS Ground Station v3"
DEFAULT_BAUD = 9600
MAX_POINTS = 600
ALTITUDE_MEDIAN_WINDOW = 5
ALTITUDE_EMA_ALPHA = 0.25

PACKET_RE = re.compile(
    r"PKT:(?P<pkt>\d+),"
    r"(?:LAT:(?P<lat>-?\d+(?:\.\d+)?),"
    r"LON:(?P<lon>-?\d+(?:\.\d+)?),"
    r"ALT:(?P<alt>-?\d+(?:\.\d+)?),"
    r"SAT:(?P<sat>\d+),"
    r"HDOP:(?P<hdop>-?\d+(?:\.\d+)?),"
    r"SPD:(?P<spd>-?\d+(?:\.\d+)?)"
    r"|NO_FIX,SAT:(?P<nofix_sat>\d+))"
)
RSSI_RE = re.compile(r"(?:LoRa\s+)?RSSI:\s*(?P<rssi>-?\d+)")
DATA_RE = re.compile(r"DATA,(?P<payload>PKT:.*?),RSSI:(?P<rssi>-?\d+)\s*$")


@dataclass
class Telemetry:
    packet: int
    timestamp: datetime
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    satellites: int = 0
    hdop: Optional[float] = None
    speed_kmh: Optional[float] = None
    rssi_dbm: Optional[int] = None
    has_fix: bool = False


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(math.sqrt(a))


def classify_fix_quality(satellites: int, hdop: Optional[float]) -> str:
    """Return a readable GPS-quality grade from satellite count and HDOP."""
    if hdop is None:
        return "UNKNOWN"
    if satellites >= 8 and hdop <= 1.2:
        return "EXCELLENT"
    if satellites >= 6 and hdop <= 2.0:
        return "GOOD"
    if satellites >= 4 and hdop <= 5.0:
        return "FAIR"
    return "POOR"


class SerialWorker(threading.Thread):
    def __init__(self, port: str, baud: int, out: queue.Queue, stop: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.out = out
        self.stop = stop
        self.ser: Optional[serial.Serial] = None

    def run(self) -> None:
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.25, write_timeout=1)
            time.sleep(2.0)
            self.out.put(("status", f"Connected to {self.port} at {self.baud} baud"))
            while not self.stop.is_set():
                raw = self.ser.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self.out.put(("line", line))
        except Exception as exc:
            self.out.put(("error", str(exc)))
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.out.put(("disconnected", None))


class GroundStation(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x850")
        self.minsize(1040, 720)

        self.q: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: Optional[SerialWorker] = None
        self.pending: Optional[Telemetry] = None

        self.last_packet: Optional[int] = None
        self.received = 0
        self.missed = 0
        self.last_rx: Optional[float] = None

        self.start_position: Optional[tuple[float, float]] = None
        self.current_position: Optional[tuple[float, float]] = None
        self.last_valid: Optional[Telemetry] = None
        self.last_fix_monotonic: Optional[float] = None
        self.using_last_known = False
        self.last_distance_m: Optional[float] = None

        self.altitude_window: deque[float] = deque(maxlen=ALTITUDE_MEDIAN_WINDOW)
        self.smoothed_absolute_altitude: Optional[float] = None
        self.altitude_baseline: Optional[float] = None
        self.current_relative_altitude: Optional[float] = None
        self.max_relative_altitude: Optional[float] = None

        self.alt_times: list[datetime] = []
        self.relative_altitudes: list[float] = []
        self.rssi_times: list[datetime] = []
        self.rssis: list[int] = []
        self.latitudes: list[float] = []
        self.longitudes: list[float] = []

        self.log_file = None
        self.writer = None
        self.log_path: Optional[Path] = None

        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.status_var = tk.StringVar(value="Disconnected")
        self.vars = {
            name: tk.StringVar(value="—")
            for name in [
                "link",
                "packet",
                "position",
                "fix_quality",
                "relative_altitude",
                "gps_altitude",
                "max_relative_altitude",
                "satellites",
                "hdop",
                "speed",
                "rssi",
                "loss",
                "distance",
                "log",
            ]
        }
        self.vars["link"].set("No packets")
        self.vars["position"].set("No GPS fix yet")
        self.vars["fix_quality"].set("NO FIX")
        self.vars["loss"].set("0.00%")
        self.vars["log"].set("Not logging")

        self._build_ui()
        self.refresh_ports()
        self.after(100, self.process_queue)
        self.after(500, self.update_status_ages)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Port").pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(
            top, textvariable=self.port_var, width=30, state="readonly"
        )
        self.port_combo.pack(side=tk.LEFT, padx=(6, 10))
        ttk.Button(top, text="Refresh", command=self.refresh_ports).pack(side=tk.LEFT)

        ttk.Label(top, text="Baud").pack(side=tk.LEFT, padx=(16, 0))
        ttk.Combobox(
            top,
            textvariable=self.baud_var,
            width=10,
            state="readonly",
            values=("9600", "19200", "38400", "57600", "115200"),
        ).pack(side=tk.LEFT, padx=(6, 10))

        self.connect_btn = ttk.Button(top, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT)
        ttk.Button(top, text="Clear", command=self.clear_session).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Button(top, text="Zero Altitude", command=self.zero_altitude).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Button(top, text="Open Log Folder", command=self.open_log_folder).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Button(top, text="Open Current Location", command=self.open_map).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Label(top, textvariable=self.status_var).pack(side=tk.RIGHT)

        pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        left, right = ttk.Frame(pane), ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)

        metrics = ttk.LabelFrame(left, text="Live Telemetry", padding=10)
        metrics.pack(fill=tk.X)
        rows = [
            ("Link", "link"),
            ("Packet", "packet"),
            ("Position", "position"),
            ("GPS fix quality", "fix_quality"),
            ("Relative altitude", "relative_altitude"),
            ("Smoothed GPS altitude", "gps_altitude"),
            ("Maximum relative altitude", "max_relative_altitude"),
            ("Satellites", "satellites"),
            ("HDOP", "hdop"),
            ("Speed", "speed"),
            ("LoRa RSSI", "rssi"),
            ("Packet loss", "loss"),
            ("Distance from start", "distance"),
            ("CSV log", "log"),
        ]
        for i, (label, key) in enumerate(rows):
            ttk.Label(metrics, text=label).grid(row=i, column=0, sticky="nw", pady=4)
            ttk.Label(
                metrics,
                textvariable=self.vars[key],
                wraplength=285,
                justify=tk.LEFT,
            ).grid(row=i, column=1, sticky="nw", padx=(12, 0), pady=4)
        metrics.columnconfigure(1, weight=1)

        raw_frame = ttk.LabelFrame(left, text="Serial Data", padding=8)
        raw_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.raw = tk.Text(raw_frame, height=18, wrap=tk.NONE, state=tk.DISABLED)
        scroll = ttk.Scrollbar(raw_frame, orient=tk.VERTICAL, command=self.raw.yview)
        self.raw.configure(yscrollcommand=scroll.set)
        self.raw.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        notebook = ttk.Notebook(right)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.alt_tab = ttk.Frame(notebook)
        self.rssi_tab = ttk.Frame(notebook)
        self.track_tab = ttk.Frame(notebook)
        notebook.add(self.alt_tab, text="Relative Altitude")
        notebook.add(self.rssi_tab, text="RSSI")
        notebook.add(self.track_tab, text="GPS Track")

        self.alt_fig = Figure(figsize=(7, 5), dpi=100)
        self.alt_ax = self.alt_fig.add_subplot(111)
        self.alt_canvas = FigureCanvasTkAgg(self.alt_fig, master=self.alt_tab)
        self.alt_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.rssi_fig = Figure(figsize=(7, 5), dpi=100)
        self.rssi_ax = self.rssi_fig.add_subplot(111)
        self.rssi_canvas = FigureCanvasTkAgg(self.rssi_fig, master=self.rssi_tab)
        self.rssi_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.track_fig = Figure(figsize=(7, 5), dpi=100)
        self.track_ax = self.track_fig.add_subplot(111)
        self.track_canvas = FigureCanvasTkAgg(self.track_fig, master=self.track_tab)
        self.track_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.redraw_plots()

    def refresh_ports(self) -> None:
        current_label = self.port_var.get()
        current_device = (
            self.port_map.get(current_label) if hasattr(self, "port_map") else None
        )

        ports = [
            (f"{port.device} — {port.description}", port.device)
            for port in list_ports.comports()
        ]
        self.port_map = dict(ports)
        labels = [item[0] for item in ports]
        self.port_combo["values"] = labels

        restored = next(
            (label for label, device in ports if device == current_device), None
        )
        if restored:
            self.port_var.set(restored)
        else:
            self.port_var.set("")
            if labels:
                self.status_var.set("Select the Uno COM port, then click Connect")
            else:
                self.status_var.set("No serial ports detected")

    def toggle_connection(self) -> None:
        if self.worker and self.worker.is_alive():
            self.disconnect()
        else:
            self.connect()

    def connect(self) -> None:
        label = self.port_var.get()
        if not label:
            messagebox.showerror(APP_TITLE, "No serial port is selected.")
            return

        port = self.port_map.get(label, label.split(" — ")[0])
        baud = int(self.baud_var.get())
        self.stop_event.clear()
        self.worker = SerialWorker(port, baud, self.q, self.stop_event)
        self.worker.start()
        self.connect_btn.config(text="Disconnect")
        self.status_var.set(f"Opening {port}…")

    def disconnect(self) -> None:
        self.stop_event.set()
        self.status_var.set("Disconnecting…")

    def start_log(self) -> None:
        self.close_log()
        folder = Path(__file__).resolve().parent / "telemetry_logs"
        folder.mkdir(exist_ok=True)
        self.log_path = folder / f"session_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self.log_file = self.log_path.open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.log_file)
        self.writer.writerow(
            [
                "computer_time",
                "packet",
                "raw_latitude",
                "raw_longitude",
                "raw_gps_altitude_m",
                "displayed_latitude",
                "displayed_longitude",
                "smoothed_gps_altitude_m",
                "relative_altitude_m",
                "satellites",
                "hdop",
                "speed_kmh",
                "rssi_dbm",
                "current_fix",
                "using_last_known",
                "fix_quality",
                "fix_age_s",
                "packet_loss_percent",
                "distance_from_start_m",
            ]
        )
        self.log_file.flush()
        self.vars["log"].set(self.log_path.name)

    def close_log(self) -> None:
        if self.log_file:
            self.log_file.close()
        self.log_file = None
        self.writer = None

    def process_queue(self) -> None:
        try:
            while True:
                event, payload = self.q.get_nowait()
                if event == "line":
                    self.append_raw(payload)
                    self.handle_line(payload)
                elif event == "status":
                    self.status_var.set(payload)
                    self.start_log()
                elif event == "error":
                    self.status_var.set("Serial error")
                    text = str(payload)
                    if "PermissionError" in text or "Access is denied" in text:
                        messagebox.showerror(
                            APP_TITLE,
                            "The selected COM port is already in use.\n\n"
                            "Close Arduino IDE Serial Monitor and Serial Plotter, "
                            "then click Refresh and select the Uno's COM port.\n\n"
                            f"Technical detail: {text}",
                        )
                    else:
                        messagebox.showerror(APP_TITLE, f"Serial error:\n{text}")
                elif event == "disconnected":
                    self.connect_btn.config(text="Connect")
                    self.worker = None
                    if self.status_var.get() != "Serial error":
                        self.status_var.set("Disconnected")
                    self.close_log()
        except queue.Empty:
            pass
        self.after(100, self.process_queue)

    def append_raw(self, line: str) -> None:
        self.raw.config(state=tk.NORMAL)
        self.raw.insert(tk.END, line + "\n")
        self.raw.see(tk.END)
        if int(self.raw.index("end-1c").split(".")[0]) > 1500:
            self.raw.delete("1.0", "300.0")
        self.raw.config(state=tk.DISABLED)

    def handle_line(self, line: str) -> None:
        data = DATA_RE.search(line)
        if data:
            item = self.parse_payload(data.group("payload"))
            if item:
                item.rssi_dbm = int(data.group("rssi"))
                self.commit(item)
            return

        match = PACKET_RE.search(line)
        if match:
            self.pending = self.from_match(match)
            return

        rssi = RSSI_RE.search(line)
        if rssi and self.pending:
            self.pending.rssi_dbm = int(rssi.group("rssi"))
            self.commit(self.pending)
            self.pending = None

    def parse_payload(self, text: str) -> Optional[Telemetry]:
        match = PACKET_RE.search(text)
        return self.from_match(match) if match else None

    @staticmethod
    def from_match(match: re.Match) -> Telemetry:
        fix = match.group("lat") is not None
        return Telemetry(
            packet=int(match.group("pkt")),
            timestamp=datetime.now(),
            has_fix=fix,
            latitude=float(match.group("lat")) if fix else None,
            longitude=float(match.group("lon")) if fix else None,
            altitude_m=float(match.group("alt")) if fix else None,
            satellites=int(match.group("sat") if fix else match.group("nofix_sat")),
            hdop=float(match.group("hdop")) if fix else None,
            speed_kmh=float(match.group("spd")) if fix else None,
        )

    def smooth_altitude(self, raw_altitude_m: float) -> tuple[float, float]:
        """Median-filter then exponentially smooth GPS altitude."""
        self.altitude_window.append(raw_altitude_m)
        median_altitude = float(statistics.median(self.altitude_window))

        if self.smoothed_absolute_altitude is None:
            self.smoothed_absolute_altitude = median_altitude
        else:
            self.smoothed_absolute_altitude = (
                ALTITUDE_EMA_ALPHA * median_altitude
                + (1.0 - ALTITUDE_EMA_ALPHA) * self.smoothed_absolute_altitude
            )

        if self.altitude_baseline is None:
            self.altitude_baseline = self.smoothed_absolute_altitude

        relative = self.smoothed_absolute_altitude - self.altitude_baseline
        if abs(relative) < 0.05:
            relative = 0.0
        self.current_relative_altitude = relative
        return self.smoothed_absolute_altitude, relative

    def commit(self, telemetry: Telemetry) -> None:
        self.last_rx = time.monotonic()
        self.received += 1

        if self.last_packet is not None and telemetry.packet > self.last_packet + 1:
            self.missed += telemetry.packet - self.last_packet - 1
        self.last_packet = telemetry.packet

        total = self.received + self.missed
        loss = 100.0 * self.missed / total if total else 0.0

        displayed_latitude: Optional[float] = None
        displayed_longitude: Optional[float] = None
        smoothed_altitude: Optional[float] = self.smoothed_absolute_altitude
        relative_altitude: Optional[float] = self.current_relative_altitude
        distance = self.last_distance_m
        fix_quality = "NO FIX"
        fix_age_s: Optional[float] = None

        if telemetry.has_fix and telemetry.latitude is not None and telemetry.longitude is not None:
            self.using_last_known = False
            self.last_valid = telemetry
            self.last_fix_monotonic = time.monotonic()
            displayed_latitude = telemetry.latitude
            displayed_longitude = telemetry.longitude
            self.current_position = (telemetry.latitude, telemetry.longitude)

            if self.start_position is None:
                self.start_position = self.current_position

            distance = haversine_m(
                self.start_position[0],
                self.start_position[1],
                telemetry.latitude,
                telemetry.longitude,
            )
            self.last_distance_m = distance

            self.latitudes.append(telemetry.latitude)
            self.longitudes.append(telemetry.longitude)
            self.latitudes = self.latitudes[-MAX_POINTS:]
            self.longitudes = self.longitudes[-MAX_POINTS:]

            if telemetry.altitude_m is not None:
                smoothed_altitude, relative_altitude = self.smooth_altitude(
                    telemetry.altitude_m
                )
                self.max_relative_altitude = (
                    relative_altitude
                    if self.max_relative_altitude is None
                    else max(self.max_relative_altitude, relative_altitude)
                )
                self.alt_times.append(telemetry.timestamp)
                self.relative_altitudes.append(relative_altitude)
                self.alt_times = self.alt_times[-MAX_POINTS:]
                self.relative_altitudes = self.relative_altitudes[-MAX_POINTS:]

            fix_quality = classify_fix_quality(telemetry.satellites, telemetry.hdop)
            self.vars["position"].set(
                f"{telemetry.latitude:.6f}, {telemetry.longitude:.6f}"
            )
            self.vars["fix_quality"].set(
                f"{fix_quality} — current fix"
            )
            self.vars["hdop"].set(
                f"{telemetry.hdop:.2f}" if telemetry.hdop is not None else "—"
            )
            self.vars["speed"].set(
                f"{telemetry.speed_kmh:.1f} km/h"
                if telemetry.speed_kmh is not None
                else "—"
            )
        elif self.last_valid is not None:
            self.using_last_known = True
            displayed_latitude = self.last_valid.latitude
            displayed_longitude = self.last_valid.longitude
            if self.last_fix_monotonic is not None:
                fix_age_s = max(0.0, time.monotonic() - self.last_fix_monotonic)

            self.vars["position"].set(
                f"{displayed_latitude:.6f}, {displayed_longitude:.6f} "
                f"(last known, {fix_age_s:.1f} s old)"
            )
            self.vars["fix_quality"].set(
                f"LAST KNOWN — current fix unavailable ({fix_age_s:.1f} s)"
            )
            self.vars["hdop"].set(
                f"{self.last_valid.hdop:.2f} (last known)"
                if self.last_valid.hdop is not None
                else "—"
            )
            self.vars["speed"].set(
                f"{self.last_valid.speed_kmh:.1f} km/h (last known)"
                if self.last_valid.speed_kmh is not None
                else "—"
            )
            fix_quality = "LAST KNOWN"
        else:
            self.using_last_known = False
            self.vars["position"].set("No GPS fix yet")
            self.vars["fix_quality"].set("NO FIX — waiting for first valid position")
            self.vars["hdop"].set("—")
            self.vars["speed"].set("—")

        if telemetry.rssi_dbm is not None:
            self.rssi_times.append(telemetry.timestamp)
            self.rssis.append(telemetry.rssi_dbm)
            self.rssi_times = self.rssi_times[-MAX_POINTS:]
            self.rssis = self.rssis[-MAX_POINTS:]

        self.vars["packet"].set(str(telemetry.packet))
        self.vars["satellites"].set(str(telemetry.satellites))
        self.vars["rssi"].set(
            f"{telemetry.rssi_dbm} dBm" if telemetry.rssi_dbm is not None else "—"
        )
        self.vars["loss"].set(f"{loss:.2f}% ({self.missed} missed)")
        self.vars["distance"].set(
            f"{distance:.1f} m" if distance is not None else "—"
        )
        self.vars["relative_altitude"].set(
            f"{relative_altitude:+.1f} m"
            if relative_altitude is not None
            else "—"
        )
        self.vars["gps_altitude"].set(
            f"{smoothed_altitude:.1f} m"
            if smoothed_altitude is not None
            else "—"
        )
        self.vars["max_relative_altitude"].set(
            f"{self.max_relative_altitude:+.1f} m"
            if self.max_relative_altitude is not None
            else "—"
        )

        if self.writer and self.log_file:
            self.writer.writerow(
                [
                    telemetry.timestamp.isoformat(timespec="milliseconds"),
                    telemetry.packet,
                    telemetry.latitude if telemetry.latitude is not None else "",
                    telemetry.longitude if telemetry.longitude is not None else "",
                    telemetry.altitude_m if telemetry.altitude_m is not None else "",
                    displayed_latitude if displayed_latitude is not None else "",
                    displayed_longitude if displayed_longitude is not None else "",
                    smoothed_altitude if smoothed_altitude is not None else "",
                    relative_altitude if relative_altitude is not None else "",
                    telemetry.satellites,
                    telemetry.hdop if telemetry.hdop is not None else "",
                    telemetry.speed_kmh if telemetry.speed_kmh is not None else "",
                    telemetry.rssi_dbm if telemetry.rssi_dbm is not None else "",
                    telemetry.has_fix,
                    self.using_last_known,
                    fix_quality,
                    f"{fix_age_s:.3f}" if fix_age_s is not None else "",
                    f"{loss:.4f}",
                    f"{distance:.3f}" if distance is not None else "",
                ]
            )
            self.log_file.flush()

        self.redraw_plots()

    def redraw_plots(self) -> None:
        self.alt_ax.clear()
        self.alt_ax.set_title("Smoothed relative altitude versus time")
        self.alt_ax.set_xlabel("Time")
        self.alt_ax.set_ylabel("Relative altitude (m)")
        self.alt_ax.axhline(0.0, linewidth=0.8)
        if self.alt_times:
            self.alt_ax.plot(self.alt_times, self.relative_altitudes)
            self.alt_fig.autofmt_xdate()
        self.alt_fig.tight_layout()
        self.alt_canvas.draw_idle()

        self.rssi_ax.clear()
        self.rssi_ax.set_title("LoRa RSSI versus time")
        self.rssi_ax.set_xlabel("Time")
        self.rssi_ax.set_ylabel("RSSI (dBm)")
        if self.rssi_times:
            self.rssi_ax.plot(self.rssi_times, self.rssis)
            self.rssi_fig.autofmt_xdate()
        self.rssi_fig.tight_layout()
        self.rssi_canvas.draw_idle()

        self.track_ax.clear()
        self.track_ax.set_title("GPS ground track")
        self.track_ax.set_xlabel("Longitude")
        self.track_ax.set_ylabel("Latitude")
        if self.latitudes:
            self.track_ax.plot(self.longitudes, self.latitudes, marker=".")
            self.track_ax.ticklabel_format(useOffset=False, style="plain")
        self.track_fig.tight_layout()
        self.track_canvas.draw_idle()

    def update_status_ages(self) -> None:
        if self.last_rx is None:
            self.vars["link"].set("No packets")
        else:
            age = time.monotonic() - self.last_rx
            if age < 2.5:
                self.vars["link"].set("ACTIVE")
            elif age < 6.0:
                self.vars["link"].set(f"STALE ({age:.1f} s)")
            else:
                self.vars["link"].set(f"LOST ({age:.1f} s)")

        if (
            self.using_last_known
            and self.last_valid is not None
            and self.last_fix_monotonic is not None
        ):
            fix_age = max(0.0, time.monotonic() - self.last_fix_monotonic)
            self.vars["position"].set(
                f"{self.last_valid.latitude:.6f}, {self.last_valid.longitude:.6f} "
                f"(last known, {fix_age:.1f} s old)"
            )
            self.vars["fix_quality"].set(
                f"LAST KNOWN — current fix unavailable ({fix_age:.1f} s)"
            )

        self.after(500, self.update_status_ages)

    def zero_altitude(self) -> None:
        if self.smoothed_absolute_altitude is None:
            messagebox.showinfo(
                APP_TITLE,
                "A valid GPS altitude has not been received yet. Wait for a fix, then try again.",
            )
            return

        self.altitude_baseline = self.smoothed_absolute_altitude
        self.current_relative_altitude = 0.0
        self.max_relative_altitude = 0.0
        self.alt_times.clear()
        self.relative_altitudes.clear()
        self.vars["relative_altitude"].set("+0.0 m")
        self.vars["max_relative_altitude"].set("+0.0 m")
        self.redraw_plots()
        self.status_var.set("Relative altitude zeroed at current GPS altitude")

    def clear_session(self) -> None:
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

        self.altitude_window.clear()
        self.smoothed_absolute_altitude = None
        self.altitude_baseline = None
        self.current_relative_altitude = None
        self.max_relative_altitude = None

        self.alt_times.clear()
        self.relative_altitudes.clear()
        self.rssi_times.clear()
        self.rssis.clear()
        self.latitudes.clear()
        self.longitudes.clear()

        for key in self.vars:
            self.vars[key].set("—")
        self.vars["link"].set("No packets")
        self.vars["position"].set("No GPS fix yet")
        self.vars["fix_quality"].set("NO FIX")
        self.vars["loss"].set("0.00%")
        self.vars["log"].set(self.log_path.name if self.log_path else "Not logging")

        self.raw.config(state=tk.NORMAL)
        self.raw.delete("1.0", tk.END)
        self.raw.config(state=tk.DISABLED)
        self.redraw_plots()

    def open_log_folder(self) -> None:
        folder = Path(__file__).resolve().parent / "telemetry_logs"
        folder.mkdir(exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except AttributeError:
            webbrowser.open(folder.as_uri())

    def open_map(self) -> None:
        if not self.current_position:
            messagebox.showinfo(APP_TITLE, "No valid GPS position has been received.")
            return
        lat, lon = self.current_position
        webbrowser.open(f"https://www.google.com/maps?q={lat:.7f},{lon:.7f}")

    def close_app(self) -> None:
        self.stop_event.set()
        self.close_log()
        self.destroy()


if __name__ == "__main__":
    GroundStation().mainloop()
