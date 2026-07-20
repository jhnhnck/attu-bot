## pre-mortem

inline since the project doesn't have the `pre-mortem` skill installed yet. adversarial pass on the plan before phase 1; the output reorders phases and surfaces the walking skeleton.

**what fails this migration?**

- **R1 — configure-vs-import timing.** `structlog.stdlib.get_logger(__name__)` at module level snapshots config on first emit. `cache_logger_on_first_use=True` defers binding, but if a module emits before the entrypoint has called `configure()`, that logger uses structlog defaults forever (no ProcessorFormatter, no pycord bucket resolver, no console renderer). probability: high if we don't enforce "configure as line 1." mitigation: phase 0 establishes the rule, integration-check verifies it.
- **R2 — pytest bootstrapping.** tests don't run our entrypoints. `tests/conftest.py` must call `configure()`. today the wrapper's import-time `_configure()` side-effect masks this dependency; removing it surfaces the gap.
- **R3 — multi-process re-import.** bot and ingestor sometimes share a process; both could call `configure()`. idempotency guard via `_attu_owned` handler markers (same trick as today's wrapper).
- **R4 — library-noise pin loss.** the wrapper pins `pymongo`, `aiohttp.access`, `discord.gateway` to WARNING and (post-fix) `discord.http` to WARNING-or-DEBUG. forgetting any of them in the new configure regresses log volume in prod.
- **R5 — `.warn` / `.fatal` aliases.** structlog `BoundLogger` keeps these. the 561 call sites do **not** need to rename their methods.
- **R6 — `.trace` / `.alert` aliases.** structlog `BoundLogger` does **not** keep these. 2 sites repo-wide. must convert before the wrapper is deleted.
- **R7 — `send_to_webhook` migration ordering.** the free function must exist before any caller is migrated; the wrapper method must outlive the last caller. straightforward but trips you up if the phases are reordered.
- **R8 — phase-5 ordering.** deleting the wrapper before phase 4 has converted every importer breaks the build. the phase-4 DoD must include a grep that proves the wrapper is unimported by anything outside itself.
- **R9 — discord.http regression.** preserve the WARNING-default / DEBUG-when-DEBUG-env semantics. the recent unit tests (`TestDiscordHttpLevelGating`) move from `tests/python/unit/test_logging.py` to `tests/python/unit/test_attu_logging.py` in phase 5; they keep pinning the contract.
- **R10 — diff size for phase 4.** ~70 import sites in one phase is a big diff. mitigation: split phase 4 into directory-sized batches, each its own commit, each its own integration-check pass. the underlying risk is low *per site*; the risk is **review fatigue** missing a regression in the noise.
- **R11 — webhook home decision (D3).** if `webhook.py` lives in `attu_logging`, the package widens slightly past "logging." if it lives in `shared-models`, that package gains an outbound-network responsibility. either is fine; pick one, document it. waffling causes an inter-phase rewrite.

**reordering produced by this pre-mortem:**

- the original draft put phase 1 = "shared-models flip." the pre-mortem says R1+R2 are higher-risk than the shared-models flip itself, so **walking skeleton goes first** and proves the configure-at-entrypoint contract end-to-end before anything else moves.
- TRACE/ALERT removal (R6) and `send_to_webhook` extraction (R7) are both preconditions for phase 5 (delete the wrapper). they slot in as discrete phases ahead of the bulk conversion so each retro is clean.
- phase 4 (bulk conversion) is split into commits-per-directory rather than one monolithic commit (R10).
