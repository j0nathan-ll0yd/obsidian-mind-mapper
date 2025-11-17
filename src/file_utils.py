#!/usr/bin/env python3
"""
File Utility Functions for Obsidian Mind Mapper

Provides helper functions for:
- Generating MD5 hashes from PDFs
- Sanitizing titles for Obsidian filenames
- Finding matching PNG files for PDFs
- Date extraction and formatting
"""

import hashlib
import re
import os
from pathlib import Path
from typing import Optional, Tuple


def generate_file_hash(file_path: str, bytes_to_read: int = 8192) -> str:
    """
    Generate an 8-character MD5 hash from the first N bytes of a file.

    Args:
        file_path: Path to the file
        bytes_to_read: Number of bytes to read for hashing (default 8192)

    Returns:
        8-character hash string
    """
    try:
        with open(file_path, 'rb') as f:
            content = f.read(bytes_to_read)
            file_hash = hashlib.md5(content).hexdigest()
            return file_hash[:8]
    except Exception as e:
        raise Exception(f"Failed to generate hash for {file_path}: {str(e)}")


def sanitize_title(title: str, max_length: int = 100) -> str:
    """
    Sanitize a title for use as an Obsidian filename.

    Removes problematic characters for Obsidian: brackets, hashes, pipes, slashes, etc.
    Keeps spaces and other characters.
    Limits length to max_length.

    Args:
        title: The title to sanitize
        max_length: Maximum length of the sanitized title

    Returns:
        Sanitized title string
    """
    # Remove problematic characters for Obsidian
    invalid_chars = r'[\[\]#\^|\\/:?]'
    sanitized = re.sub(invalid_chars, '', title)

    # Remove extra spaces
    sanitized = re.sub(r'\s+', ' ', sanitized)

    # Trim to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip()

    return sanitized.strip()


def find_matching_png(pdf_path: str) -> Optional[str]:
    """
    Find a matching PNG file for a given PDF file.

    For FireShot captures, the PNG and PDF usually have similar names.
    This function tries various matching strategies.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Path to matching PNG file, or None if not found
    """
    pdf_path_obj = Path(pdf_path)
    directory = pdf_path_obj.parent
    pdf_name = pdf_path_obj.stem  # filename without extension

    # Strategy 1: Exact match (same name, different extension)
    exact_match = directory / f"{pdf_name}.png"
    if exact_match.exists():
        return str(exact_match)

    # Strategy 2: For FireShot files, try to match the core title
    # FireShot format: "FireShot Capture NNN - Title - domain.com"
    if "FireShot Capture" in pdf_name:
        # Extract the capture number
        match = re.search(r'FireShot Capture (\d+)', pdf_name)
        if match:
            capture_num = match.group(1)
            # Look for PNG with same capture number
            for png_file in directory.glob(f"FireShot Capture {capture_num}*.png"):
                return str(png_file)

    # Strategy 3: Look for normalized filenames (YYYY-MM-DD|domain|title format)
    if '|' in pdf_name:
        # Try finding PNG with same structure
        exact_match_normalized = directory / f"{pdf_name}.png"
        if exact_match_normalized.exists():
            return str(exact_match_normalized)

    return None


def extract_year_month(date_str: str) -> str:
    """
    Extract YYYY-MM from a date string.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Year-month string in YYYY-MM format
    """
    if not date_str:
        return None

    # Handle YYYY-MM-DD format
    match = re.match(r'(\d{4}-\d{2})', date_str)
    if match:
        return match.group(1)

    return None


def parse_fireshot_filename(filename: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse a FireShot filename to extract metadata.

    FireShot format: "FireShot Capture NNN - Title - domain.com.pdf"

    Args:
        filename: The FireShot filename

    Returns:
        Tuple of (capture_number, title, domain) or None if not a FireShot file
    """
    if "FireShot Capture" not in filename:
        return None

    # Remove extension
    name = Path(filename).stem

    # Pattern: FireShot Capture NNN - Title - domain.com
    pattern = r'FireShot Capture (\d+) - (.+) - ([a-zA-Z0-9.-]+\.[a-zA-Z]+)$'
    match = re.match(pattern, name)

    if match:
        capture_num = match.group(1)
        title = match.group(2)
        domain = match.group(3)
        return (capture_num, title, domain)

    return None


def check_existing_note(lifegames_dir: str, title: str) -> Optional[str]:
    """
    Check if a note with the given title already exists in the Lifegames vault.

    Args:
        lifegames_dir: Path to the Lifegames directory
        title: Sanitized title to check

    Returns:
        Path to existing note if found, None otherwise
    """
    lifegames_path = Path(lifegames_dir)

    # Check in root
    root_note = lifegames_path / f"{title}.md"
    if root_note.exists():
        return str(root_note)

    # Check in Reviewed folder
    reviewed_note = lifegames_path / "Reviewed" / f"{title}.md"
    if reviewed_note.exists():
        return str(reviewed_note)

    return None


if __name__ == "__main__":
    # Simple CLI for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python src/file_utils.py <command> [args]")
        print("Commands:")
        print("  hash <file>              - Generate 8-char hash")
        print("  sanitize <title>         - Sanitize title")
        print("  find-png <pdf>           - Find matching PNG")
        print("  parse-fireshot <filename> - Parse FireShot filename")
        sys.exit(1)

    command = sys.argv[1]

    if command == "hash" and len(sys.argv) == 3:
        file_path = sys.argv[2]
        print(generate_file_hash(file_path))

    elif command == "sanitize" and len(sys.argv) == 3:
        title = sys.argv[2]
        print(sanitize_title(title))

    elif command == "find-png" and len(sys.argv) == 3:
        pdf_path = sys.argv[2]
        result = find_matching_png(pdf_path)
        print(result if result else "No matching PNG found")

    elif command == "parse-fireshot" and len(sys.argv) == 3:
        filename = sys.argv[2]
        result = parse_fireshot_filename(filename)
        if result:
            print(f"Capture: {result[0]}, Title: {result[1]}, Domain: {result[2]}")
        else:
            print("Not a FireShot filename")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
