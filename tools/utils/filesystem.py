import os
import shutil
from pathlib import Path

SANDBOX_PATH = Path(__file__).resolve().parent.parent.parent / 'root' / 'files'
SANDBOX_PATH.mkdir(parents=True, exist_ok=True)

def list_files_in_sandbox(relative_path=""):
    """List files and directories in the sandbox at the given relative path."""
    full_path = SANDBOX_PATH / relative_path
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Path does not exist: {relative_path}")
    if not os.path.isdir(full_path):
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")
    return os.listdir(full_path)

def read_file_in_sandbox(relative_path):
    """Read the content of a file in the sandbox."""
    full_path = SANDBOX_PATH / relative_path
    if not full_path.is_file():
        raise FileNotFoundError(f"File does not exist: {relative_path}")
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file_in_sandbox(relative_path, content):
    """Write content to a file in the sandbox."""
    full_path = SANDBOX_PATH / relative_path
    # Ensure the directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

def create_directory_in_sandbox(relative_path):
    """Create a directory in the sandbox."""
    full_path = SANDBOX_PATH / relative_path
    full_path.mkdir(parents=True, exist_ok=True)

def delete_file_in_sandbox(relative_path):
    """Delete a file in the sandbox."""
    full_path = SANDBOX_PATH / relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"File does not exist: {relative_path}")
    if full_path.is_dir():
        raise IsADirectoryError(f"Path is a directory: {relative_path}")
    full_path.unlink()

def delete_directory_in_sandbox(relative_path):
    """Delete a directory in the sandbox (must be empty)."""
    full_path = SANDBOX_PATH / relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {relative_path}")
    if not full_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")
    full_path.rmdir()

def move_file_in_sandbox(src_relative_path, dst_relative_path):
    """Move a file within the sandbox."""
    src_full_path = SANDBOX_PATH / src_relative_path
    dst_full_path = SANDBOX_PATH / dst_relative_path
    shutil.move(src_full_path, dst_full_path)

def copy_file_in_sandbox(src_relative_path, dst_relative_path):
    """Copy a file within the sandbox."""
    src_full_path = SANDBOX_PATH / src_relative_path
    dst_full_path = SANDBOX_PATH / dst_relative_path
    shutil.copy2(src_full_path, dst_full_path)

def edit_file_section_in_sandbox(relative_path, original_section, new_content):
    """Edit a specific section of a file in the sandbox by replacing the original_section with new_content."""
    full_path = SANDBOX_PATH / relative_path
    if not full_path.is_file():
        raise FileNotFoundError(f"File does not exist: {relative_path}")
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the original section
    pos = content.find(original_section)
    if pos == -1:
        raise ValueError(f"Original section not found in file")
    
    # Replace the section
    new_file_content = content[:pos] + new_content + content[pos + len(original_section):]
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(new_file_content)

def append_to_file_in_sandbox(relative_path, content):
    """Append content to a file in the sandbox without overwriting existing content."""
    full_path = SANDBOX_PATH / relative_path
    # Ensure the directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'a', encoding='utf-8') as f:
        f.write(content)