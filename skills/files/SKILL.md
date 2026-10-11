---
name: files
description: Read, write, edit, search and list the user's files and notes (in Omen's sandbox folder).
keywords: [file, files, folder, directory, note, notes, txt, md, markdown, document, save, write, edit, append, delete, rename, grep]
---
Paths are relative to the sandbox folder, e.g. `notes/todo.md`.
- When the user gives a path, use it directly. `write_file` creates missing folders, so don't list folders first.
- To find which file mentions something, call `grep` once over everything (path ".").
- To change part of a file: `read_file`, then `edit_file` with text copied exactly from it.
- To add to a file: `append_to_file`. To create or replace a whole file: `write_file`.
- Deleting or overwriting asks the user first; if they say no, tell them nothing changed.
