# Data quality and legal coverage — V3

## Rules

- One legal document has one primary legal domain; chunks are not independently relabeled into unrelated domains.
- Duplicates are controlled by source/document identity and normalized content hash.
- Generic index/list pages are discovery sources, not substantive evidence.
- URL-encoded filenames and UUID-like filenames are cleaned before reaching users.
- Unreadable PDF Arabic extraction is not shown as reliable article evidence.
- Official service/guidance facts are ranked above noisy PDF layers for operational questions.
- A base-law reference is not represented as a complete consolidated statute.
- A later amendment is not silently treated as the full base law.
- Named-conduct guards prevent unrelated punishment clauses from being returned for a specific offence.
- Direct values (penalties, deadlines, fees) require explicit evidence.

## Local storage

The zero-configuration pilot uses `data/qanoni.sqlite3`. It stores the legal corpus and local conversation history. Before release packaging, conversation/message tables are cleared.

## Update strategy

The source registry and synchronization code are retained for future updates, but exact high-stakes answers should be acceptance-tested after every major corpus refresh.
