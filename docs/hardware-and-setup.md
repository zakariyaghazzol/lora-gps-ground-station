# Hardware and setup

## Historical hardware

- Arduino Nano transmitter, u-blox NEO-6M / GY-GPS6MV2 GPS module.
- Arduino Uno R3 receiver.
- Two Adafruit RFM95 900 MHz radio breakouts with appropriate antennas.
- USB connection from the Uno to the desktop dashboard.

The source selects 915.0 MHz on both radios; transmitter power is set through
`setTxPower(13, false)`. It does not explicitly override the RadioHead modem
configuration. Do not infer a tested range or range margin from this setup.

## Pin assignments from the sketches

| Connection | Nano transmitter | Uno receiver |
|---|---|---|
| RFM95 CS | D10 | D10 |
| RFM95 reset | D9 | D9 |
| RFM95 interrupt / DIO0 | D2 | D2 |
| SPI MOSI / MISO / SCK | Hardware SPI | Hardware SPI |
| GPS TX -> MCU RX | D4 | Not connected |
| GPS RX | Not connected (D3 is reserved as SoftwareSerial TX) | Not connected |

The classic AVR Nano/Uno hardware SPI pins are D11/D12/D13 respectively.
This table is a signal assignment, not a power/level-shifting schematic.
Verify the exact board and breakout documentation, supply and logic-voltage
compatibility, common ground, antenna connection, and local RF requirements
before powering/transmitting. Bare radio modules and breakouts may have
different electrical requirements. No wiring was changed or powered during
this publication-preparation validation.

## Firmware

Use Arduino IDE or Arduino CLI with the Arduino AVR core. Install RadioHead
and TinyGPSPlus separately; SPI and SoftwareSerial come from the AVR core.
The inspected local versions were AVR core 1.8.8, RadioHead 1.143.1, and
TinyGPSPlus 1.0.3. Historical installed dependency versions were not recorded.

Open the `.ino` with its matching folder name. Choose Nano for
`NanoGPStransmitter`; choose Uno for **one** of the receiver alternatives.
`UnoReceiverDashboard` is the single-line variant recommended for this app.
Select the Nano bootloader/processor option matching the physical board.

Compile-only checks, with no port or upload command:

```sh
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 firmware/NanoGPStransmitter
arduino-cli compile --fqbn arduino:avr:uno firmware/UnoReceiverDashboard
arduino-cli compile --fqbn arduino:avr:uno firmware/UNOreceiverV2GPS
```

Compilation is not a hardware test. Upload and RF operation require a separate
intentional bench step after electrical and operating checks.

## Python dashboard

Use Python 3.10+ with Tkinter, PySerial and Matplotlib. Tkinter comes with many
desktop Python installers but may need an OS-specific package on Linux. The
original dependency bounds are retained in `requirements.txt`; they are not a
lockfile. For this preparation, tests used Python 3.13.14, PySerial 3.5 and
Matplotlib 3.11.0 on Windows.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m ground_station.offline_replay
python ground_station/ground_station_v3.py
```

For a live session, close Arduino Serial Monitor/Plotter so the port is free,
select the Uno's port explicitly and connect at 9600 baud. Wait for GPS fix;
use **Zero Altitude** to set a relative reference. **Disconnect** closes the
serial worker and log. Restart the app for a clean independent experiment.

Logs are created automatically in `ground_station/telemetry_logs/`. They
contain sensitive location/time data. Never use a real log as a public sample.
The map button opens an external browser with position in the URL; it may use
the retained last-known position during fix loss.
