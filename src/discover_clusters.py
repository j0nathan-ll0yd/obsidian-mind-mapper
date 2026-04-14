#!/usr/bin/env python3
"""
Auto-Discovery Note Linking Tool

Discovers related Obsidian notes via tag co-occurrence and title similarity,
producing candidate cluster definitions for review and application.

Part of Phase 3c: Auto-Discovery Note Linking
"""

import json
import sys
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
import argparse

# Import TagAnalyzer from the sibling module
sys.path.insert(0, str(Path(__file__).parent))
from analyze_tags import TagAnalyzer


# Common English stop words to ignore during title similarity comparison
STOP_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'up', 'as', 'is', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'shall', 'can',
    'it', 'its', 'this', 'that', 'these', 'those', 'i', 'we', 'you',
    'he', 'she', 'they', 'what', 'which', 'who', 'how', 'when', 'where',
    'why', 'not', 'no', 'so', 'if', 'then', 'than', 'into', 'about',
    'over', 'after', 'out', 'more', 'also', 'just', 'now', 'new',
}


class UnionFind:
    """Simple union-find for merging overlapping groups."""

    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str):
        px, py = self.find(x), self.find(y)
        if px != py:
            self.parent[py] = px

    def groups(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = defaultdict(set)
        for x in self.parent:
            result[self.find(x)].add(x)
        return dict(result)


def title_word_set(filename: str) -> Set[str]:
    """Extract meaningful words from a note filename (without .md extension)."""
    stem = Path(filename).stem
    words = re.findall(r'[a-zA-Z]+', stem)
    return {w.lower() for w in words if w.lower() not in STOP_WORDS and len(w) > 1}


def jaccard(a: Set[str], b: Set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def deterministic_cluster_id(notes: List[str]) -> str:
    """Generate a deterministic cluster_id from sorted note filenames."""
    joined = '|'.join(sorted(notes))
    return 'auto_' + hashlib.md5(joined.encode('utf-8')).hexdigest()[:8]


def suggested_name_from_tags(tags: List[str]) -> str:
    """Produce a human-readable cluster name from shared tags."""
    if not tags:
        return 'Unnamed Cluster'
    # Use the 2 most common tags
    return ' / '.join(tags[:2])


def detect_linear_strategy(notes: List[str]) -> bool:
    """
    Heuristic: notes share a title prefix with ascending markers like
    Part 1 / Part 2, or sequential years, or 'update' suffix.
    """
    stems = [Path(n).stem.lower() for n in notes]

    # Look for Part N / Part N+1 pattern
    part_pattern = re.compile(r'part\s*(\d+)', re.IGNORECASE)
    part_nums = []
    for s in stems:
        m = part_pattern.search(s)
        if m:
            part_nums.append(int(m.group(1)))

    if len(part_nums) == len(notes) and part_nums == sorted(part_nums):
        return True

    # Look for ascending 4-digit years in otherwise similar titles
    year_pattern = re.compile(r'\b(20\d{2})\b')
    years = []
    for s in stems:
        m = year_pattern.findall(s)
        if m:
            years.append(int(m[-1]))

    if len(years) == len(notes) and years == sorted(years):
        return True

    return False


def select_hub_note(notes: List[str], shared_tags_per_note: Dict[str, List[str]]) -> str:
    """
    For hub_spoke: pick the note with the most shared specific tags
    with other cluster members.  Ties broken by earliest date in filename.
    """
    def score_note(n: str) -> Tuple[int, str]:
        tag_count = len(shared_tags_per_note.get(n, []))
        # Extract date portion for tie-breaking (lower date string = earlier = preferred)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', n)
        date_str = date_match.group(1) if date_match else '9999-99-99'
        return (-tag_count, date_str)  # negative so highest count sorts first

    return min(notes, key=score_note)


def merge_overlapping_groups(groups: List[Set[str]], overlap_threshold: float = 0.5) -> List[Set[str]]:
    """Merge groups that share >= overlap_threshold fraction of notes."""
    changed = True
    while changed:
        changed = False
        merged: List[Set[str]] = []
        used = [False] * len(groups)
        for i, g1 in enumerate(groups):
            if used[i]:
                continue
            current = set(g1)
            for j, g2 in enumerate(groups):
                if i == j or used[j]:
                    continue
                intersection = current & g2
                smaller = min(len(current), len(g2))
                if smaller > 0 and len(intersection) / smaller >= overlap_threshold:
                    current |= g2
                    used[j] = True
                    changed = True
            merged.append(current)
            used[i] = True
        groups = merged
    return groups


def build_note_tag_index(
    analyzer: TagAnalyzer,
    specific_tags: Set[str],
    unclustered: Set[str],
) -> Dict[str, Set[str]]:
    """Build a map of note -> set of specific tags it has (among unclustered notes)."""
    note_tags: Dict[str, Set[str]] = defaultdict(set)
    for tag in specific_tags:
        for note in analyzer.notes_by_tag.get(tag, []):
            if note in unclustered:
                note_tags[note].add(tag)
    return dict(note_tags)


def discover_clusters(
    vault_path: Path,
    clusters_file: Path,
    generic_tag_pct: float = 0.05,
    min_notes: int = 2,
    max_notes: int = 15,
    min_shared_tags: int = 2,
    title_overlap_threshold: float = 0.5,
) -> Dict:
    """
    Main discovery algorithm.

    Returns a dict with 'candidates' and 'metadata'.

    Tag-based grouping uses pairs of notes sharing >= min_shared_tags specific
    tags (default 2), so loose single-tag thematic groups are excluded.
    Title-based grouping uses Jaccard >= title_overlap_threshold on word sets.
    """

    # Step 1: Load existing clusters → build exclusion set
    print(f"Loading existing clusters from {clusters_file}...", file=sys.stderr)
    existing_notes: Set[str] = set()
    if clusters_file.exists():
        with open(clusters_file, 'r', encoding='utf-8') as f:
            cluster_data = json.load(f)
        for cluster in cluster_data.get('clusters', []):
            for note in cluster.get('notes', []):
                existing_notes.add(note)
    print(f"  Already clustered: {len(existing_notes)} notes", file=sys.stderr)

    # Step 2: Fresh tag analysis from live vault
    print(f"Analyzing vault tags...", file=sys.stderr)
    analyzer = TagAnalyzer(vault_path)
    analyzer.analyze_vault()

    total_notes = len(analyzer.all_notes)
    print(f"  Total notes in vault: {total_notes}", file=sys.stderr)

    # Step 3: Filter generic tags (appearing in > generic_tag_pct of notes)
    generic_threshold = int(total_notes * generic_tag_pct)
    specific_tags = {
        tag for tag, count in analyzer.tag_counts.items()
        if count <= generic_threshold
    }
    print(f"  Generic tag threshold: >{generic_threshold} notes ({generic_tag_pct*100:.0f}%)", file=sys.stderr)
    print(f"  Specific tags: {len(specific_tags)} / {len(analyzer.tag_counts)} total tags", file=sys.stderr)

    # Unclustered notes
    unclustered = set(analyzer.all_notes) - existing_notes
    print(f"  Unclustered notes: {len(unclustered)}", file=sys.stderr)

    # Step 4: Tag-based candidate groups via pair co-occurrence
    # Connect pairs of unclustered notes that share >= min_shared_tags specific tags
    note_tag_index = build_note_tag_index(analyzer, specific_tags, unclustered)
    unclustered_list = sorted(unclustered)

    print(f"  Building tag co-occurrence pairs (min shared tags: {min_shared_tags})...", file=sys.stderr)
    uf_tag = UnionFind()
    tag_pair_count = 0
    # Index: tag -> list of unclustered notes with that tag (for efficiency)
    tag_to_unclustered: Dict[str, List[str]] = defaultdict(list)
    for note, tags in note_tag_index.items():
        for tag in tags:
            tag_to_unclustered[tag].append(note)

    # For each pair of notes, count shared specific tags
    pair_shared: Dict[Tuple[str, str], int] = defaultdict(int)
    for tag, notes_with_tag in tag_to_unclustered.items():
        notes_sorted = sorted(notes_with_tag)
        for i, n1 in enumerate(notes_sorted):
            for n2 in notes_sorted[i + 1:]:
                key = (n1, n2) if n1 < n2 else (n2, n1)
                pair_shared[key] += 1

    for (n1, n2), count in pair_shared.items():
        if count >= min_shared_tags:
            uf_tag.union(n1, n2)
            tag_pair_count += 1

    tag_groups_raw = uf_tag.groups()
    tag_groups: List[Set[str]] = [g for g in tag_groups_raw.values() if len(g) >= min_notes]
    print(f"  Tag co-occurrence pairs (>= {min_shared_tags} shared tags): {tag_pair_count}", file=sys.stderr)
    print(f"  Tag-based groups: {len(tag_groups)}", file=sys.stderr)

    # Step 5: Title-based candidates via union-find
    print(f"  Computing title similarity pairs (Jaccard >= {title_overlap_threshold})...", file=sys.stderr)
    uf_title = UnionFind()
    word_sets = {n: title_word_set(n) for n in unclustered_list}

    title_pair_count = 0
    for i, n1 in enumerate(unclustered_list):
        for n2 in unclustered_list[i + 1:]:
            sim = jaccard(word_sets[n1], word_sets[n2])
            if sim >= title_overlap_threshold:
                uf_title.union(n1, n2)
                title_pair_count += 1

    title_groups_raw = uf_title.groups()
    title_groups = [g for g in title_groups_raw.values() if len(g) >= min_notes]
    print(f"  Title similarity pairs found: {title_pair_count}", file=sys.stderr)
    print(f"  Title-based groups: {len(title_groups)}", file=sys.stderr)

    # Combine tag groups and title groups into one list
    all_group_sets: List[Set[str]] = tag_groups + title_groups

    # Step 6: Merge overlapping groups (>= 50% shared notes)
    merged_groups = merge_overlapping_groups(all_group_sets, overlap_threshold=0.5)

    # Step 7: Filter groups with < min_notes or > max_notes
    merged_groups = [g for g in merged_groups if min_notes <= len(g) <= max_notes]
    print(f"  Candidate groups after merging: {len(merged_groups)}", file=sys.stderr)

    # Step 8 & 9: Score and build candidates
    candidates = []
    for group_notes in merged_groups:
        notes_list = sorted(group_notes)

        # Find shared specific tags for this group
        shared_tags: List[str] = []
        for tag in specific_tags:
            tag_notes = set(analyzer.notes_by_tag.get(tag, []))
            if group_notes.issubset(tag_notes) or (len(group_notes & tag_notes) >= 2 and len(group_notes & tag_notes) == len(group_notes)):
                shared_tags.append(tag)

        # More generous: tags shared by at least 2 notes in the group
        tag_shared_count: Dict[str, int] = defaultdict(int)
        for note in group_notes:
            # Reconstruct per-note tags from notes_by_tag
            pass

        # Rebuild: which specific tags appear in >=2 notes of this group
        group_specific_shared: List[str] = []
        for tag in specific_tags:
            tag_note_set = set(analyzer.notes_by_tag.get(tag, []))
            overlap_count = len(group_notes & tag_note_set)
            if overlap_count >= 2:
                group_specific_shared.append(tag)

        # Compute average pairwise title overlap
        pairs = []
        for i, n1 in enumerate(notes_list):
            for n2 in notes_list[i + 1:]:
                pairs.append(jaccard(word_sets.get(n1, set()), word_sets.get(n2, set())))
        avg_title_overlap = sum(pairs) / len(pairs) if pairs else 0.0

        # Score
        max_possible = len(group_specific_shared) * 2 + 3  # rough normalizer
        score_raw = len(group_specific_shared) * 2 + avg_title_overlap * 3
        score = min(1.0, score_raw / max_possible) if max_possible > 0 else avg_title_overlap

        # Strategy selection
        n = len(notes_list)
        if detect_linear_strategy(notes_list):
            strategy = 'linear'
            hub_note = None
        elif n <= 5:
            strategy = 'full_mesh'
            hub_note = None
        else:
            strategy = 'hub_spoke'
            # Per-note shared tag count for hub selection
            per_note_tags: Dict[str, List[str]] = {}
            for note in notes_list:
                per_note_tags[note] = [
                    t for t in group_specific_shared
                    if note in analyzer.notes_by_tag.get(t, [])
                ]
            hub_note = select_hub_note(notes_list, per_note_tags)

        # Build rationale
        if group_specific_shared:
            rationale = f"{len(notes_list)} notes share tags [{', '.join(group_specific_shared[:3])}]"
            if avg_title_overlap > 0:
                rationale += f"; title similarity {avg_title_overlap:.2f}"
        else:
            rationale = f"{len(notes_list)} notes have title similarity {avg_title_overlap:.2f}"

        candidate_id = deterministic_cluster_id(notes_list)
        note_titles = [Path(n).stem for n in notes_list]

        candidates.append({
            'candidate_id': candidate_id,
            'suggested_name': suggested_name_from_tags(group_specific_shared) if group_specific_shared else 'Title-Similar Group',
            'shared_tags': group_specific_shared,
            'notes': notes_list,
            'note_titles': note_titles,
            'score': round(score, 4),
            'rationale': rationale,
            'suggested_strategy': strategy,
            'hub_note': hub_note,
        })

    # Sort by score descending
    candidates.sort(key=lambda c: c['score'], reverse=True)

    return {
        'candidates': candidates,
        'metadata': {
            'total_candidates': len(candidates),
            'vault_notes': total_notes,
            'unclustered_notes': len(unclustered),
            'already_clustered': len(existing_notes),
            'generic_tag_threshold': generic_threshold,
            'specific_tags_count': len(specific_tags),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description='Discover candidate note clusters via tag co-occurrence and title similarity'
    )
    parser.add_argument(
        '--vault-path',
        type=Path,
        default=Path(__file__).parent.parent / 'Lifegames',
        help='Path to Obsidian vault (default: ../Lifegames)',
    )
    parser.add_argument(
        '--clusters',
        type=Path,
        default=Path(__file__).parent.parent / 'linked_notes_clusters.json',
        help='Existing cluster definitions file (default: ../linked_notes_clusters.json)',
    )
    parser.add_argument(
        '--generic-tag-pct',
        type=float,
        default=0.05,
        help='Exclude tags appearing in more than this fraction of notes (default: 0.05)',
    )
    parser.add_argument(
        '--min-notes',
        type=int,
        default=2,
        help='Minimum notes per candidate cluster (default: 2)',
    )
    parser.add_argument(
        '--max-notes',
        type=int,
        default=15,
        help='Maximum notes per candidate cluster — larger groups are dropped (default: 15)',
    )
    parser.add_argument(
        '--min-shared-tags',
        type=int,
        default=2,
        help='Minimum shared specific tags for a tag-based pair to be linked (default: 2)',
    )
    parser.add_argument(
        '--title-overlap',
        type=float,
        default=0.5,
        help='Minimum Jaccard title word overlap to link two notes (default: 0.5)',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Write JSON output to this file (default: stdout)',
    )

    args = parser.parse_args()

    if not args.vault_path.exists():
        print(f"Error: Vault path does not exist: {args.vault_path}", file=sys.stderr)
        return 1

    result = discover_clusters(
        vault_path=args.vault_path,
        clusters_file=args.clusters,
        generic_tag_pct=args.generic_tag_pct,
        min_notes=args.min_notes,
        max_notes=args.max_notes,
        min_shared_tags=args.min_shared_tags,
        title_overlap_threshold=args.title_overlap,
    )

    meta = result['metadata']
    print(f"\nDiscovery complete:", file=sys.stderr)
    print(f"  Candidates found:   {meta['total_candidates']}", file=sys.stderr)
    print(f"  Vault notes:        {meta['vault_notes']}", file=sys.stderr)
    print(f"  Unclustered notes:  {meta['unclustered_notes']}", file=sys.stderr)
    print(f"  Already clustered:  {meta['already_clustered']}", file=sys.stderr)

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json)
        print(f"  Output written to:  {args.output}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == '__main__':
    exit(main())
