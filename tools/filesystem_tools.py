from agents import function_tool

####################
# Filesystem tools #
####################
from .utils.filesystem import (
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
def list_files(relative_path: str = "") -> list[str]:
    """
    List files and directories in the filesystem at the given relative path.

    Args:
        relative_path: Relative path within the filesystem (default: root)

    Returns:
        List of file and directory names
    """
    return list_files_in_sandbox(relative_path)


@function_tool
def read_file(relative_path: str) -> str:
    """
    Read the content of a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem

    Returns:
        Content of the file as a string
    """
    return read_file_in_sandbox(relative_path)


@function_tool
def write_file(relative_path: str, content: str) -> str:
    """
    Write content to a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem
        content: Content to write to the file

    Returns:
        Success message
    """
    write_file_in_sandbox(relative_path, content)
    return f"Successfully wrote to {relative_path}"


@function_tool
def create_directory(relative_path: str) -> str:
    """
    Create a directory in the filesystem.

    Args:
        relative_path: Relative path to the directory within the filesystem

    Returns:
        Success message
    """
    create_directory_in_sandbox(relative_path)
    return f"Successfully created directory {relative_path}"


@function_tool
def delete_file(relative_path: str) -> str:
    """
    Delete a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem

    Returns:
        Success message
    """
    delete_file_in_sandbox(relative_path)
    return f"Successfully deleted file {relative_path}"


@function_tool
def delete_directory(relative_path: str) -> str:
    """
    Delete a directory in the filesystem (must be empty).

    Args:
        relative_path: Relative path to the directory within the filesystem

    Returns:
        Success message
    """
    delete_directory_in_sandbox(relative_path)
    return f"Successfully deleted directory {relative_path}"


@function_tool
def move_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Move a file within the filesystem.

    Args:
        src_relative_path: Relative path to the source file
        dst_relative_path: Relative path to the destination

    Returns:
        Success message
    """
    move_file_in_sandbox(src_relative_path, dst_relative_path)
    return f"Successfully moved {src_relative_path} to {dst_relative_path}"


@function_tool
def copy_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Copy a file within the filesystem.

    Args:
        src_relative_path: Relative path to the source file
        dst_relative_path: Relative path to the destination

    Returns:
        Success message
    """
    copy_file_in_sandbox(src_relative_path, dst_relative_path)
    return f"Successfully copied {src_relative_path} to {dst_relative_path}"


@function_tool
def edit_file_section(
    relative_path: str, original_section: str, new_content: str
) -> str:
    """
    Edit a specific section of a file in the filesystem by replacing the original_section with new_content.

    Args:
        relative_path: Relative path to the file within the filesystem
        original_section: The exact text section to replace
        new_content: The new content to replace the original section with

    Returns:
        Success message
    """
    edit_file_section_in_sandbox(relative_path, original_section, new_content)
    return f"Successfully edited section in {relative_path}"


@function_tool
def append_to_file(relative_path: str, content: str) -> str:
    """
    Append content to a file in the filesystem without overwriting existing content.

    Args:
        relative_path: Relative path to the file within the filesystem
        content: Content to append to the file

    Returns:
        Success message
    """
    append_to_file_in_sandbox(relative_path, content)
    return f"Successfully appended to {relative_path}"
