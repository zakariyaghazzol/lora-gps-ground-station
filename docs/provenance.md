# Source provenance

Project: Zakariya Ghazzol's July 2026 LoRa GPS telemetry and ground station.
Public-copy preparation and offline regression checks: September 23, 2026.

The three sketches and dashboard were selected from the existing project's
working copies and compared against its July 17, 2026 verified-baseline
manifest. All four match that manifest's SHA-256 values and are unchanged in
this copy. Baseline audit dates describe local evidence, not a public release.

| Included source | SHA-256 |
|---|---|
| `firmware/NanoGPStransmitter/NanoGPStransmitter.ino` | `86c81e57f1538b7d656623967cb080d06fb53aa04ba41e3758ec13d357cd7d51` |
| `firmware/UNOreceiverV2GPS/UNOreceiverV2GPS.ino` | `cb28e15c9c3f5c230d0d26932adabd79594aa0022cfe4d520eef0f4e6eb9da1a` |
| `firmware/UnoReceiverDashboard/UnoReceiverDashboard.ino` | `44ff3caca7111dd6114da691ea793531ba5d16f8ea9c0b6a42f8948e27dc985c` |
| `ground_station/ground_station_v3.py` | `cdd4a4ae29cc881092898f50f4d1afa299f15eee058c250abc4d4397cf54ade5` |

`requirements.txt` retains the original package's two dependency bounds.
README, documentation, ignore rules, synthetic fixture, offline adapter, and
17 regression tests were added for this source snapshot. They are not evidence
that those tests existed during the July experiment. No original file was
modified, and no private Git history was copied.

No source-level copyright/license header was present in the four selected
files. None was removed. Dependency authors and license information are listed
in [third-party notices](../THIRD_PARTY_NOTICES.md); their implementation source,
examples, libraries, and binaries are not bundled. Review against the locally
installed RadioHead `rf95_client` and `rf95_server` examples found shared short
API/Arduino idioms, but did not establish a substantive copied example body.
That limited comparison is not a complete chain-of-authorship audit.

Excluded: real GPS CSV logs, timestamps/location traces, photos, machine/user
paths, credentials, archived downloads, dependency trees, build outputs, and
unrelated flight-computer or camera material. The aggregate evidence document
contains no real latitude or longitude. Synthetic example coordinates were
invented near (0, 0), not transformed from a real track.

No project-wide license has been chosen or added. This source snapshot does
not grant a new open-source license to the project or change the terms of
separately installed dependencies.

## Dashboard image added September 23, 2026

The README screenshot is a native capture of the existing v3 UI loaded by a
local presentation wrapper with stored values from the documented historical
CSV. The wrapper disables hardware/map access, withholds location fields,
labels the view as a replay, and uses elapsed time on the plot. It does not
modify the original dashboard implementation. The image is not generated or
retouched to invent readings, and is not the exact session in the earlier
phone photograph. The private CSV and local wrapper are not distributed.
