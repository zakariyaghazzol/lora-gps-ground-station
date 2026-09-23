# Validation and measured evidence

## Historical hardware session (July 2026)

The following aggregate values were recomputed on September 23, 2026 from a
retained private CSV. The CSV is not part of this repository because it contains
precise raw/displayed GPS coordinates and timestamps.

| Metric | Result |
|---|---:|
| Logged data rows | 20,152 |
| First-to-last row elapsed time | 340.381233 minutes (5.673 hours) |
| Last row's stored `packet_loss_percent` | 0.5549% |
| Mean nonblank `rssi_dbm` | -53.115472 dBm |
| Maximum `satellites` | 11 |
| Rows with `current_fix=True` | 19,773 |
| Rows with `using_last_known=True` | 379 |

Privacy-safe method: count data rows; subtract first from last `computer_time`;
take the last stored loss value; average nonblank RSSI; find maximum satellite
count; and count the two Boolean columns. No coordinates are needed for these
aggregates. The input file's SHA-256 was
`2eaf176a3e2063eca45e3bae05e5fb55dd0be75983e3380be706659e0e26b178`.

The loss value is the **final dashboard-reported cumulative estimate**. It is
not independently reconstructed from these row counts and is not a calibrated
RF delivery measurement: reconnects, clears, duplicates, restarts, and gaps
before logging can affect its denominator. The CSV supports a long operating
session, not a demonstrated maximum range, spatial accuracy, or physical
flight. Private retention also means a public reader cannot independently
reproduce this historical summary from the published fixture.

## Offline source checks (September 23, 2026)

The public copy adds 17 passing `unittest` tests that call the unchanged
dashboard methods through a headless adapter. Coverage includes both receiver
envelopes, payload fields, startup noise, selected incomplete input, fix loss
and recovery, altitude smoothing, quality thresholds, synthetic distance,
sequence gaps, bounded plot history, CSV raw/retained-field distinction, and
the shipped synthetic fixture. Two tests explicitly characterize permissive
parsing and duplicate counting; they do not claim those limitations are fixed.

```sh
python -m unittest discover -s tests -v
python -m ground_station.offline_replay
```

The fixture produces six received packets, one intentionally omitted sequence
number, a 14.29% legacy loss estimate, and a final last-known position state.
Those are invented test conditions, not historical RF performance.

Test runtime: Python 3.13.14, PySerial 3.5, Matplotlib 3.11.0 on Windows. No
serial device, browser map, Tk window, or real GPS data is opened by these
tests. The adapter uses in-memory labels and disables plot rendering; it does
not verify GUI appearance, serial timing, actual radio delivery, or hardware.

All three sketches also passed offline compile-only checks with Arduino CLI
1.5.1, Arduino AVR core 1.8.8, RadioHead 1.143.1, and TinyGPSPlus 1.0.3:

| Sketch / target | Program bytes | Global RAM bytes |
|---|---:|---:|
| `NanoGPStransmitter` / `arduino:avr:nano:cpu=atmega328` | 16,976 / 30,720 | 1,031 / 2,048 |
| `UnoReceiverDashboard` / `arduino:avr:uno` | 8,364 / 32,256 | 635 / 2,048 |
| `UNOreceiverV2GPS` / `arduino:avr:uno` | 8,506 / 32,256 | 635 / 2,048 |

Build output is not distributed. These compile results do not verify runtime
stack margin, wiring, or radio behavior. No firmware upload, radio transmission,
or new physical experiment was performed for this source preparation.
