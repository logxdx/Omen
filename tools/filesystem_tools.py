from agents import function_tool

####################
# Filesystem tools #
####################
from tools.utils.filesystem import (
    list_files_in_sandbox,
    read_file_in_sandbox,
    write_file_in_sandbox,
    create_directory_in_sandbox,
    delete_file_in_sandbox,
    delete_directory_in_sandbox,
    move_file_in_sandbox,
    copy_file_in_sandbox,
    edit_file_section_in_sandbox,
    append_to_file_in_sandbox,
)


@function_tool
def list_files(relative_path: str = "") -> str:
    """
    List files and directories.

    Args:
        relative_path: path relative to root

    Returns:
        String containing newline-separated list of file and directory names, or error message
    """
    try:
        files = list_files_in_sandbox(relative_path)
        return files
    except Exception as e:
        return f"Error listing files in '{relative_path}': {str(e)}"


@function_tool
def read_file(relative_path: str) -> str:
    """
    Read the content of a file.

    Args:
        relative_path: file path relative to root

    Returns:
        Content of the file as a string, or error message
    """
    try:
        return read_file_in_sandbox(relative_path)
    except Exception as e:
        return f"Error reading file '{relative_path}': {str(e)}"


@function_tool
def write_file(relative_path: str, content: str) -> str:
    """
    Write content to a file.

    Args:
        relative_path: file path relative to root
        content: Content to write to the file

    Returns:
        Success message or error message
    """
    try:
        write_file_in_sandbox(relative_path, content)
        return f"Successfully wrote to {relative_path}"
    except Exception as e:
        return f"Error writing to file '{relative_path}': {str(e)}"


@function_tool
def create_directory(relative_path: str) -> str:
    """
    Create a directory.

    Args:
        relative_path: path to the directory relative to root

    Returns:
        Success message or error message
    """
    try:
        create_directory_in_sandbox(relative_path)
        return f"Successfully created directory {relative_path}"
    except Exception as e:
        return f"Error creating directory '{relative_path}': {str(e)}"


@function_tool
def delete_file(relative_path: str) -> str:
    """
    Delete a file.

    Args:
        relative_path: file path relative to root

    Returns:
        Success message or error message
    """
    try:
        delete_file_in_sandbox(relative_path)
        return f"Successfully deleted file {relative_path}"
    except Exception as e:
        return f"Error deleting file '{relative_path}': {str(e)}"


@function_tool
def delete_directory(relative_path: str) -> str:
    """
    Delete a directory (must be empty).

    Args:
        relative_path: Directory path relative to root

    Returns:
        Success message or error message
    """
    try:
        delete_directory_in_sandbox(relative_path)
        return f"Successfully deleted directory {relative_path}"
    except Exception as e:
        return f"Error deleting directory '{relative_path}': {str(e)}"


@function_tool
def move_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Move a file.

    Args:
        src_relative_path: source file path relative to root
        dst_relative_path: destination file path relative to root

    Returns:
        Success message or error message
    """
    try:
        move_file_in_sandbox(src_relative_path, dst_relative_path)
        return f"Successfully moved {src_relative_path} to {dst_relative_path}"
    except Exception as e:
        return f"Error moving file from '{src_relative_path}' to '{dst_relative_path}': {str(e)}"


@function_tool
def copy_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Copy a file.

    Args:
        src_relative_path: source file path relative to root
        dst_relative_path: destination file path relative to root

    Returns:
        Success message or error message
    """
    try:
        copy_file_in_sandbox(src_relative_path, dst_relative_path)
        return f"Successfully copied {src_relative_path} to {dst_relative_path}"
    except Exception as e:
        return f"Error copying file from '{src_relative_path}' to '{dst_relative_path}': {str(e)}"


@function_tool
def edit_file_section(
    relative_path: str, original_section: str, new_content: str
) -> str:
    """
    Edit a specific section of a file by replacing the original_section with new_content.

    Args:
        relative_path: file path relative to root
        original_section: The exact text section to replace
        new_content: The new content to replace the original section with

    Returns:
        Success message or error message
    """
    try:
        edit_file_section_in_sandbox(relative_path, original_section, new_content)
        return f"Successfully edited section in {relative_path}"
    except Exception as e:
        return f"Error editing section in file '{relative_path}': {str(e)}"


@function_tool
def append_to_file(relative_path: str, content: str) -> str:
    """
    Append content to a file without overwriting existing content.

    Args:
        relative_path: file path relative to root
        content: Content to append to the file

    Returns:
        Success message or error message
    """
    try:
        append_to_file_in_sandbox(relative_path, content)
        return f"Successfully appended to {relative_path}"
    except Exception as e:
        return f"Error appending to file '{relative_path}': {str(e)}"


FILESYSTEM_TOOLS = [
    list_files,
    read_file,
    write_file,
    create_directory,
    delete_file,
    delete_directory,
    move_file,
    copy_file,
    edit_file_section,
    append_to_file,
]
