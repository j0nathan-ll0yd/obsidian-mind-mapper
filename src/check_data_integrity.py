#!/usr/bin/env python3
"""
Data Integrity Checker for Obsidian Notes

Scans all notes in Lifegames/ directory and validates:
- Required frontmatter fields
- Field formats and types
- File structure (sections)
- Attachment references
- Hash consistency

Reports any issues and provides statistics.
"""

import os
import json
import yaml
import re
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict

# Required frontmatter fields
REQUIRED_FIELDS = {
    'title': str,
    'source': str,
    'source_url': str,
    'date': str,
    'authors': list,
    'tags': list,
    'filename': str,
    'file_hash': str,
    'generated_by': str,
    'generated_model': str,
    'generated_at': str
}

# Optional fields that should be consistent if present
OPTIONAL_FIELDS = {
    'cssclass': str,
    'cssclasses': list,
    'original_filename': str
}

# Required sections in markdown body
REQUIRED_SECTIONS = [
    'Summary',
    'Key Points',
    'Linked Concepts',
    'Notes',
    'Attachments'
]

class IntegrityReport:
    def __init__(self):
        self.total_notes = 0
        self.valid_notes = 0
        self.issues = defaultdict(list)
        self.stats = defaultdict(int)

    def add_issue(self, category: str, note_path: str, message: str):
        self.issues[category].append({
            'note': note_path,
            'message': message
        })

    def add_stat(self, key: str, value: int = 1):
        self.stats[key] += value

    def print_report(self):
        print("\n" + "="*80)
        print("DATA INTEGRITY REPORT")
        print("="*80)

        print(f"\n📊 STATISTICS")
        print(f"   Total notes scanned: {self.total_notes}")
        print(f"   Valid notes: {self.valid_notes}")
        print(f"   Notes with issues: {self.total_notes - self.valid_notes}")
        print(f"   Success rate: {(self.valid_notes/self.total_notes*100):.1f}%")

        print(f"\n📈 BREAKDOWN")
        for key, value in sorted(self.stats.items()):
            print(f"   {key}: {value}")

        if self.issues:
            print(f"\n⚠️  ISSUES FOUND ({len(self.issues)} categories)")
            for category, issue_list in sorted(self.issues.items()):
                print(f"\n   {category.upper()} ({len(issue_list)} notes)")
                for issue in issue_list[:5]:  # Show first 5 examples
                    note_name = Path(issue['note']).name
                    print(f"      - {note_name}")
                    print(f"        {issue['message']}")
                if len(issue_list) > 5:
                    print(f"      ... and {len(issue_list) - 5} more")
        else:
            print(f"\n✅ NO ISSUES FOUND - All notes pass integrity checks!")

        print("\n" + "="*80 + "\n")


def extract_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """Extract YAML frontmatter and body from markdown content."""
    if not content.startswith('---'):
        return {}, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1])
        body = parts[2].strip()
        return frontmatter or {}, body
    except yaml.YAMLError as e:
        return {'_yaml_error': str(e)}, content


def check_note_integrity(note_path: Path, report: IntegrityReport):
    """Check a single note for integrity issues."""
    report.total_notes += 1
    note_valid = True

    try:
        with open(note_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        report.add_issue('read_error', str(note_path), f"Cannot read file: {e}")
        return

    # Extract frontmatter
    frontmatter, body = extract_frontmatter(content)

    if '_yaml_error' in frontmatter:
        report.add_issue('yaml_error', str(note_path),
                        f"YAML parsing error: {frontmatter['_yaml_error']}")
        note_valid = False
        return

    if not frontmatter:
        report.add_issue('missing_frontmatter', str(note_path),
                        "No frontmatter found")
        note_valid = False
        return

    # Check required fields
    for field_name, field_type in REQUIRED_FIELDS.items():
        if field_name not in frontmatter:
            report.add_issue('missing_field', str(note_path),
                           f"Missing required field: {field_name}")
            note_valid = False
        elif not isinstance(frontmatter[field_name], field_type):
            actual_type = type(frontmatter[field_name]).__name__
            expected_type = field_type.__name__
            report.add_issue('wrong_type', str(note_path),
                           f"Field '{field_name}' has type {actual_type}, expected {expected_type}")
            note_valid = False

    # Check date format (YYYY-MM-DD)
    if 'date' in frontmatter:
        date_str = str(frontmatter['date'])
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            report.add_issue('invalid_date', str(note_path),
                           f"Date format invalid: '{date_str}' (expected YYYY-MM-DD)")
            note_valid = False

    # Check generated_at format (YYYY-MM-DD or ISO8601)
    if 'generated_at' in frontmatter:
        gen_at = str(frontmatter['generated_at'])
        if not (re.match(r'^\d{4}-\d{2}-\d{2}$', gen_at) or
                re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', gen_at)):
            report.add_issue('invalid_generated_at', str(note_path),
                           f"generated_at format invalid: '{gen_at}'")
            note_valid = False

    # Check filename/file_hash consistency
    if 'filename' in frontmatter and 'file_hash' in frontmatter:
        if frontmatter['filename'] != frontmatter['file_hash']:
            report.add_issue('hash_mismatch', str(note_path),
                           f"filename '{frontmatter['filename']}' != file_hash '{frontmatter['file_hash']}'")
            note_valid = False

    # Check hash length (should be 8 characters)
    if 'file_hash' in frontmatter:
        hash_val = str(frontmatter['file_hash'])
        if len(hash_val) != 8:
            report.add_issue('invalid_hash', str(note_path),
                           f"file_hash length is {len(hash_val)}, expected 8")
            note_valid = False

    # Check for required sections
    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in body:
            report.add_issue('missing_section', str(note_path),
                           f"Missing section: {section}")
            note_valid = False

    # Check attachment references
    if 'file_hash' in frontmatter:
        hash_val = frontmatter['file_hash']
        attachments_dir = note_path.parent / 'Attachments'

        expected_files = {
            f"{hash_val}.pdf": 'pdf',
            f"{hash_val}.png": 'png',
            f"{hash_val}.json": 'json'
        }

        for filename, file_type in expected_files.items():
            file_path = attachments_dir / filename
            if not file_path.exists():
                report.add_issue('missing_attachment', str(note_path),
                               f"Missing attachment: {filename}")
                note_valid = False

    # Check authors format
    if 'authors' in frontmatter:
        authors = frontmatter['authors']
        if authors and not all(isinstance(a, str) for a in authors):
            report.add_issue('invalid_authors', str(note_path),
                           "Authors list contains non-string values")
            note_valid = False

    # Check tags format
    if 'tags' in frontmatter:
        tags = frontmatter['tags']
        if tags and not all(isinstance(t, str) for t in tags):
            report.add_issue('invalid_tags', str(note_path),
                           "Tags list contains non-string values")
            note_valid = False

    # Check URL format
    if 'source_url' in frontmatter:
        url = str(frontmatter['source_url'])
        if not (url.startswith('http://') or url.startswith('https://')):
            report.add_issue('invalid_url', str(note_path),
                           f"source_url doesn't start with http:// or https://: {url}")
            note_valid = False

    # Statistics
    if note_valid:
        report.valid_notes += 1
        report.add_stat('valid_notes')

    if 'generated_model' in frontmatter:
        model = frontmatter['generated_model']
        report.add_stat(f'model_{model}')

    if 'tags' in frontmatter and frontmatter['tags']:
        report.add_stat('notes_with_tags')
        report.add_stat('total_tags', len(frontmatter['tags']))

    if 'authors' in frontmatter and frontmatter['authors']:
        report.add_stat('notes_with_authors')


def scan_vault(vault_path: Path) -> IntegrityReport:
    """Scan all notes in the vault and check integrity."""
    report = IntegrityReport()

    # Find all markdown files (excluding .obsidian directory)
    markdown_files = []
    for md_file in vault_path.rglob('*.md'):
        # Skip .obsidian directory and any hidden directories
        if '.obsidian' in md_file.parts:
            continue
        markdown_files.append(md_file)

    print(f"🔍 Scanning {len(markdown_files)} notes in {vault_path}...")

    for note_path in sorted(markdown_files):
        check_note_integrity(note_path, report)

    return report


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Check data integrity of Obsidian notes'
    )
    parser.add_argument(
        '--vault-path',
        type=Path,
        default=Path(__file__).parent.parent / 'Lifegames',
        help='Path to Obsidian vault (default: ../Lifegames)'
    )
    parser.add_argument(
        '--json-output',
        type=Path,
        help='Save detailed report to JSON file'
    )

    args = parser.parse_args()

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        return 1

    # Run integrity check
    report = scan_vault(args.vault_path)

    # Print report
    report.print_report()

    # Save JSON report if requested
    if args.json_output:
        json_data = {
            'total_notes': report.total_notes,
            'valid_notes': report.valid_notes,
            'statistics': dict(report.stats),
            'issues': dict(report.issues)
        }

        with open(args.json_output, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"📄 Detailed report saved to: {args.json_output}")

    # Return exit code based on issues
    return 0 if report.valid_notes == report.total_notes else 1


if __name__ == '__main__':
    exit(main())
