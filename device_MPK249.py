# name=Akai MPK249 (FL Studio)
# url=https://github.com/skimtat/FlStudioAkaiMPK249Script
# supportedDevices=MPK249
#
# Akai MPK249 — FL Studio MIDI Controller Script
# ------------------------------------------------
# Open-source community script. Built for MPK249 Preset 11 ("FL Studio").
#
# Install location (Windows):
#   Documents/Image-Line/FL Studio/Settings/Hardware/MPK249/device_MPK249.py
#
# This file is intentionally a SINGLE self-contained module so that community
# users can install it by copying one file. Concerns are separated by function
# and clearly delineated section headers rather than by separate files.
#
# Build status:
#   [x] Lifecycle + dispatch scaffold
#   [x] Transport (MMC) handler            <-- implemented, values pending HW verify
#   [ ] Pad handler (4 banks -> FPC)       <-- stubbed
#   [ ] Knob / fader CC handler            <-- stubbed
#   [ ] Visual feedback / LED out          <-- stubbed

"""Akai MPK249 controller script for FL Studio 2025.

The FL Studio scripting host calls the module-level ``OnX`` callbacks defined
near the bottom of this file. Everything above them is configuration, state,
and the per-control-type handlers those callbacks dispatch into.
"""

# FL Studio built-in API modules. No external libraries are available inside
# the FL Studio Python runtime (3.12.1 in FL Studio 2025), so everything here is
# stdlib + these.
import transport   # play / stop / record / loop, global transport commands
import mixer       # mixer track control (volume, etc.) - used later by faders
import channels    # channel rack access - used later by pads
import patterns    # pattern navigation - used later
import ui          # hint bar messages, window focus
import midi        # MIDI + FPT_* command constants
import device      # this controller's I/O (midiOutMsg, port info)
import general     # misc helpers (general.getVersion, etc.)


# =============================================================================
# CONFIG  --  MIDI MAP  (VERIFY EVERY VALUE AGAINST THE HARDWARE)
# -----------------------------------------------------------------------------
# IMPORTANT: The numbers in this block are the *standard / expected* values for
# MPK249 Preset 11. They are NOT yet confirmed against Tracy's hardware. Before
# we treat any of these as final, they will be captured live with a MIDI
# monitor and corrected here. Keeping every magic number in one place is the
# whole point of this section.
# =============================================================================

# --- Debug -------------------------------------------------------------------
# When True, every inbound message and every action is printed to the FL Studio
# script output window (View > Script output) for live verification.
DEBUG = True

# When True the script acts purely as a MIDI sniffer: it logs every inbound
# message (including which port and the raw bytes) but performs NO transport or
# other action. This is the verification phase -- we use it to discover which
# port the controls actually use and what bytes they send, before wiring up any
# behaviour. Flip to False once the MIDI map is confirmed.
#
# Transport is now verified and wired, so capture mode is OFF. (Knobs/faders/
# pads are still unmapped stubs; they simply do nothing yet.)
CAPTURE_ONLY = False

# High-rate "stream" message types whose LOGGING is suppressed so they don't
# flood the Script output and bury the messages we care about (e.g. pad
# Note-Ons hidden under a torrent of pad aftertouch). Dispatch is unaffected --
# only the debug print is skipped.
#   0xD0 = channel aftertouch (pressure)   0xA0 = poly aftertouch
#   0xE0 = pitch bend
LOG_SUPPRESS_TYPES = (0xD0, 0xA0, 0xE0)

# --- Ports -------------------------------------------------------------------
# The MPK249 exposes four MIDI ports. In FL Studio's MIDI settings each port can
# be bound to this script. event.port reflects the port number the user typed in
# that settings page, so we do NOT hard-filter on it (it varies per machine).
# These constants are documentation + optional filtering only.
PORT_KEYS = 7       # "MPK249"  - main keyboard / transport
PORT_PADS = 8       # "MIDIIN2" - pads
PORT_CTRL = 9       # "MIDIIN3" - transport (MMC) / CC
PORT_AUX = 10       # "MIDIIN4" - auxiliary

# --- Transport: MIDI Machine Control (MMC) sub-command bytes -----------------
# MMC arrives as a SysEx frame:  F0 7F <deviceId> 06 <command> F7
# The <command> bytes below are from the MIDI MMC spec. High confidence, but
# still flagged for hardware verification because we need to confirm the MPK249
# actually emits these (and not, e.g., plain CC or Note transport).
MMC_STOP = 0x01
MMC_PLAY = 0x02
MMC_DEFERRED_PLAY = 0x03
MMC_FAST_FORWARD = 0x04
MMC_REWIND = 0x05
MMC_RECORD_STROBE = 0x06   # "punch in" / record on
MMC_RECORD_EXIT = 0x07
MMC_PAUSE = 0x09

# SysEx framing bytes we use to recognise an MMC message.
SYSEX_START = 0xF0
SYSEX_END = 0xF7
SYSEX_UNIVERSAL_RT = 0x7F   # universal real-time
SYSEX_MMC_SUBID = 0x06      # MMC command sub-id at index 3

# --- Transport: Control Change  (ACTUAL hardware behaviour -- VERIFIED) ------
# Discovery (2026-06-17, via the sniffer): on this MPK249 the six transport
# buttons do NOT send MMC. They send Control Change on MIDI channel 1
# (status 0xB0), value 127 on press, with no release message. The MMC SysEx
# path above is retained only as a fallback for other presets/firmware -- it is
# not what this hardware emits. These CC numbers are the real transport map.
TRANSPORT_CC_CHANNEL = 0          # 0-based MIDI channel (0 == MIDI channel 1)
TRANSPORT_CC_PRESS_VALUE = 127    # value sent on button press
TRANSPORT_CC_PLAY = 118
TRANSPORT_CC_STOP = 117
TRANSPORT_CC_RECORD = 119
TRANSPORT_CC_LOOP = 114
TRANSPORT_CC_FORWARD = 116
TRANSPORT_CC_BACK = 115

# --- Keyboard performance controls (pitch / mod wheel) -----------------------
# FINDING (verified 2026-06-17): when a port is bound to a controller SCRIPT, FL
# forwards unhandled *notes* to the selected channel, but NOT pitch bend or mod
# wheel -- and there is no script API that injects them as performance data the
# way channels.midiNoteOn injects notes. Attempts via processMIDICC /
# forwardMIDICC only fed the messages into FL's generic CC-link system (which
# even mis-linked pitch bend onto a mixer fader). So the script now leaves the
# wheels completely untouched. Full native wheel support requires running the
# keyboard port as a generic controller instead -- a pending design decision.
# Verified raw messages, for reference:
#   right wheel = CC 1 (Modulation) ; left wheel = Pitch Bend (status 0xE0)

# --- Pads (Note On/Off on MIDI channel 10) -- VERIFIED 2026-06-17 -------------
# Pads strike Note On (0x99) / Note Off (0x89) on channel 10. Each of the four
# pad banks (A/B/C/D) sends a distinct contiguous block of 16 notes, so the
# active bank can be DERIVED from the note number -- no separate bank-switch
# message is needed. Velocity arrived fixed at 127 (MPK "Full Level" was on;
# turn it off on the pads for velocity-sensitive playing).
#   Bank A: 36-51   Bank B: 52-67   Bank C: 68-83   Bank D: 84-99
PAD_MIDI_CHANNEL = 10        # 1-based (status nibble 9 -> 0x99 / 0x89)
PAD_BANK_A_BASE = 36         # bottom note of Bank A
PADS_PER_BANK = 16
PAD_BANK_COUNT = 4
PAD_LAST_NOTE = PAD_BANK_A_BASE + PAD_BANK_COUNT * PADS_PER_BANK - 1   # 99
BANK_NAMES = ("A", "B", "C", "D")

# --- Knobs / Faders (CC on Channel 1) ----------------------------------------
# CC numbers are user-assignable in the MPK editor; the Preset 11 defaults are
# unknown to this script until captured. Stubbed until then.
KNOB_CC_NUMBERS = []         # <-- VERIFY (expect 8 per bank)
FADER_CC_NUMBERS = []        # <-- VERIFY (expect 8 per bank)


# =============================================================================
# STATE
# =============================================================================
# Mutable runtime state lives in this single dict so it is easy to inspect and
# reset, and so handlers don't proliferate module-level globals.
STATE = {
    "pad_bank": 0,        # 0=A, 1=B, 2=C, 3=D
    "control_mode": "drum",  # "drum" (pads->FPC) vs "mixer" (controls->mixer)
}


# =============================================================================
# HELPERS
# =============================================================================
def _log(message):
    """Print to the FL Studio script output window when DEBUG is on."""
    if DEBUG:
        print("[MPK249] " + str(message))


def _should_log(event):
    """Whether to print this inbound event (filters high-rate noise streams)."""
    if not DEBUG:
        return False
    if event.sysex:
        return True
    return (event.status & 0xF0) not in LOG_SUPPRESS_TYPES


def _hint(message):
    """Show feedback in the FL Studio hint bar (bottom-left of the UI).

    Every user action routes through here so the player always gets on-screen
    confirmation of what the controller just did.
    """
    ui.setHintMsg("MPK249: " + str(message))


def _describe_event(event):
    """Return a compact human-readable string for an inbound MIDI event."""
    if event.sysex:
        return ("port=%d SYSEX %s"
                % (event.port,
                   " ".join("%02X" % b for b in event.sysex)))
    return ("port=%d status=0x%02X (type=0x%02X chan=%d) data1=%d data2=%d"
            % (event.port, event.status, event.status & 0xF0,
               event.status & 0x0F, event.data1, event.data2))


def _mmc_name(command):
    """Human-readable name for an MMC command byte (for logging)."""
    return {
        MMC_STOP: "STOP",
        MMC_PLAY: "PLAY",
        MMC_DEFERRED_PLAY: "DEFERRED_PLAY",
        MMC_FAST_FORWARD: "FAST_FORWARD",
        MMC_REWIND: "REWIND",
        MMC_RECORD_STROBE: "RECORD_STROBE",
        MMC_RECORD_EXIT: "RECORD_EXIT",
        MMC_PAUSE: "PAUSE",
    }.get(command, "UNKNOWN(0x%02X)" % command)


# =============================================================================
# HANDLER: TRANSPORT  (MMC over SysEx)
# =============================================================================
def _handle_mmc(event):
    """Parse an MMC SysEx frame and drive FL Studio transport.

    Expected frame layout (indices):
        0: 0xF0  SysEx start
        1: 0x7F  universal real-time
        2: ----  device id (0x7F = all devices)
        3: 0x06  MMC command sub-id
        4: ----  the actual command byte we care about
       -1: 0xF7  SysEx end

    Returns True if the message was recognised and handled.
    """
    data = event.sysex
    # Defensive: must be a well-formed MMC frame before we index into it.
    if not data or len(data) < 6:
        return False
    if data[0] != SYSEX_START or data[1] != SYSEX_UNIVERSAL_RT:
        return False
    if data[3] != SYSEX_MMC_SUBID:
        return False

    command = data[4]
    _log("MMC decoded: %s (cmd byte 0x%02X) on port %d"
         % (_mmc_name(command), command, event.port))

    # During the verification phase we only identify the message; we do not act.
    if CAPTURE_ONLY:
        return True

    # Map the MMC command to an FL Studio global transport action. Using
    # globalTransport() (rather than transport.start()/stop()) makes the buttons
    # behave exactly like FL's own transport buttons, including correct toggling.
    if command == MMC_PLAY or command == MMC_DEFERRED_PLAY:
        transport.globalTransport(midi.FPT_Play, 1, event.pmeFlags)
        _hint("Play")
    elif command == MMC_STOP:
        transport.globalTransport(midi.FPT_Stop, 1, event.pmeFlags)
        _hint("Stop")
    elif command == MMC_RECORD_STROBE:
        transport.globalTransport(midi.FPT_Record, 1, event.pmeFlags)
        _hint("Record")
    elif command == MMC_RECORD_EXIT:
        transport.globalTransport(midi.FPT_Record, 1, event.pmeFlags)
        _hint("Record off")
    elif command == MMC_FAST_FORWARD:
        transport.globalTransport(midi.FPT_FFwd, 1, event.pmeFlags)
        _hint("Fast forward")
    elif command == MMC_REWIND:
        transport.globalTransport(midi.FPT_Rewind, 1, event.pmeFlags)
        _hint("Rewind")
    elif command == MMC_PAUSE:
        transport.globalTransport(midi.FPT_Play, 1, event.pmeFlags)
        _hint("Pause")
    else:
        _log("Unhandled MMC command: 0x%02X" % command)
        return False

    return True


# =============================================================================
# HANDLER: PADS  (stubbed -- awaiting confirmed note map)
# =============================================================================
def _handle_pad(event):
    """Handle a pad Note On/Off (feedback + bank tracking, then pass through).

    Pads send Note On/Off on channel 10 across four banks of 16 contiguous
    notes (A:36-51, B:52-67, C:68-83, D:84-99). We identify the bank + pad from
    the note number, show a hint, and remember the active bank. The note is then
    PASSED THROUGH (we return False so FL still routes it to the selected
    channel) -- select an FPC or any drum instrument and the pads trigger it.

    Returns False always: this handler observes/annotates but never consumes the
    note, so playing remains in FL's hands. Keyboard keys (which are also Note
    messages, but on a different channel) are ignored here via the channel check.
    """
    # Only the pad channel (10) counts -- keyboard keys are Notes too, on ch 1.
    if (event.status & 0x0F) != (PAD_MIDI_CHANNEL - 1):
        return False
    note = event.data1
    if note < PAD_BANK_A_BASE or note > PAD_LAST_NOTE:
        return False  # out of pad range -- leave it alone

    # Feedback + bank tracking only on the strike (Note On with velocity > 0).
    if (event.status & 0xF0) == midi.MIDI_NOTEON and event.data2 > 0:
        offset = note - PAD_BANK_A_BASE
        bank = offset // PADS_PER_BANK
        pad = offset % PADS_PER_BANK
        STATE["pad_bank"] = bank
        _hint("Pad %s%02d  (note %d, vel %d)"
              % (BANK_NAMES[bank], pad + 1, note, event.data2))

    return False


# =============================================================================
# HANDLER: TRANSPORT  (Control Change -- the real hardware path)
# =============================================================================
# Each transport button maps to a small action function. globalTransport() is
# used for play/stop/record/loop so the buttons behave exactly like FL's own
# transport buttons (correct toggling). Forward/Back jump song markers, which is
# a safe single-shot action -- important because these buttons send no release
# message, so a "hold to scrub" action (FPT_FastForward/Rewind) would run away.
def _t_play(event):
    transport.globalTransport(midi.FPT_Play, 1, event.pmeFlags)


def _t_stop(event):
    transport.globalTransport(midi.FPT_Stop, 1, event.pmeFlags)


def _t_record(event):
    transport.globalTransport(midi.FPT_Record, 1, event.pmeFlags)


def _t_loop(event):
    transport.globalTransport(midi.FPT_LoopRecord, 1, event.pmeFlags)


def _t_forward(event):
    transport.markerJumpJog(1)


def _t_back(event):
    transport.markerJumpJog(-1)


# CC number -> (display name, action function).
TRANSPORT_CC_ACTIONS = {
    TRANSPORT_CC_PLAY: ("Play", _t_play),
    TRANSPORT_CC_STOP: ("Stop", _t_stop),
    TRANSPORT_CC_RECORD: ("Record", _t_record),
    TRANSPORT_CC_LOOP: ("Loop toggle", _t_loop),
    TRANSPORT_CC_FORWARD: ("Forward (next marker)", _t_forward),
    TRANSPORT_CC_BACK: ("Back (prev marker)", _t_back),
}


def _handle_transport_cc(event):
    """Drive transport from a transport-button CC. Returns True if consumed."""
    action = TRANSPORT_CC_ACTIONS.get(event.data1)
    if action is None:
        return False  # not a transport CC -- let the knob/fader handler try

    name, fn = action
    # Fire only on press. Any release (value 0) is consumed silently so it
    # never leaks through to other handlers or FL's generic linking.
    if event.data2 != TRANSPORT_CC_PRESS_VALUE:
        return True

    try:
        fn(event)
        _hint(name)
        _log("Transport: %s (CC %d)" % (name, event.data1))
    except Exception as exc:  # defensive: a bad API call must not kill input
        _log("Transport action FAILED for %s (CC %d): %s"
             % (name, event.data1, exc))
    return True


# =============================================================================
# HANDLER: KNOBS / FADERS  (stubbed -- awaiting confirmed CC map)
# =============================================================================
def _handle_cc(event):
    """Route Control Change messages.

    Transport buttons (verified) arrive here as CC on channel 1 and are consumed
    by _handle_transport_cc. Everything else is intentionally NOT handled so it
    passes straight through to FL Studio:

      * The right wheel is the Mod wheel -> CC 1 (verified 2026-06-17). Leaving
        it unhandled lets FL apply modulation natively, which is what users
        expect. (If a user wants the mod wheel mapped to a specific param, that
        is a deliberate future addition, not a default.)
      * Knob/fader CCs are not yet mapped (awaiting hardware capture).
    """
    if _handle_transport_cc(event):
        return True
    # Mod wheel (CC 1) and all other CCs fall through untouched -- see the note
    # in the CONFIG block on why the wheels are not forwarded. Knob/fader
    # mapping is still to be implemented.
    return False


# =============================================================================
# FL STUDIO LIFECYCLE CALLBACKS
# =============================================================================
def OnInit():
    """Called once when the script is loaded / FL Studio starts."""
    _log("OnInit - device: %s, FL version: %s"
         % (device.getName(), general.getVersion()))
    _hint("MPK249 script loaded")


def OnDeInit():
    """Called once when the script is unloaded / FL Studio closes."""
    _log("OnDeInit")


def OnMidiIn(event):
    """Lowest-level inbound hook -- called for every message before OnMidiMsg.

    Used here as a raw sniffer so we can see EXACTLY what arrives on each port,
    even messages FL Studio might otherwise route or filter. We never set
    event.handled here, so normal dispatch in OnMidiMsg still runs.
    """
    if _should_log(event):
        _log("RAW " + _describe_event(event))


def OnSysEx(event):
    """Dedicated SysEx callback.

    Some FL Studio versions deliver SysEx (and therefore MMC) here rather than
    through OnMidiMsg. We route it to the same MMC parser so transport works
    regardless of which path FL uses.
    """
    _log("SYX " + _describe_event(event))
    if _handle_mmc(event) and not CAPTURE_ONLY:
        event.handled = True


def OnMidiMsg(event):
    """Primary inbound MIDI dispatcher.

    Order of dispatch:
        1. SysEx  -> transport (MMC)
        2. Note   -> pads (stub)
        3. CC     -> knobs / faders (stub)
    Anything we explicitly handle is marked event.handled so FL Studio does not
    also act on it. Unhandled messages pass through untouched (defensive: keys,
    pitch bend, aftertouch etc. keep working normally). While CAPTURE_ONLY is on
    we never set event.handled -- we only observe.
    """
    if _should_log(event):
        _log("MSG " + _describe_event(event))

    # 1) SysEx / MMC transport.
    if event.sysex:
        if _handle_mmc(event) and not CAPTURE_ONLY:
            event.handled = True
        return

    status_type = event.status & 0xF0  # strip channel nibble

    # 2) Note messages -> pads.
    if status_type in (midi.MIDI_NOTEON, midi.MIDI_NOTEOFF):
        if _handle_pad(event) and not CAPTURE_ONLY:
            event.handled = True
        return

    # 3) Control Change -> knobs / faders.
    if status_type == midi.MIDI_CONTROLCHANGE:
        if _handle_cc(event) and not CAPTURE_ONLY:
            event.handled = True
        return

    # Everything else is left untouched for FL Studio. Keys pass through to the
    # selected channel natively. Pitch bend (0xE0), mod wheel, and aftertouch are
    # intentionally NOT handled here -- see the note in the CONFIG block.


def OnRefresh(flags):
    """Called when FL Studio state changes (used later for LED feedback)."""
    pass


def OnIdle():
    """Called frequently while idle (used later for animations/blinking)."""
    pass
