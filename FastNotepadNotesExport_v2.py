#!/usr/bin/env python3
"""
FastNotepadNotesExport_v2.py

Export notes from a "Fast Notepad" (Android) backup file to individual .txt
files, keeping each note's original timestamp as the file's modification time.

Backup layout handled by this script (observed in 2026 backups):

    <40-char hash>#<JSON object with an "index" string>
    {[!*|@]}<JSON dict>
    {[!*|@]}<JSON dict with the note texts (and scroll positions)>

The "index" string holds one record per note, separated by "^!":

    <note id>;;<color>;<unix timestamp>;;<color>;<n>;;{"reminder":0};<title>

The note texts live in a JSON dict whose keys end with the note id.

Usage:
    python3 FastNotepadNotesExport_v2.py                 # opens a file dialog
    python3 FastNotepadNotesExport_v2.py BACKUP_FILE     # no GUI needed
    python3 FastNotepadNotesExport_v2.py BACKUP_FILE -o OUTPUT_DIR

Works on macOS, Linux and Windows. Python 3.6+; tkinter is only needed for the
file dialog, so passing the path on the command line works without it.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

SECTION_SEPARATOR = "{[!*|@]}"
RECORD_SEPARATOR = "^!"
FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def choose_file():
    """Ask for the backup file with a dialog, or fall back to the terminal."""
    try:
        import tkinter
        import tkinter.filedialog

        root = tkinter.Tk()
        root.withdraw()
        print("Choose a Fast Notepad backup file")
        path = tkinter.filedialog.askopenfilename(title="Choose a Fast Notepad backup file")
        root.destroy()
        return path
    except Exception:
        return input("Path to the backup file: ").strip().strip("'\"")


def parse_index(index):
    """Return ({note_id: title}, {note_id: unix_timestamp}) from the index string."""
    titles, stamps = {}, {}
    for record in index.split(RECORD_SEPARATOR):
        m = re.match(r"([A-Za-z0-9]+);", record)
        if not m:
            continue
        note_id = m.group(1)
        title = re.search(r"\{[^}]*\};(.*)$", record, re.S)
        titles[note_id] = title.group(1).strip() if title else ""
        ts = re.search(r"#[0-9A-Fa-f]{8};(\d{9,13});", record)
        if ts:
            value = int(ts.group(1))
            stamps[note_id] = value / 1000 if value > 10**11 else value  # ms -> s
    return titles, stamps


def load_backup(path):
    """Parse the backup file and return (titles, stamps, bodies)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # Drop the "<hash>#" prefix and read the first JSON object (the index).
    _, sep, rest = text.partition("#")
    if not sep:
        raise ValueError("no '#' separator found")
    first, end = json.JSONDecoder().raw_decode(rest)
    if not isinstance(first, dict) or "index" not in first:
        raise ValueError("no 'index' entry found")

    titles, stamps = parse_index(first["index"])
    if not titles:
        raise ValueError("the index contains no notes")

    # Find the note texts in the remaining JSON sections.
    bodies = {}
    for section in rest[end:].split(SECTION_SEPARATOR):
        section = section.strip()
        if not section:
            continue
        try:
            data = json.loads(section)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if not isinstance(value, str):
                continue
            for candidate in (key, key.rsplit("_", 1)[-1], key[-16:]):
                if candidate in titles:
                    bodies[candidate] = value
                    break
    return titles, stamps, bodies


def safe_filename(title, fallback):
    name = FORBIDDEN_CHARS.sub("_", title).strip(" .")[:80]
    return name or fallback


def export(path, out_dir):
    titles, stamps, bodies = load_backup(path)
    os.makedirs(out_dir, exist_ok=True)

    used = set()
    dated = 0
    for note_id, text in bodies.items():
        title = titles.get(note_id, "")
        if not title:  # untitled note: use its first non-empty line
            title = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        name = safe_filename(title, note_id)
        base, n = name, 2
        while name.lower() in used:
            name = "{} ({})".format(base, n)
            n += 1
        used.add(name.lower())

        file_path = os.path.join(out_dir, name + ".txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        if note_id in stamps:
            os.utime(file_path, (stamps[note_id], stamps[note_id]))
            dated += 1

    print("Notes in index:      {}".format(len(titles)))
    print("Notes exported:      {}".format(len(bodies)))
    print("Timestamps applied:  {}".format(dated))
    if stamps:
        print("Oldest note:         {}".format(datetime.fromtimestamp(min(stamps.values()))))
        print("Newest note:         {}".format(datetime.fromtimestamp(max(stamps.values()))))
    print("Saved to:            {}".format(out_dir))
    missing = len(titles) - len(bodies)
    if missing:
        print("Note: {} index entries had no text (empty notes?).".format(missing))


def main():
    parser = argparse.ArgumentParser(description="Export Fast Notepad backup notes to .txt files.")
    parser.add_argument("backup", nargs="?", help="path to the backup file (opens a dialog if omitted)")
    parser.add_argument("-o", "--output", help="output folder (default: 'exported_notes' next to the backup)")
    args = parser.parse_args()

    path = args.backup or choose_file()
    if not path:
        print("No file chosen.")
        return 1
    path = os.path.abspath(path)
    out_dir = os.path.abspath(args.output) if args.output else os.path.join(os.path.dirname(path), "exported_notes")

    try:
        export(path, out_dir)
    except (OSError, ValueError) as e:
        print("Error: couldn't read this backup ({}). Possibly wrong file.".format(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
