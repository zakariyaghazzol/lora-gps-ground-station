# Third-party dependencies and attribution

This repository includes project sketches and Python application source, not
vendored libraries, third-party example directories, or compiled firmware.
Third-party packages remain under their upstream terms. A project-wide license
has not been selected; nothing here assigns new terms to upstream code.

| Dependency | Attribution / inspected metadata | Use |
|---|---|---|
| RadioHead `RH_RF95` | Mike McCauley / AirSpayce; local 1.143.1 headers describe GPLv3 or commercial licensing | RFM95 radio driver, separately installed |
| TinyGPSPlus | Mikal Hart; local 1.0.3 header states LGPL 2.1 or later | GPS NMEA parsing, separately installed |
| Arduino AVR core (`SPI`, `SoftwareSerial`) | Arduino and the authors credited in the installed core | Board support and serial/SPI interfaces, separately installed |
| PySerial | Chris Liechti and contributors, as credited by the installed package | Desktop serial transport |
| Matplotlib | Matplotlib development team, as credited by the installed package | Desktop graphs |
| Python / Tkinter / Tcl/Tk | Respective upstream projects and contributors | Runtime and desktop interface |

RadioHead's dependency licensing is distinct from the provenance of the
sketches in this repository. The snapshot distributes neither RadioHead source
nor linked firmware binaries. Consult the installed dependency's license and
applicable upstream terms before redistributing a combined build; do not infer
a blanket license for all source from this table.

No upstream author or license text has been removed from included source.
Original-source comparisons and their limits are recorded in
[`docs/provenance.md`](docs/provenance.md).
