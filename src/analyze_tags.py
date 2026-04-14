#!/usr/bin/env python3
"""
Tag Analyzer for Obsidian Vault

Analyzes tags across all notes to:
- Extract all unique tags
- Count tag frequencies
- Find tag co-occurrences
- Identify potential synonyms/duplicates
- Detect naming inconsistencies
- Generate analysis reports

Part of Phase 3a: Tag Taxonomy Optimization
"""

import os
import json
import yaml
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple
import re

class TagAnalyzer:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.tag_counts = Counter()
        self.tag_cooccurrence = defaultdict(Counter)
        self.notes_by_tag = defaultdict(list)
        self.all_notes = []

    def extract_frontmatter(self, content: str) -> Dict:
        """Extract YAML frontmatter from markdown content."""
        if not content.startswith('---'):
            return {}

        parts = content.split('---', 2)
        if len(parts) < 3:
            return {}

        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}

    def analyze_vault(self):
        """Scan all notes and extract tag data."""
        print(f"🔍 Scanning vault: {self.vault_path}")

        markdown_files = []
        for md_file in self.vault_path.rglob('*.md'):
            if '.obsidian' not in md_file.parts:
                markdown_files.append(md_file)

        print(f"   Found {len(markdown_files)} notes")

        for note_path in markdown_files:
            try:
                with open(note_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                frontmatter = self.extract_frontmatter(content)
                tags = frontmatter.get('tags', [])

                if not isinstance(tags, list):
                    continue

                note_name = note_path.name
                self.all_notes.append(note_name)

                # Count tags
                for tag in tags:
                    self.tag_counts[tag] += 1
                    self.notes_by_tag[tag].append(note_name)

                # Track co-occurrences
                for i, tag1 in enumerate(tags):
                    for tag2 in tags[i+1:]:
                        self.tag_cooccurrence[tag1][tag2] += 1
                        self.tag_cooccurrence[tag2][tag1] += 1

            except Exception as e:
                print(f"   ⚠️  Error reading {note_path.name}: {e}")
                continue

        print(f"   ✅ Analysis complete\n")

    def find_similar_tags(self, threshold: float = 0.7) -> List[Tuple[str, str, float]]:
        """Find potentially similar tags using string similarity."""
        from difflib import SequenceMatcher

        similar_pairs = []
        tags = list(self.tag_counts.keys())

        for i, tag1 in enumerate(tags):
            for tag2 in tags[i+1:]:
                # Normalize for comparison
                t1 = tag1.lower().replace('-', '').replace('_', '')
                t2 = tag2.lower().replace('-', '').replace('_', '')

                similarity = SequenceMatcher(None, t1, t2).ratio()

                if similarity >= threshold:
                    similar_pairs.append((tag1, tag2, similarity))

        return sorted(similar_pairs, key=lambda x: x[2], reverse=True)

    def find_naming_inconsistencies(self) -> Dict[str, List[str]]:
        """Identify tags with different capitalization or separators."""
        groups = defaultdict(list)

        for tag in self.tag_counts.keys():
            # Normalize to lowercase, no separators
            normalized = tag.lower().replace('-', '').replace('_', '').replace(' ', '')
            groups[normalized].append(tag)

        # Filter to groups with multiple variants
        return {k: v for k, v in groups.items() if len(v) > 1}

    def find_hierarchical_patterns(self) -> Dict[str, List[str]]:
        """Identify potential parent-child relationships."""
        hierarchies = defaultdict(list)

        for tag in self.tag_counts.keys():
            # Look for tags that are substrings of others
            for other_tag in self.tag_counts.keys():
                if tag != other_tag:
                    # Check if tag is a component of other_tag
                    if tag.lower() in other_tag.lower().split('-'):
                        hierarchies[tag].append(other_tag)

        return dict(hierarchies)

    def get_top_cooccurring_tags(self, tag: str, n: int = 10) -> List[Tuple[str, int]]:
        """Get top N tags that co-occur with given tag."""
        if tag not in self.tag_cooccurrence:
            return []

        cooccur = self.tag_cooccurrence[tag]
        return cooccur.most_common(n)

    def generate_report(self) -> Dict:
        """Generate comprehensive analysis report."""
        print("📊 Generating analysis report...")

        report = {
            'summary': {
                'total_notes': len(self.all_notes),
                'total_unique_tags': len(self.tag_counts),
                'total_tag_usages': sum(self.tag_counts.values()),
                'avg_tags_per_note': sum(self.tag_counts.values()) / len(self.all_notes) if self.all_notes else 0,
                'tags_used_once': sum(1 for count in self.tag_counts.values() if count == 1),
                'tags_used_5plus': sum(1 for count in self.tag_counts.values() if count >= 5),
                'tags_used_10plus': sum(1 for count in self.tag_counts.values() if count >= 10)
            },
            'top_tags': self.tag_counts.most_common(50),
            'rare_tags': [(tag, count) for tag, count in self.tag_counts.items() if count == 1],
            'similar_tags': self.find_similar_tags(threshold=0.7),
            'naming_inconsistencies': self.find_naming_inconsistencies(),
            'hierarchical_patterns': self.find_hierarchical_patterns()
        }

        # Add co-occurrence data for top tags
        report['top_tag_cooccurrences'] = {}
        for tag, count in self.tag_counts.most_common(20):
            report['top_tag_cooccurrences'][tag] = self.get_top_cooccurring_tags(tag, 5)

        return report

    def print_report(self, report: Dict):
        """Print human-readable analysis report."""
        print("\n" + "="*80)
        print("TAG ANALYSIS REPORT")
        print("="*80)

        # Summary
        summary = report['summary']
        print(f"\n📊 SUMMARY")
        print(f"   Total notes: {summary['total_notes']}")
        print(f"   Unique tags: {summary['total_unique_tags']}")
        print(f"   Total tag usages: {summary['total_tag_usages']}")
        print(f"   Average tags per note: {summary['avg_tags_per_note']:.1f}")
        print(f"   Tags used once: {summary['tags_used_once']} ({summary['tags_used_once']/summary['total_unique_tags']*100:.1f}%)")
        print(f"   Tags used 5+ times: {summary['tags_used_5plus']}")
        print(f"   Tags used 10+ times: {summary['tags_used_10plus']}")

        # Top tags
        print(f"\n🏆 TOP 30 TAGS")
        for tag, count in report['top_tags'][:30]:
            pct = (count / summary['total_notes']) * 100
            bar = "█" * int(pct / 2)
            print(f"   {tag:.<50} {count:>4} ({pct:>5.1f}%) {bar}")

        # Rare tags
        if report['rare_tags']:
            print(f"\n🔍 RARE TAGS (used only once): {len(report['rare_tags'])}")
            print(f"   Showing first 20:")
            for tag, count in report['rare_tags'][:20]:
                print(f"   - {tag}")

        # Similar tags
        if report['similar_tags']:
            print(f"\n🔄 SIMILAR TAGS (potential duplicates/synonyms)")
            for tag1, tag2, similarity in report['similar_tags'][:20]:
                print(f"   - {tag1} ↔ {tag2} (similarity: {similarity:.2f})")
                print(f"     {tag1}: {self.tag_counts[tag1]} uses | {tag2}: {self.tag_counts[tag2]} uses")

        # Naming inconsistencies
        if report['naming_inconsistencies']:
            print(f"\n⚠️  NAMING INCONSISTENCIES ({len(report['naming_inconsistencies'])} groups)")
            for normalized, variants in list(report['naming_inconsistencies'].items())[:20]:
                print(f"   - {variants}")
                for v in variants:
                    print(f"     {v}: {self.tag_counts[v]} uses")

        # Hierarchical patterns
        if report['hierarchical_patterns']:
            print(f"\n🌳 POTENTIAL HIERARCHIES ({len(report['hierarchical_patterns'])} parent tags)")
            for parent, children in list(report['hierarchical_patterns'].items())[:15]:
                print(f"   {parent} ({self.tag_counts[parent]} uses)")
                for child in children[:5]:
                    print(f"      └─ {child} ({self.tag_counts[child]} uses)")

        # Co-occurrences
        print(f"\n🔗 TAG CO-OCCURRENCES (top 10 tags)")
        for tag, cooccur_list in list(report['top_tag_cooccurrences'].items())[:10]:
            print(f"   {tag}:")
            for cooccur_tag, count in cooccur_list[:5]:
                print(f"      - {cooccur_tag} ({count} times)")

        print("\n" + "="*80 + "\n")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Analyze tags in Obsidian vault'
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
        help='Save report to JSON file'
    )
    parser.add_argument(
        '--detailed-output',
        type=Path,
        help='Save detailed data (including notes_by_tag) to JSON file'
    )

    args = parser.parse_args()

    if not args.vault_path.exists():
        print(f"❌ Error: Vault path does not exist: {args.vault_path}")
        return 1

    # Run analysis
    analyzer = TagAnalyzer(args.vault_path)
    analyzer.analyze_vault()
    report = analyzer.generate_report()

    # Print report
    analyzer.print_report(report)

    # Save JSON report
    if args.json_output:
        with open(args.json_output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"📄 Report saved to: {args.json_output}")

    # Save detailed data
    if args.detailed_output:
        detailed = {
            'report': report,
            'tag_counts': dict(analyzer.tag_counts),
            'notes_by_tag': dict(analyzer.notes_by_tag),
            'tag_cooccurrence': {
                tag: dict(cooccur)
                for tag, cooccur in analyzer.tag_cooccurrence.items()
            }
        }
        with open(args.detailed_output, 'w', encoding='utf-8') as f:
            json.dump(detailed, f, indent=2, ensure_ascii=False)
        print(f"📄 Detailed data saved to: {args.detailed_output}")

    return 0


if __name__ == '__main__':
    exit(main())
