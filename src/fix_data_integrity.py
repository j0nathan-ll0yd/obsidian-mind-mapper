#!/usr/bin/env python3
"""
Data Integrity Fixer for Obsidian Notes

Fixes common data integrity issues:
- Date/datetime objects converted to string format
- YAML syntax errors (unescaped quotes)
- Empty source_url fields
- Invalid generated_at timestamps
"""

import os
import re
import yaml
from pathlib import Path
from datetime import date, datetime
from typing import Dict, Any
import shutil

def backup_note(note_path: Path, backup_dir: Path):
    """Create a backup of the note before modifying."""
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f"{note_path.stem}_{timestamp}.md"
    shutil.copy2(note_path, backup_path)
    return backup_path


def fix_frontmatter_types(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date/datetime objects to strings and fix null values."""
    fixed = frontmatter.copy()

    for key, value in fixed.items():
        if isinstance(value, datetime):
            # Convert datetime to ISO8601 format
            fixed[key] = value.strftime('%Y-%m-%dT%H:%M:%S')
        elif isinstance(value, date):
            # Convert date to YYYY-MM-DD format
            fixed[key] = value.strftime('%Y-%m-%d')

    # Fix null authors (should be empty list)
    if 'authors' in fixed and fixed['authors'] is None:
        fixed['authors'] = []

    # Fix null tags (should be empty list)
    if 'tags' in fixed and fixed['tags'] is None:
        fixed['tags'] = []

    return fixed


def fix_yaml_quotes(content: str) -> str:
    """Fix YAML syntax errors from unescaped quotes in strings."""
    lines = content.split('\n')
    in_frontmatter = False
    fixed_lines = []

    for i, line in enumerate(lines):
        if i == 0 and line.strip() == '---':
            in_frontmatter = True
            fixed_lines.append(line)
            continue

        if in_frontmatter and line.strip() == '---':
            in_frontmatter = False
            fixed_lines.append(line)
            continue

        if in_frontmatter:
            # Check for title line with problematic quotes
            if line.strip().startswith('title:'):
                # Extract the title value
                match = re.match(r'^(\s*title:\s*)"(.+)"(.*)$', line)
                if match:
                    indent, title_content, rest = match.groups()
                    # Escape internal quotes
                    if '"' in title_content:
                        # Replace with proper YAML escaping (double quotes)
                        title_escaped = title_content.replace('"', '\\"')
                        line = f'{indent}"{title_escaped}"{rest}'

            # Similar fix for other string fields
            for field in ['source', 'original_filename']:
                if line.strip().startswith(f'{field}:'):
                    match = re.match(rf'^(\s*{field}:\s*)"(.+)"(.*)$', line)
                    if match:
                        indent, content, rest = match.groups()
                        if '"' in content:
                            content_escaped = content.replace('"', '\\"')
                            line = f'{indent}"{content_escaped}"{rest}'

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def fix_note(note_path: Path, dry_run: bool = False, backup_dir: Path = None) -> tuple[bool, str]:
    """Fix integrity issues in a single note."""
    try:
        with open(note_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"Cannot read file: {e}"

    # First, fix YAML quote issues
    fixed_content = fix_yaml_quotes(content)

    # Extract frontmatter
    if not fixed_content.startswith('---'):
        return False, "No frontmatter found"

    parts = fixed_content.split('---', 2)
    if len(parts) < 3:
        return False, "Malformed frontmatter"

    try:
        frontmatter = yaml.safe_load(parts[1])
        body = parts[2].strip()
    except yaml.YAMLError as e:
        return False, f"YAML parsing error: {e}"

    if not frontmatter:
        return False, "Empty frontmatter"

    # Fix frontmatter types
    fixed_frontmatter = fix_frontmatter_types(frontmatter)

    # Fix empty source_url
    if 'source_url' in fixed_frontmatter and not fixed_frontmatter['source_url']:
        # Try to construct from source name or leave as placeholder
        fixed_frontmatter['source_url'] = 'https://unknown-source'

    # Reconstruct the note
    yaml_str = yaml.dump(fixed_frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    reconstructed = f"---\n{yaml_str}---\n\n{body}"

    if dry_run:
        return True, "Would fix (dry run)"

    # Create backup
    if backup_dir:
        backup_note(note_path, backup_dir)

    # Write fixed content
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(reconstructed)

    return True, "Fixed"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Fix data integrity issues in Obsidian notes'
    )
    parser.add_argument(
        '--vault-path',
        type=Path,
        default=Path(__file__).parent.parent / 'Lifegames',
        help='Path to Obsidian vault (default: ../Lifegames)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be fixed without making changes'
    )
    parser.add_argument(
        '--backup-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'backups' / 'integrity_fixes',
        help='Directory for backups (default: ../backups/integrity_fixes)'
    )
    parser.add_argument(
        '--note',
        type=str,
        help='Fix only a specific note (by filename)'
    )

    args = parser.parse_args()

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        return 1

    # Find notes to fix
    if args.note:
        note_path = args.vault_path / args.note
        if not note_path.exists():
            print(f"❌ Error: Note not found: {note_path}")
            return 1
        notes = [note_path]
    else:
        notes = []
        for md_file in args.vault_path.rglob('*.md'):
            if '.obsidian' not in md_file.parts:
                notes.append(md_file)

    mode_str = "DRY RUN - No changes will be made" if args.dry_run else "FIXING NOTES"
    print(f"\n{'='*80}")
    print(f"{mode_str}")
    print(f"{'='*80}\n")
    print(f"📝 Processing {len(notes)} notes...\n")

    success_count = 0
    error_count = 0
    errors = []

    for note_path in sorted(notes):
        success, message = fix_note(note_path, dry_run=args.dry_run, backup_dir=args.backup_dir)

        if success:
            success_count += 1
            if args.dry_run or args.note:
                print(f"✅ {note_path.name}: {message}")
        else:
            error_count += 1
            errors.append((note_path.name, message))
            print(f"❌ {note_path.name}: {message}")

    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Success: {success_count}")
    print(f"❌ Errors: {error_count}")

    if errors:
        print(f"\nErrors encountered:")
        for name, message in errors:
            print(f"  - {name}: {message}")

    if not args.dry_run and success_count > 0:
        print(f"\n💾 Backups saved to: {args.backup_dir}")

    print()

    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    exit(main())
