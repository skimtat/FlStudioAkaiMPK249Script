# Akai MPK249 — FL Studio MIDI Controller Script

**A free, open-source FL Studio controller script for the Akai Professional MPK249.** Get working transport buttons, all 64 drum pads, and pitch/mod wheels in FL Studio 2025 — no clunky generic-controller setup, no guesswork. Every MIDI value here was captured and verified against real MPK249 hardware.

![Platform](https://img.shields.io/badge/FL%20Studio-2025-orange)
![MIDI Scripting](https://img.shields.io/badge/MIDI%20Scripting-v40-blue)
![Python](https://img.shields.io/badge/Python-3.12-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

> If you searched **"Akai MPK249 FL Studio script"**, **"MPK249 transport buttons not working in FL Studio"**, **"MPK249 pads FPC"**, or **"MPK249 pitch bend / mod wheel not working FL Studio"** — you're in the right place.

---

## Why this exists

The MPK249 is one of the most popular 49-key controllers out there, but it ships with **no native FL Studio integration**. Out of the box the transport buttons don't move FL's transport, the pads don't route anywhere useful, and the pitch/mod wheels often go dead the moment you assign the controller to a script. This project fixes all of that with a single, fully-commented Python file you drop into FL Studio.

---

## Features

| Feature | Status |
|---|---|
| ▶️ Transport — Play / Stop / Record / Loop / Forward / Back | ✅ Working |
| 🥁 Drum pads — all 4 banks (A/B/C/D), 64 pads, → FPC / any channel | ✅ Working |
| 🎚️ On-screen hint feedback for every action | ✅ Working |
| 🏦 Automatic pad-bank detection (no bank button needed) | ✅ Working |
| 🎡 Pitch bend & mod wheel | ✅ Working (FL-side setup — see below) |
| 🎛️ Assignable knobs & faders → mixer / plugin params | 🚧 In progress |
| 💡 Pad LED / visual feedback | 🚧 Planned |

---

## Requirements

- **FL Studio 2025** (MIDI Scripting version 40; built-in Python **3.12.1**). No external libraries — FL Studio API only.
- **Akai MPK249** on **Preset 11** (the "FL Studio" preset).
- **Windows 11** (developed and tested here). macOS likely works but is untested — reports welcome.

---

## Installation

1. **Download** `device_MPK249.py` from this repo.

2. **Place it** in a folder named `MPK249` inside your FL Studio hardware settings directory:

   ```
   …/Image-Line/FL Studio/Settings/Hardware/MPK249/device_MPK249.py
   ```

   Not sure where that is? In FL Studio open **Options → File settings** and check your user-data folder. (It is *not* always under `Documents` — it can live on another drive.)

3. In FL Studio open **Options → MIDI Settings**.

4. In the **Input** list, click your MPK249 port and set **Controller type → "Akai MPK249 (FL Studio)"**. Enable it and give it a **Port number**. The MPK exposes several ports (`MPK249`, `MIDIIN2/3/4`); the main `MPK249` port carries transport and pads, so start there.

5. Open **View → Script output**. On success you'll see:

   ```
   [MPK249] OnInit - device: MPK249, FL version: 40
   ```

   No output? Click **Reload script** in that window.

---

## Transport controls

The MPK249's transport buttons send **Control Change** messages (not MMC, despite what Akai's docs imply — verified live). The script maps them to FL's transport, with a hint-bar message on every press.

| Button  | Action                  | CC  |
|---------|-------------------------|-----|
| Play    | Toggle playback         | 118 |
| Stop    | Stop                    | 117 |
| Record  | Toggle record           | 119 |
| Loop    | Toggle loop recording   | 114 |
| Forward | Jump to next marker     | 116 |
| Back    | Jump to previous marker | 115 |

---

## Drum pads → FPC

Pads send **Note On/Off on MIDI channel 10**, in four contiguous 16-note banks:

| Bank | Notes  |
|------|--------|
| A    | 36–51  |
| B    | 52–67  |
| C    | 68–83  |
| D    | 84–99  |

Because each bank is a distinct note range, the script knows the active bank **from the note alone** — no need to read the A/B/C/D button. Every strike shows feedback like `Pad B03 (note 54, vel 110)` and remembers the active bank.

**To play FPC (or any drum instrument):** select that channel in the Channel Rack — the pads trigger it. Keyboard keys are filtered out (they're on a different channel), so you can play keys and pads without crosstalk.

> **Tip:** pad velocity coming through as a flat `127`? That's the MPK's **Full Level** button — turn it off for velocity-sensitive drumming.

---

## Pitch bend & mod wheel (important)

If your **pitch/mod wheels stopped working after assigning the MPK to a controller script**, you're not crazy — this is a known FL Studio behavior, not a bug in this script.

When a MIDI port is bound to a **controller script**, FL Studio forwards unhandled **notes** to the selected channel automatically, but it does **not** forward pitch bend or mod wheel, and there's no script API to inject them as performance data. The clean fix is FL's own **global controller links**, which read the wheel MIDI independently of the script:

1. Add an instrument and open it so its wrapper is visible.
2. **Right-click the plugin's pitch-bend wheel → "Link to controller…"**.
3. Move the **MPK pitch wheel** so FL auto-detects it.
4. Tick **"Make global"** so it applies to every project.
5. Click **Accept**, then repeat for the **mod wheel**.
6. Save these into your **default template** so every new project has them.

This coexists perfectly with the script — transport and pads keep working while the wheels drive plugins natively, across all projects.

---

## Troubleshooting

**Script output shows nothing / `OnInit` never prints.** The port isn't bound. Re-check Controller type in MIDI Settings, then click **Reload script**.

**Transport buttons do nothing.** Make sure the script is on the **main `MPK249` port**, and that you're on **Preset 11**.

**Pads only send aftertouch, no notes.** Re-send/reload your preset to the MPK, and **strike** the pads (a sharp hit) rather than pressing slowly — MPC-style pads need velocity to fire a Note-On.

**Pitch/mod wheels dead.** See the [Pitch bend & mod wheel](#pitch-bend--mod-wheel-important) section — set up the global links.

**Want to see what your hardware is sending?** Set `DEBUG = True` (it's on by default) and watch **View → Script output**. Set `CAPTURE_ONLY = True` to make the script a pure MIDI sniffer that logs everything and acts on nothing — handy for mapping new controls.

---

## How it works

`device_MPK249.py` is a single self-contained module. FL Studio calls its `OnInit` / `OnMidiMsg` / `OnMidiIn` / `OnSysEx` callbacks; incoming MIDI is dispatched by type to dedicated handlers (transport, pads, CC). Every hardware-specific MIDI number lives in one **CONFIG — MIDI MAP** block at the top of the file, each value verified against real hardware. A `DEBUG` logger and a `CAPTURE_ONLY` sniffer mode make it easy to discover and add new mappings safely.

---

## Roadmap

- [x] Transport (Play / Stop / Record / Loop / Forward / Back)
- [x] Drum pads — all 4 banks, channel 10, with bank detection + feedback
- [x] Pitch & mod wheels (via FL global links — documented)
- [ ] Knob / fader CC mapping (mixer + plugin params)
- [ ] Optional "pads always → FPC" routing, independent of channel selection
- [ ] Pad LED / visual feedback

---

## Contributing

Issues and pull requests welcome. If your MPK249 behaves differently — different preset, firmware, or OS — open an issue with a capture from **Script output** and we'll widen hardware support.

## License

[MIT](LICENSE) — free to use, modify, and share. Built by and for the FL Studio community.

---

<sub>Keywords: Akai MPK249, FL Studio 2025, MIDI controller script, FL Studio template, FPC, drum pads, transport control, pitch bend, mod wheel, Image-Line, MPK249 FL Studio setup, MPK249 not working, device_MPK249.py.</sub>
