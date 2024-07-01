import os
import tarfile
import tempfile
import zipfile
from typing import List

from git import Repo

excluded_folders = ['node_modules', 'venv', 'vendor', '.git', '.idea']
supported_extensions = [
    # Text Files
    ".txt", ".csv", ".json", ".xml",

    # Spreadsheet Files
    ".xls", ".xlsx",

    # Document Files
    ".doc", ".docx", ".pdf",

    # Presentation Files
    ".ppt", ".pptx",

    # Image Files
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",

    # Code Files
    ".py", ".java", ".js", ".html", ".css", ".cpp", ".c", ".rb", ".php",

    # Audio Files
    ".mp3", ".wav",

    # Video Files
    ".mp4", ".avi", ".mkv"
]


def sanitize_file_name(file_path: str) -> str:
    new_file_path = file_path
    try:
        if os.path.basename(file_path).index('.') < 1:
            new_file_path += '.txt'
            os.rename(file_path, new_file_path)
    except ValueError as e:
        new_file_path += '.txt'
        os.rename(file_path, new_file_path)
    return new_file_path


def is_file_extension_supported(file_path: str) -> bool:
    for extension in supported_extensions:
        if file_path.endswith(extension):
            return True

    return False


def extract_zip(file_path: str, to_folder: str) -> List[str]:
    """
    Extracts files from a zip archive.

    Parameters:
        file_path (str): The path to the zip file.
        to_folder (str): Path where should be files extracted

    Returns:
        List[str]: A list of paths to the extracted files.
    """
    extracted_files = []
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        temp_dir = tempfile.mkdtemp('zip', 'extracted', to_folder)
        zip_ref.extractall(temp_dir)
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in excluded_folders]
            for file in files:
                extracted_files.append(sanitize_file_name(os.path.join(root, file)))
    return extracted_files


def git_clone(repo_url: str, to_folder: str) -> List[str]:
    """
    Clones a Git repository to a specified directory.

    Parameters:
        repo_url (str): The URL of the repository to clone.
        to_folder (str): Path where should be git cloned into.
    """
    cloned_files = []
    temp_dir = tempfile.mkdtemp('git', 'cloned', to_folder)
    try:
        Repo.clone_from(repo_url, temp_dir)
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in excluded_folders]
            for file in files:
                cloned_files.append(sanitize_file_name(os.path.join(root, file)))
    except Exception as e:
        print(f"Error cloning repository: {e}")
    finally:
        print(f"Repository cloned into {temp_dir}")
    return cloned_files


def extract_tar(file_path: str, to_folder: str) -> List[str]:
    """
    Extracts files from a tar.gz archive.

    Parameters:
        file_path (str): The path to the tar.gz file.

    Returns:
        List[str]: A list of paths to the extracted files.
    """
    extracted_files = []
    with tarfile.open(file_path, 'r:gz') as tar_ref:
        temp_dir = tempfile.mkdtemp('tar', 'extracted', to_folder)
        tar_ref.extractall(temp_dir)
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d not in excluded_folders]
            for file in files:
                extracted_files.append(sanitize_file_name(os.path.join(root, file)))
    return extracted_files
