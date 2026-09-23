# Packet protocol and legacy behavior

The sketches exchange ASCII payloads. The project informally calls this
unversioned format `GPS0`; the literal text `GPS0` is **not** sent. There is no
`FC1` support in this historical dashboard.

## Radio payload

```text
PKT:<sequence>,LAT:<degrees>,LON:<degrees>,ALT:<meters>,SAT:<count>,HDOP:<value>,SPD:<km/h>
PKT:<sequence>,NO_FIX,SAT:<count>
```

Field order is fixed. The transmitter formats coordinates to six decimals,
altitude and speed to one decimal, and HDOP to two decimals. `PKT` increments
after each send attempt and starts at zero on boot. On the AVR boards it is a
32-bit unsigned value. The main loop schedules a send when at least 1000 ms
has elapsed; blocking radio and debug/GPS handling can affect actual cadence.

A fixed payload requires a valid GPS location younger than 3000 ms. The sketch
does not independently check age/validity of altitude, speed, satellite count,
or HDOP. `NO_FIX` means current position is unavailable; retained display data
must not be mistaken for a new fix.

## USB serial envelopes (9600 baud)

The `UnoReceiverDashboard` sketch emits one line per successful receive:

```text
DATA,PKT:1,LAT:0.000000,LON:0.000000,ALT:100.0,SAT:10,HDOP:0.90,SPD:0.0,RSSI:-50
```

The `UNOreceiverV2GPS` sketch uses two lines plus an empty separator:

```text
Telemetry: PKT:1,LAT:0.000000,LON:0.000000,ALT:100.0,SAT:10,HDOP:0.90,SPD:0.0
LoRa RSSI: -50 dBm
```

Examples above are synthetic. RSSI is the receiving radio's reported value,
not a field measured by the GPS or transmitter. The dashboard commits the
two-line variant only after an RSSI line arrives. A new payload can replace an
uncommitted pending payload; there is no pending-packet timeout.

## Processing

- Quality heuristic: EXCELLENT at >=8 satellites and HDOP <=1.2; GOOD at >=6
  and <=2.0; FAIR at >=4 and <=5.0; POOR otherwise; UNKNOWN for missing HDOP.
- Altitude: median of the last five fixed samples, then EMA with alpha 0.25.
  The first smoothed altitude is the baseline. **Zero Altitude** resets it.
- Fix loss: preserve the last position, altitude, HDOP, speed and distance;
  label them last-known, update fix age, and avoid appending a false new track
  point. Raw missing position fields remain blank in the CSV.
- Packet loss: add positive forward sequence gaps to `missed`; calculate
  `100 * missed / (received + missed)`. Loss before the first received packet
  cannot be inferred by this method.
- Plot data retain the latest 600 points; the CSV can span the full session.

## Known limitations

These are preserved historical behaviors, not guarantees of robustness:

- Regex matching searches within a line. It does not require exact framing,
  validate numeric ranges, or reject all malformed/trailing text.
- Every committed packet counts as received, including duplicates. Reboots,
  reordering and 32-bit wrap are not reconciled. A stale packet followed by a
  newer packet may inflate the gap estimate.
- A pending two-line payload can be paired with a later unrelated RSSI line.
  Prefer the single-line receiver for an unambiguous envelope.
- Reconnecting starts a new CSV but does not itself clear counters/history.
  **Clear** resets in-memory state but does not start a new CSV. Either action
  can complicate interpretation of session-wide loss statistics.
- There is no application authentication, encryption, acknowledgement, or
  retransmission. This is RadioHead point-to-point LoRa, not LoRaWAN.
- Satellite/HDOP grades are a display heuristic, not an accuracy certification.
  GPS altitude and relative-altitude plots are not calibrated flight sensors.

The tests characterize these boundaries; they do not imply RF, electrical,
GUI-interaction, navigation, or flight qualification.
