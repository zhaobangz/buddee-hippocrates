"""File management helpers used by the agent tools.

This module provides a `FileManager` class with utilities to organize files
on disk into folders by extension, category, or date. The functions are
designed to be safe (support a `dry_run` mode) and easy to call from the
`Agent` when the user asks the assistant to organize files.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from typing import Dict, Iterable, Optional


DEFAULT_CATEGORIES: Dict[str, Iterable[str]] = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".odt", ".rtf"],
    "Spreadsheets": [".xls", ".xlsx", ".csv"],
    "Presentations": [".ppt", ".pptx"],
    "Audio": [".mp3", ".wav", ".m4a", ".flac"],
    "Video": [".mp4", ".mov", ".avi", ".mkv"],
    "Archives": [".zip", ".tar", ".gz", ".rar"],
    "Code": [".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs"],
}


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _unique_target(target: str) -> str:
    """Return a non-conflicting path by appending a numeric suffix if needed."""
    base, ext = os.path.splitext(target)
    counter = 1
    candidate = target
    while os.path.exists(candidate):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return candidate


class FileManager:
    """Organize files and provide simple file creation utilities.

    Methods are idempotent and support `dry_run` to preview actions.
    """

    def create_file(self, file_name: str, content: str) -> None:
        """Create or overwrite a file with `content`."""
        _ensure_dir(os.path.dirname(os.path.abspath(file_name)) or '.')
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(content)

    def organize_by_extension(self, src_dir: str, dest_dir: Optional[str] = None, dry_run: bool = False) -> Dict[str, str]:
        """Move files from `src_dir` into subfolders by file extension.

        Returns a mapping of source -> destination for files that would be
        moved (or were moved). When `dry_run` is True no filesystem changes
        are made; the mapping is still returned for preview.
        """
        src_dir = os.path.abspath(src_dir)
        if not dest_dir:
            dest_dir = os.path.join(src_dir, 'organized_by_extension')
        dest_dir = os.path.abspath(dest_dir)
        actions: Dict[str, str] = {}

        for entry in os.listdir(src_dir):
            src_path = os.path.join(src_dir, entry)
            if os.path.isdir(src_path):
                continue
            _, ext = os.path.splitext(entry)
            ext = ext.lower() or '.noext'
            folder = ext.lstrip('.')
            target_folder = os.path.join(dest_dir, folder)
            target_path = os.path.join(target_folder, entry)
            target_path = _unique_target(target_path)

            actions[src_path] = target_path
            if not dry_run:
                _ensure_dir(target_folder)
                shutil.move(src_path, target_path)

        return actions

    def organize_by_category(self, src_dir: str, categories: Optional[Dict[str, Iterable[str]]] = None, dest_dir: Optional[str] = None, dry_run: bool = False) -> Dict[str, str]:
        """Organize files into category folders based on extension mapping.

        `categories` maps folder names to iterables of extensions (including
        the leading dot). If omitted `DEFAULT_CATEGORIES` will be used. Files
        that do not match any category are placed into an `Other` folder.
        """
        if categories is None:
            categories = DEFAULT_CATEGORIES
        src_dir = os.path.abspath(src_dir)
        if not dest_dir:
            dest_dir = os.path.join(src_dir, 'organized_by_category')
        dest_dir = os.path.abspath(dest_dir)
        actions: Dict[str, str] = {}

        # Normalize mapping for fast lookup
        ext_map: Dict[str, str] = {}
        for cat, exts in categories.items():
            for e in exts:
                ext_map[e.lower()] = cat

        for entry in os.listdir(src_dir):
            src_path = os.path.join(src_dir, entry)
            if os.path.isdir(src_path):
                continue
            _, ext = os.path.splitext(entry)
            ext = ext.lower()
            category = ext_map.get(ext, 'Other')
            target_folder = os.path.join(dest_dir, category)
            target_path = os.path.join(target_folder, entry)
            target_path = _unique_target(target_path)

            actions[src_path] = target_path
            if not dry_run:
                _ensure_dir(target_folder)
                shutil.move(src_path, target_path)

        return actions

    def organize_by_date(self, src_dir: str, dest_dir: Optional[str] = None, by: str = 'month', dry_run: bool = False) -> Dict[str, str]:
        """Organize files into folders by modification date.

        `by` can be 'year' or 'month'. For 'month' folders are YYYY-MM.
        """
        src_dir = os.path.abspath(src_dir)
        if not dest_dir:
            dest_dir = os.path.join(src_dir, 'organized_by_date')
        dest_dir = os.path.abspath(dest_dir)
        actions: Dict[str, str] = {}

        for entry in os.listdir(src_dir):
            src_path = os.path.join(src_dir, entry)
            if os.path.isdir(src_path):
                continue
            try:
                mtime = os.path.getmtime(src_path)
                dt = datetime.fromtimestamp(mtime)
            except Exception:
                dt = datetime.now()

            if by == 'year':
                folder = f"{dt.year}"
            else:
                folder = f"{dt.year}-{dt.month:02d}"

            target_folder = os.path.join(dest_dir, folder)
            target_path = os.path.join(target_folder, entry)
            target_path = _unique_target(target_path)

            actions[src_path] = target_path
            if not dry_run:
                _ensure_dir(target_folder)
                shutil.move(src_path, target_path)

        return actions


if __name__ == '__main__':
    # Simple CLI so you can run the organizer directly for manual use.
    import argparse

    parser = argparse.ArgumentParser(description='Organize files in a directory')
    parser.add_argument('src', help='Source directory to organize')
    parser.add_argument('--strategy', choices=['extension', 'category', 'date'], default='extension')
    parser.add_argument('--dest', help='Destination root directory (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Show actions without moving files')
    parser.add_argument('--by', choices=['month', 'year'], default='month', help='When using date strategy')
    args = parser.parse_args()

    fm = FileManager()
    if args.strategy == 'extension':
        actions = fm.organize_by_extension(args.src, dest_dir=args.dest, dry_run=args.dry_run)
    elif args.strategy == 'category':
        actions = fm.organize_by_category(args.src, dest_dir=args.dest, dry_run=args.dry_run)
    else:
        actions = fm.organize_by_date(args.src, dest_dir=args.dest, by=args.by, dry_run=args.dry_run)

    # Print a short summary
    print(f"Planned actions (count={len(actions)}){' [dry-run]' if args.dry_run else ''}:")
    for s, d in list(actions.items())[:200]:
        print(f"{s} -> {d}")