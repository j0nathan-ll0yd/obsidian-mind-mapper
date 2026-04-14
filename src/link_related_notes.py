#!/usr/bin/env python3
"""
Automatic Note Linking Tool

Identifies and creates bi-directional wiki links between related notes
based on cluster definitions.

Part of Phase 3b: Linked Concepts (Revised)
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class NoteLinker:
    def __init__(self, clusters_file: Path, vault_path: Path):
        """Load cluster definitions and prepare for linking."""
        with open(clusters_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.clusters = data['clusters']
        self.vault_path = vault_path

        # Build link mappings
        self.note_to_links = defaultdict(set)  # note -> set of notes it should link to
        self._build_link_mappings()

        # Statistics
        self.stats = {
            'notes_processed': 0,
            'notes_modified': 0,
            'links_added': 0,
            'links_already_exist': 0,
            'errors': []
        }

    def _build_link_mappings(self):
        """Build mappings of which notes should link to which based on clusters."""
        for cluster in self.clusters:
            notes = cluster['notes']
            strategy = cluster['linking_strategy']

            if strategy == 'full_mesh':
                # All notes link to all other notes
                for note in notes:
                    for other_note in notes:
                        if note != other_note:
                            self.note_to_links[note].add(other_note)

            elif strategy == 'linear':
                # Sequential linking: A↔B, B↔C (still bi-directional)
                for i in range(len(notes) - 1):
                    # Forward link
                    self.note_to_links[notes[i]].add(notes[i + 1])
                    # Backward link (bi-directional)
                    self.note_to_links[notes[i + 1]].add(notes[i])

            elif strategy == 'hub_spoke':
                # Hub links to all spokes, spokes link back to hub
                hub = cluster.get('hub_note')
                if not hub:
                    print(f"⚠️  Warning: hub_spoke strategy but no hub_note defined for {cluster['name']}")
                    continue

                for note in notes:
                    if note == hub:
                        # Hub links to all spokes
                        for spoke in notes:
                            if spoke != hub:
                                self.note_to_links[hub].add(spoke)
                    else:
                        # Spoke links back to hub
                        self.note_to_links[note].add(hub)

    def extract_linked_concepts_section(self, content: str) -> Tuple[str, str, str]:
        """
        Extract the Linked Concepts section from note content.

        Returns: (before_section, section_content, after_section)
        """
        # Pattern to match ## Linked Concepts section
        pattern = r'(.*?)(## Linked Concepts\s*\n)(.*?)(?=\n## |\Z)'

        match = re.search(pattern, content, re.DOTALL)

        if not match:
            # Section doesn't exist - return whole content as "before"
            return content, '', ''

        before = match.group(1)
        header = match.group(2)
        section = match.group(3)
        after = content[match.end():]

        return before, header + section, after

    def parse_existing_links(self, section_content: str) -> Set[str]:
        """Parse existing wiki links from Linked Concepts section."""
        # Pattern for wiki links: [[Note Title]]
        pattern = r'\[\[([^\]]+)\]\]'

        matches = re.findall(pattern, section_content)
        return set(matches)

    def build_linked_concepts_section(self, existing_links: Set[str], new_links: Set[str]) -> str:
        """Build the Linked Concepts section with existing + new links."""
        # Combine existing and new links
        all_links = existing_links | new_links

        if not all_links:
            # No links - return placeholder
            return "## Linked Concepts\n\n<!-- For manual wiki-linking later -->\n"

        # Sort links alphabetically
        sorted_links = sorted(all_links)

        # Build section
        section = "## Linked Concepts\n\n"
        for link in sorted_links:
            section += f"[[{link}]]\n"
        section += "\n"

        return section

    def get_note_title(self, note_path: Path) -> str:
        """Get note title from filename (without .md extension)."""
        return note_path.stem

    def link_note(self, note_path: Path, links_to_add: Set[str], backup_dir: Path = None, dry_run: bool = False) -> Tuple[bool, str]:
        """Add wiki links to a single note's Linked Concepts section."""
        self.stats['notes_processed'] += 1

        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            error_msg = f"Cannot read: {e}"
            self.stats['errors'].append((note_path.name, error_msg))
            return False, error_msg

        # Extract Linked Concepts section
        before, section, after = self.extract_linked_concepts_section(content)

        # Parse existing links
        existing_links = self.parse_existing_links(section)

        # Determine which links are new
        truly_new_links = links_to_add - existing_links
        already_exist = links_to_add & existing_links

        if already_exist:
            self.stats['links_already_exist'] += len(already_exist)

        if not truly_new_links:
            return True, f"No new links to add (already has {len(existing_links)} links)"

        # Build new section
        new_section = self.build_linked_concepts_section(existing_links, truly_new_links)

        # Reconstruct note
        reconstructed = before + new_section + after

        if dry_run:
            self.stats['notes_modified'] += 1
            self.stats['links_added'] += len(truly_new_links)
            return True, f"Would add {len(truly_new_links)} links (existing: {len(existing_links)})"

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
        self.stats['links_added'] += len(truly_new_links)

        return True, f"Added {len(truly_new_links)} links (existing: {len(existing_links)})"

    def link_vault(self, backup_dir: Path = None, dry_run: bool = False):
        """Link all notes in the vault according to cluster definitions."""
        mode = "DRY RUN" if dry_run else "LINKING"
        print(f"\n{'='*80}")
        print(f"AUTOMATIC NOTE {mode}")
        print(f"{'='*80}\n")
        print(f"📊 Clusters loaded: {len(self.clusters)}")
        print(f"📝 Notes to process: {len(self.note_to_links)}\n")

        # Process each note that has links to add
        for note_filename, target_titles in sorted(self.note_to_links.items()):
            note_path = self.vault_path / note_filename

            if not note_path.exists():
                error_msg = f"Note not found: {note_filename}"
                self.stats['errors'].append((note_filename, error_msg))
                print(f"❌ {note_filename}: {error_msg}")
                continue

            # Process this note
            success, message = self.link_note(note_path, target_titles, backup_dir, dry_run)

            # Only print if modified or error
            if not success or "Would add" in message or "Added" in message:
                status = "✅" if success else "❌"
                print(f"{status} {note_filename}: {message}")

        # Print summary
        print(f"\n{'='*80}")
        print(f"LINKING SUMMARY")
        print(f"{'='*80}")
        print(f"📊 Notes processed: {self.stats['notes_processed']}")
        print(f"✏️  Notes modified: {self.stats['notes_modified']}")
        print(f"🔗 Links added: {self.stats['links_added']}")
        print(f"♻️  Links already exist: {self.stats['links_already_exist']}")
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
        description='Automatically link related notes based on cluster definitions'
    )
    parser.add_argument(
        '--clusters',
        type=Path,
        default=Path('linked_notes_clusters.json'),
        help='Cluster definitions JSON file (default: linked_notes_clusters.json)'
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
        default=Path(__file__).parent.parent / 'backups' / 'note_linking',
        help='Directory for backups (default: ../backups/note_linking)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.clusters.exists():
        print(f"❌ Error: Cluster definitions file not found: {args.clusters}")
        return 1

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        return 1

    # Run linking
    linker = NoteLinker(args.clusters, args.vault_path)
    linker.link_vault(
        backup_dir=args.backup_dir if not args.dry_run else None,
        dry_run=args.dry_run
    )

    if args.dry_run:
        print("ℹ️  This was a dry run. To apply changes, run without --dry-run flag.")

    return 0


if __name__ == '__main__':
    exit(main())
