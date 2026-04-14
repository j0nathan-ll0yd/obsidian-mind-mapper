# Link Notes Command

You are helping to **discover and apply bi-directional wiki links** between related Obsidian notes in the Lifegames vault.

This command uses tag co-occurrence and title similarity to find notes that cover the same topic, story, or subject, then links them via the `## Linked Concepts` section.

## Tools Available

1. **`src/discover_clusters.py`** - Discovers candidate note clusters
   - Analyzes live vault tags and title similarity
   - Excludes notes already in `linked_notes_clusters.json`
   - Outputs scored candidates with suggested linking strategy

2. **`src/link_related_notes.py`** - Applies wiki links based on cluster definitions
   - Reads `linked_notes_clusters.json`
   - Adds bi-directional `[[wiki links]]` to `## Linked Concepts` sections
   - Supports `--dry-run` mode

## Your Task

Follow this workflow:

---

### Phase 1: Discovery

Run the discovery script:

```bash
cd /Users/jlloyd/Repositories/obsidian-mind-mapper
source venv/bin/activate
python src/discover_clusters.py --output /tmp/link_candidates.json
```

Read `/tmp/link_candidates.json` and present a summary:

```
Found N candidate clusters across M notes.
Already clustered: X notes. Vault total: Y notes.
```

---

### Phase 2: Batch Presentation

Show candidates in batches of 5, sorted by score (highest first). For each candidate show:

```
[N] Score: 0.85 | Strategy: full_mesh | 3 notes
    Name: Joan Crawford Stage Productions
    Notes:
      1. Joan Crawford Superstar Intentional Theatrics' Stage Biography of Hollywood Icon
      2. Joan Crawford Superstar Loving Bio at Theater 33
      3. Joan Crawford Superstar at Theatre Eddys
    Shared tags: Hollywood, Joan-Crawford, Theater-33
    Rationale: 3 notes share tags [Hollywood, Joan-Crawford]; title similarity 0.61
```

For hub_spoke candidates, also show:
```
    Hub note: [hub note title]
```

After each batch of 5, ask:

```
Options: (a) approve all  (1,3,5) approve by number  (d N) deep-dive into N  (n) next batch  (q) done
```

---

### Phase 3: Deep-Dive (on demand)

When the user requests `d N` for candidate N:

1. Read the `## Summary` and `## Key Points` sections from each note in that cluster
2. Present the content clearly, one note at a time
3. Ask: "Approve as-is / Approve with modifications / Reject"
4. If "Approve with modifications": allow the user to add or remove specific notes before approving

---

### Phase 4: Finalization

Collect all approved clusters. For each approved cluster:

1. Show a JSON preview of what will be added:
   ```json
   {
     "cluster_id": "auto_a1b2c3d4",
     "name": "Joan Crawford Stage Productions",
     "description": "...",
     "linking_strategy": "full_mesh",
     "notes": ["Note A.md", "Note B.md", "Note C.md"]
   }
   ```

2. **Idempotency check**: before appending, verify no `cluster_id` from approved clusters already exists in `linked_notes_clusters.json`. Skip any duplicates and notify the user.

3. Append all approved clusters to `linked_notes_clusters.json`:
   - Preserve all existing content exactly
   - Increment `metadata.total_clusters` by the number of clusters added
   - Update `metadata.description` if needed

4. Confirm: "Added N clusters to linked_notes_clusters.json. Total clusters: X."

---

### Phase 5: Link Application

Run the linker in dry-run mode first:

```bash
python src/link_related_notes.py --dry-run
```

Show the dry-run output. Ask the user to confirm before proceeding.

On confirmation, apply the links:

```bash
python src/link_related_notes.py
```

Report the final results:
- Notes modified
- Links added
- Errors (if any)

---

## Safety Features

- **Discovery is non-destructive**: `discover_clusters.py` only reads the vault
- **User approval required**: every cluster is reviewed before being added
- **Dry-run first**: always show what will change before applying links
- **Backups**: `link_related_notes.py` creates backups in `backups/note_linking/`
- **Idempotent**: clusters with existing IDs are skipped, not duplicated

## CLI Reference

```bash
# Basic discovery
python src/discover_clusters.py --output /tmp/link_candidates.json

# Adjust sensitivity (fewer, tighter clusters)
python src/discover_clusters.py --min-shared-tags 3 --output /tmp/link_candidates.json

# Adjust title similarity threshold (default 0.5)
python src/discover_clusters.py --title-overlap 0.6 --output /tmp/link_candidates.json

# Increase max cluster size (default 15)
python src/discover_clusters.py --max-notes 20 --output /tmp/link_candidates.json

# Apply links (dry run)
python src/link_related_notes.py --dry-run

# Apply links (live)
python src/link_related_notes.py
```

## Instructions

1. Start by running Phase 1 (discovery)
2. Present findings summary
3. Walk through Phase 2 batch review with the user
4. Perform deep-dives on request (Phase 3)
5. Finalize approved clusters (Phase 4)
6. Apply links after dry-run confirmation (Phase 5)

Always prioritize safety: present candidates for review before writing anything.
