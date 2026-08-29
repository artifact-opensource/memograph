# Windows Support

Memograph runs on Windows. This guide covers setup, known quirks, and the
bug fixes that make the package import- and run-clean out of the box on
Windows (and other non-POSIX platforms).

## Setup

```powershell
# Clone
git clone https://github.com/artifact-opensource/memograph
cd memograph

# Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install (editable)
pip install -e .

# Dev dependencies + run the test suite
pip install pytest pytest-cov
pytest tests/
```

> **PowerShell execution policy:** if `Activate.ps1` is blocked, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use
> `.\.venv\Scripts\activate.bat` from a `cmd.exe` prompt instead.

## What was fixed for cross-platform / Windows compatibility

These fixes are included in this branch so the package works on a clean
checkout (previously it failed to import and to run on Windows):

| # | File | Problem | Fix |
|---|------|---------|-----|
| 1 | `memograph/lifecycle/evictor.py` | `Any` referenced but not imported (`NameError`) | Added `Any` to the `typing` import |
| 2 | `memograph/engines/{graph,kv,lexical,structured,temporal}_adapter.py`, `memograph/engines/memory_store.py` | `ContentType` / `RetrievalEngine` / `ShardDomain` referenced but not imported | Added the missing imports from `core.shard` / `core.types` |
| 3 | `memograph/auth/permissions.py` | `PermissionEngine`, `PermissionContext`, `PolicyDecision` were used by the lifecycle promotion gate but never defined | Added minimal, behavior-correct stubs (default `PermissionEngine` allows all promotions) |
| 4 | `memograph/lifecycle/pipeline.py` | The 3 permission classes above were not imported; `LifecycleResult` constructor requires `target_shard` + `event` but the error paths omitted them | Imported the classes (with `ImportError` fallbacks) and supplied the required fields on error returns |
| 5 | `memograph/core/memograph.py` (`get_lineage`) | `visited` was pre-seeded with the start node, so the traversal loop never executed and always returned an empty lineage | `visited` now starts empty |
| 6 | `memograph/core/memograph.py` (`save`) | Used `os.O_CLOEXEC` + `os.rename`, which do not exist / behave differently on Windows (`AttributeError`) | Switched to `tempfile.mkstemp` + `os.replace` (atomic on both POSIX and Windows) |
| 7 | `memograph/core/shard.py` (`MemoryShard.create`) | `promote_shard` passed `version=...` but `create()` did not accept it | Added an optional `version` parameter (defaults to `1`) |
| 8 | `memograph/tools.py` (`_do_store`) | `MemoryEvent.create()` requires `event_id` but it was not passed | Added `event_id=int(time.time() * 1_000_000)` |
| 9 | `memograph/tools.py` (`_do_retrieve`) | `assemble_context` was called with a stray `query` positional arg (landing in the `max_tokens` slot); iteration was over the `ContextEnvelope` object instead of `.shards`; the query `scope` fell back to the domain name, filtering out every real shard | Removed the stray arg, iterate `selected.shards`, and only constrain the query by `scope` when one is explicitly supplied |

## Known limitations

- **Retrieval is lexical, not semantic.** The scoring in `ContextRouter`
  is a lightweight heuristic; true semantic/embedding search lives in the
  optional `hektor` extra (`pip install memograph[hektor]`) and is not
  bundled. On Windows the HEKTOR path still requires its native
  dependencies.
- **`os.replace`** is used for atomic writes; on network/FAT filesystems
  this is best-effort atomic, not guaranteed.
- The agent tool (`memograph_tool`) is a **singleton per `session_id`** and
  persists its graph to `.memograph_storage/<session_id>.json`. Stale files
  from earlier runs are reloaded on start — delete the file or use a fresh
  `session_id` to get a clean slate.
