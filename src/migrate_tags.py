#!/usr/bin/env python3
"""
Tag Migration Tool

Applies taxonomy changes to all notes:
- Capitalizes tags according to standard
- Consolidates duplicate/similar tags
- Preserves all other note content

Part of Phase 3a: Tag Taxonomy Optimization (Normalization Only)
"""

import json
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict

class TagMigrator:
    def __init__(self, taxonomy_file: Path, vault_path: Path):
        """Load taxonomy and prepare for migration."""
        with open(taxonomy_file, 'r', encoding='utf-8') as f:
            self.taxonomy = json.load(f)

        self.vault_path = vault_path

        # Combine all mappings
        self.tag_mappings = {}
        self.tag_mappings.update(self.taxonomy['capitalization_mappings'])
        self.tag_mappings.update(self.taxonomy['consolidation_mappings'])

        # Statistics
        self.stats = {
            'notes_processed': 0,
            'notes_modified': 0,
            'tags_remapped': 0,
            'errors': []
        }

    def extract_frontmatter(self, content: str):
        """Extract YAML frontmatter and body from markdown."""
        if not content.startswith('---'):
            return {}, content

        parts = content.split('---', 2)
        if len(parts) < 3:
            return {}, content

        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return frontmatter, body
        except yaml.YAMLError as e:
            return {'_yaml_error': str(e)}, content

    def migrate_tags(self, tags: List[str]) -> tuple[List[str], Dict[str, int]]:
        """
        Migrate tags using taxonomy.

        Returns: (new_tags_list, stats_dict)
        """
        if not tags:
            return [], {'remapped': 0}

        new_tags = []
        stats = {'remapped': 0}

        # Remap tags according to taxonomy
        for tag in tags:
            if tag in self.tag_mappings:
                new_tag = self.tag_mappings[tag]
                new_tags.append(new_tag)
                stats['remapped'] += 1
            else:
                new_tags.append(tag)

        # Deduplicate while preserving order
        final_tags = list(dict.fromkeys(new_tags))

        return final_tags, stats

    def migrate_note(self, note_path: Path, backup_dir: Path = None, dry_run: bool = False) -> tuple[bool, str]:
        """Migrate tags in a single note."""
        self.stats['notes_processed'] += 1

        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            error_msg = f"Cannot read: {e}"
            self.stats['errors'].append((note_path.name, error_msg))
            return False, error_msg

        # Extract frontmatter
        frontmatter, body = self.extract_frontmatter(content)

        if '_yaml_error' in frontmatter:
            error_msg = f"YAML error: {frontmatter['_yaml_error']}"
            self.stats['errors'].append((note_path.name, error_msg))
            return False, error_msg

        if not frontmatter:
            return True, "No frontmatter (skipped)"

        # Get current tags
        original_tags = frontmatter.get('tags', [])
        if not isinstance(original_tags, list):
            return True, "No tags array (skipped)"

        # Migrate tags
        new_tags, migration_stats = self.migrate_tags(original_tags)

        # Check if anything changed
        if new_tags == original_tags:
            return True, "No changes needed"

        # Update frontmatter
        frontmatter['tags'] = new_tags

        # Reconstruct note
        yaml_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        reconstructed = f"---\n{yaml_str}---\n\n{body}"

        if dry_run:
            self.stats['notes_modified'] += 1
            self.stats['tags_remapped'] += migration_stats['remapped']
            return True, f"Would modify (remapped: {migration_stats['remapped']})"

        # Create backup
        if backup_dir:
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"{note_path.stem}_{timestamp}.md"
            shutil.copy2(note_path, backup_path)

        # Write updated note
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(reconstructed)

        self.stats['notes_modified'] += 1
        self.stats['tags_remapped'] += migration_stats['remapped']

        return True, f"Modified (remapped: {migration_stats['remapped']})"

    def migrate_vault(self, backup_dir: Path = None, dry_run: bool = False):
        """Migrate all notes in the vault."""
        # Find all markdown files
        markdown_files = []
        for md_file in self.vault_path.rglob('*.md'):
            if '.obsidian' not in md_file.parts:
                markdown_files.append(md_file)

        mode = "DRY RUN" if dry_run else "MIGRATION"
        print(f"\n{'='*80}")
        print(f"TAG {mode}")
        print(f"{'='*80}\n")
        print(f"📝 Processing {len(markdown_files)} notes...")
        print(f"   Capitalization fixes: {len(self.taxonomy['capitalization_mappings'])}")
        print(f"   Consolidations: {len(self.taxonomy['consolidation_mappings'])}\n")

        # Process notes
        for note_path in sorted(markdown_files):
            success, message = self.migrate_note(note_path, backup_dir, dry_run)

            # Only print if modified or error
            if not success or "Modified" in message or "Would modify" in message:
                status = "✅" if success else "❌"
                print(f"{status} {note_path.name}: {message}")

        print(f"\n{'='*80}")
        print(f"MIGRATION SUMMARY")
        print(f"{'='*80}")
        print(f"📊 Notes processed: {self.stats['notes_processed']}")
        print(f"✏️  Notes modified: {self.stats['notes_modified']}")
        print(f"🔄 Tags remapped: {self.stats['tags_remapped']}")
        print(f"❌ Errors: {len(self.stats['errors'])}")

        if self.stats['errors']:
            print(f"\nErrors encountered:")
            for note_name, error_msg in self.stats['errors'][:10]:
                print(f"  - {note_name}: {error_msg}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")

        if not dry_run and backup_dir and self.stats['notes_modified'] > 0:
            print(f"\n💾 Backups saved to: {backup_dir}")

        print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Migrate tags using taxonomy'
    )
    parser.add_argument(
        '--taxonomy',
        type=Path,
        default=Path('tag_taxonomy.json'),
        help='Taxonomy JSON file (default: tag_taxonomy.json)'
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
        help='Show what would change without making modifications'
    )
    parser.add_argument(
        '--backup-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'backups' / 'tag_migration',
        help='Directory for backups (default: ../backups/tag_migration)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.taxonomy.exists():
        print(f"❌ Error: Taxonomy file not found: {args.taxonomy}")
        print(f"   Run 'python src/design_taxonomy.py' first")
        return 1

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        return 1

    # Run migration
    migrator = TagMigrator(args.taxonomy, args.vault_path)
    migrator.migrate_vault(
        backup_dir=args.backup_dir if not args.dry_run else None,
        dry_run=args.dry_run
    )

    if args.dry_run:
        print("ℹ️  This was a dry run. To apply changes, run without --dry-run flag.")

    return 0


if __name__ == '__main__':
    exit(main())
