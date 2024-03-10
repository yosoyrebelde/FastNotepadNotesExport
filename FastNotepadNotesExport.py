r"""
This parses 'Fast Notepad' android app notes backup file and exports all notes to '.txt' files.

Notes dump file format:
blabla#{"index":"csv_string"}{[!*|@]}{"folders":"Folder1\nFolder2"}{[!*|@]}{"bla":"bla","_file_index":"text"}

Index csv string format:
^!file_index_1;folder_name;;;;;;;;file_name^!file_index_2;folder_name;;;;;;;;file_name_2^!
Folder name can be empty; can be ' ' if the note is in the trash bin.
There can be more than one '^!' between lines.
"""

import os
import json
import csv
import shutil
import re
import random
import string
import tkinter.filedialog

INITIAL_DIR = os.path.dirname(os.path.abspath(__file__))
TRASH_FOLDER_NAME = "Recycle-bin"
NOTE_FILE_EXTENSION = ".txt"

# Dump file special things
JSON_OBJECTS_DIVIDER = r"{[!*|@]}"
TRASH_FOLDER_CSV_NAME = " "

CSV_ROW_LENGTH = 10

CSV_COL_FILE_INDEX = 0
CSV_COL_FOLDER_NAME = 1
CSV_COL_FILE_NAME = 9

# File name sanitizing things
FILE_NAME_MAX_LEN = 50
RE_RESTRICTED_CHARS = re.compile(r"[^\w. _-]")
RESTRICTED_NAMES = [
    'CON', 'PRN', 'AUX', 'NUL','COM0', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5',
    'COM6', 'COM7', 'COM8', 'COM9', 'COM¹', 'COM²', 'COM³', 'LPT0', 'LPT1', 'LPT2',
    'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9', 'LPT¹', 'LPT²', 'LPT³',
]

# Folder path created by the script, empty string means no files created yet.
created_path = ""

class FastNotepadParserError(Exception):
    pass

def full_path(name, folder, is_dir=False):
    """ Joins path segments, adds file extension."""
    if is_dir:
        return os.path.join(folder, name)
    return f"{os.path.join(folder, name)}{NOTE_FILE_EXTENSION}"

def sanitize_name(name, folder, is_dir=False):
    """ Returns a valid name for the file/folder."""

    def gen_unique_name(name, folder, is_dir):
        """ Makes a file/folder name unique within its folder."""
        characters = string.digits
        while os.path.exists(full_path(name, folder, is_dir)):
            name += random.choice(characters)
        return name

    # Remove restricted characters
    name = RE_RESTRICTED_CHARS.sub(repl='', string=name)

    # Cut file name length
    name = name[:FILE_NAME_MAX_LEN]

    # Remove whitespaces on start/end
    name = name.strip()

    # Check if the name reserved
    if name.upper() in RESTRICTED_NAMES:
        name = ''

    # Check if the name is empty
    if name == '':
        name = '_'

    # Check if the name is not unique
    if os.path.exists(full_path(name, folder, is_dir)):
        name = gen_unique_name(name, folder, is_dir)

    return name

def get_json_objects(file_path):
    """ Returns json objects from the notes dump as dicts."""

    def try_to_find(string, substring, rfind=False):
        if(rfind):
            found = string.rfind(substring)
        else:
            found = string.find(substring)
        if(found) == -1:
            raise FastNotepadParserError("Error: Couldn't find expected data. Possibly wrong file.")
        return found

    def check_json_objects(index_json, folders_json, content_json):
        all_checks_ok = True
        all_checks_ok = all_checks_ok and ("index" in index_json)
        all_checks_ok = all_checks_ok and ("folders" in folders_json)
        if not all_checks_ok:
            raise FastNotepadParserError("Error: Couldn't find expected data. Possibly wrong file.")

    with open(file_path, 'r', encoding='utf-8') as file:
        raw_string = file.read()

    # Get the 'index' object
    index_start = try_to_find(raw_string, '{')
    index_end = try_to_find(raw_string, JSON_OBJECTS_DIVIDER)

    # Get the 'folders' object
    folders_start = index_end + len(JSON_OBJECTS_DIVIDER)
    folders_end = try_to_find(raw_string, JSON_OBJECTS_DIVIDER, rfind=True)

    # Get the content object
    content_start = folders_end + len(JSON_OBJECTS_DIVIDER)

    # Load jsons
    try:
        index_json = json.loads(raw_string[index_start:index_end])
        folders_json = json.loads(raw_string[folders_start:folders_end])
        content_json = json.loads(raw_string[content_start:])
    except json.decoder.JSONDecodeError as e:
        raise FastNotepadParserError(f"Error: Couldn't find expected data. Possibly wrong file. JSON load error: {e}")

    check_json_objects(index_json, folders_json, content_json)
    return index_json, folders_json, content_json

def create_folder(name, folder_path):
    """ Creates a new folder inside the `folder_path`. Returns the created path."""
    valid_folder_name = sanitize_name(name, folder_path, is_dir=True)
    valid_folder_path = full_path(valid_folder_name, folder_path, is_dir=True)
    os.mkdir(valid_folder_path)
    return valid_folder_path

def create_folders(folders_json, folder_path):
    """ Creates folders that are in the dump file.
    Returns dict {"folder_name_from_dump": "created_folder_path",}
    """
    global created_path

    if os.path.exists(folder_path):
        raise FastNotepadParserError(f"Error: Folder \"{folder_path}\" already exists!")

    # Create the parent folder
    os.mkdir(folder_path)
    created_path = folder_path
    
    # Get folder names from the notes dump
    folder_list = folders_json['folders'].split('\n')

    folder_paths = dict()

    # Create folders
    for folder_name in folder_list:
        valid_folder_name = sanitize_name(folder_name, folder_path, is_dir=True)
        valid_folder_path = full_path(valid_folder_name, folder_path, is_dir=True)
        os.mkdir(valid_folder_path)
        folder_paths[folder_name] = valid_folder_path

    # Create trash folder
    trash_folder_valid_name = create_folder(TRASH_FOLDER_NAME, folder_path)
    folder_paths[TRASH_FOLDER_CSV_NAME] = trash_folder_valid_name

    return folder_paths

def parse_csv(csv_string):
    """ Parses the csv string.
    Returns list: [{'index': 'bla', 'folder': 'bla', 'name': 'bla'},]"""
    result = list()
    csv_reader = csv.reader(csv_string.split('^!'), delimiter=';')
    for csv_row in csv_reader:

        # Handle duplicated csv endline symbols
        if len(csv_row) == 0:
            continue

        # Parse csv row

        if len(csv_row) != CSV_ROW_LENGTH:
            raise FastNotepadParserError("Error: Wrong 'index' data.")

        file_index = f"_{csv_row[CSV_COL_FILE_INDEX]}" # with '_' prefix
        file_folder = csv_row[CSV_COL_FOLDER_NAME]
        file_name = csv_row[CSV_COL_FILE_NAME]

        result.append({
            'index': file_index,
            'folder': file_folder,
            'name': file_name,
        })

    return result

def create_files(index_json, folders_json, content_json, folder_path):
    """ Writes notes from the dump."""

    # Create_folders
    folder_paths = create_folders(folders_json, folder_path)
    # Parse files index
    files_index = parse_csv(index_json['index'])

    # Save the notes
    for file_data in files_index:

        if file_data['folder'] == "":
            dir_to_write_file = folder_path
        else:
            dir_to_write_file = folder_paths[file_data['folder']]

        # Sanitize file name
        file_name = sanitize_name(file_data['name'] , dir_to_write_file)
        # Get current note path
        file_path = full_path(file_name, dir_to_write_file)

        # Write the note
        with open(file_path, 'w', encoding='utf-8') as file:

            if file_data['index'] not in content_json:
                raise FastNotepadParserError("Error: Couldn't find note's text!")

            file.write(content_json[file_data['index']])

def parse_file(file_path):
    """ Parses notes dump file and writes notes from the dump."""
    index_json, folders_json, content_json = get_json_objects(file_path)
    folder_to_save_notes = f"{file_path}_parsed"
    create_files(index_json, folders_json, content_json, folder_to_save_notes)

def cleanup():
    """ Removes the parsed results folder.
    Should be called if the parse operation cannot be completed successfully.
    """
    if created_path == "":
        return
    if os.path.exists(created_path):
        shutil.rmtree(created_path)

def get_file_from_user():
    """ Opens a dialog, returns file path user selected."""
    file = tkinter.filedialog.askopenfilename(title="Choose a Notepad backup file", initialdir=INITIAL_DIR)
    return file

if __name__ == "__main__":

    try:
        file = get_file_from_user()
        if file != "":
            parse_file(file)

    except FastNotepadParserError as e:
        cleanup()
        print(e)

    except:
        cleanup()
        raise
