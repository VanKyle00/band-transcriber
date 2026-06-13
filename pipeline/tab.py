"""MIDI -> ASCII tablature.

A deterministic, dependency-light fret assigner: greedily place each note on the
string/fret that keeps the lowest fret while staying near the previous hand
position. Honest about limits — it has no notion of idiomatic fingering, so guitar
output is "best-effort" (bass, being monophonic, comes out clean). A learned model
(e.g. open-fret) can replace `assign_columns` later without touching the renderer.
"""
from __future__ import annotations

MAX_FRET = 24
_PITCH_LETTERS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _pitch_letter(midi: int) -> str:
    return _PITCH_LETTERS[midi % 12]


def _placements(pitch: int, tuning: list[int]) -> list[tuple[int, int]]:
    """All (string_index, fret) positions that can sound `pitch` on this tuning."""
    out = []
    for idx, open_pitch in enumerate(tuning):
        fret = pitch - open_pitch
        if 0 <= fret <= MAX_FRET:
            out.append((idx, fret))
    return out


def _group_columns(notes, epsilon: float = 0.06) -> list[list[int]]:
    """Group notes that start within `epsilon` seconds into chord columns.

    notes: iterable of (start_seconds, pitch). Returns time-ordered columns,
    each a list of pitches.
    """
    ordered = sorted(notes, key=lambda n: n[0])
    columns: list[list[int]] = []
    current: list[int] = []
    anchor: float | None = None
    for start, pitch in ordered:
        if anchor is None or start - anchor <= epsilon:
            current.append(pitch)
            anchor = start if anchor is None else anchor
        else:
            columns.append(current)
            current = [pitch]
            anchor = start
    if current:
        columns.append(current)
    return columns


def assign_columns(columns: list[list[int]], tuning: list[int]) -> list[dict[int, int]]:
    """Assign each chord column to {string_index: fret}.

    Low pitches claim low strings first; ties break toward the previous hand
    position to reduce leaps. Unplayable notes (out of range / no free string)
    are dropped rather than faked.
    """
    result: list[dict[int, int]] = []
    prev_pos: float | None = None
    for col in columns:
        used: set[int] = set()
        placements: dict[int, int] = {}
        for pitch in sorted(col):
            cands = [(i, f) for i, f in _placements(pitch, tuning) if i not in used]
            if not cands:
                continue

            def cost(c: tuple[int, int]) -> tuple[float, int]:
                _, fret = c
                dist = abs(fret - prev_pos) if prev_pos is not None else 0.0
                return (dist, fret)

            idx, fret = min(cands, key=cost)
            used.add(idx)
            placements[idx] = fret
        if placements:
            prev_pos = sum(placements.values()) / len(placements)
        result.append(placements)
    return result


def render_tab(placements: list[dict[int, int]], tuning: list[int],
               columns_per_line: int = 16) -> str:
    """Render assigned columns as ASCII tab. Highest-pitched string on top."""
    n = len(tuning)
    order = sorted(range(n), key=lambda i: tuning[i], reverse=True)  # high string first
    labels = [_pitch_letter(tuning[i]).ljust(2) for i in order]

    blocks: list[str] = []
    for start in range(0, max(len(placements), 1), columns_per_line):
        chunk = placements[start:start + columns_per_line]
        rows = {i: f"{labels[r]}|" for r, i in enumerate(order)}
        for col in chunk:
            width = max([len(str(f)) for f in col.values()] + [1])
            for i in order:
                cell = str(col[i]).rjust(width, "-") if i in col else "-" * width
                rows[i] += "-" + cell + "-"
        block = "\n".join(rows[i] + "|" for i in order)
        blocks.append(block)
    return "\n\n".join(blocks)


def notes_to_tab(notes, tuning: list[int], columns_per_line: int = 16) -> str:
    """Full pipeline: (start, pitch) notes -> ASCII tab string."""
    columns = _group_columns(notes)
    placements = assign_columns(columns, tuning)
    return render_tab(placements, tuning, columns_per_line)


def midi_to_ascii_tab(midi_path: str, tuning: list[int]) -> str:
    """Read a MIDI file and produce ASCII tab. Requires pretty_midi at runtime."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = [
        (note.start, note.pitch)
        for inst in pm.instruments if not inst.is_drum
        for note in inst.notes
    ]
    return notes_to_tab(notes, tuning)
