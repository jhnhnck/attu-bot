# ccboard

reference for the ccboard feature — the replacement for the legacy starboard. behavior rules, embed structure, configuration, and code pointers.

ccboard is gated by `GuildCCBoard.enabled` (default `False`); when off, the legacy starboard remains active and ccboard is dormant. on the `False → True` transition the manager picks up dirty entries and the watcher starts recording reactions; both systems can run in parallel during a migration window since their slash commands are disjoint.

---

## architecture

```
apps/bot/doom_bot/ccboard/
  __init__.py        # shared per-message lock dict + _pending_bot_removals echo-suppression set
  watcher.py         # raw reaction event handlers; backfill, redirect, one-vote enforcement
  manager.py         # ManagerTask(BaseTask); 10s poll, 60s settle debounce
  builder.py         # rule-pipeline embed builder; pure (entry, config, state) → state
  migration.py       # one-shot starboard → ccboard data migration
  auditor.py         # AuditorTask(BaseTask); manual-only stub; reconcile/recount/discover/orphan passes (phase 2)
```

state lives in two collections:

- **`ccboard_reactions`** — `ReactionDocument`, one per `(message_id, user_id)`. soft-deleted on remove, refreshed in place on same-emoji re-react, replaced on different-emoji vote change.
- **`ccboard_entries`** — `BoardEntryDocument`, one per tracked message. holds the static `MessageDocument` snapshot taken at first track, the `effective_author_id` (resolved credit author), `is_dirty` pickup flag, and the leaderboard-relevant aggregates (`net_points`, `positive_points`).

both repositories live in `packages/shared-models/attu_models/`. the bot wires `_reaction_repo` and `_entry_repo` into `doom_bot.ccboard` at startup via `database/__init__.py`.

---

## configuration

per-guild in mongodb under `ccboard`:

| field | type | purpose |
|---|---|---|
| `enabled` | `bool` | feature flag; legacy starboard active when False |
| `channel_id` | `int` | id of the ccboard channel |
| `emojis` | `dict[str, int]` | emoji → signed integer point value (e.g. `{'⭐': 1, '💀': -1}`) |
| `super_bonus` | `int` | extra points added for a burst/super reaction (default 1) |
| `threshold` | `int` | minimum positive points to create a board post (default 2) |
| `points_label` | `str` | display name for points in the post content string (default `'stars'`) |
| `positive_color` | `str` | embed hex color when `net_points > 0` (default `'#EEDD20'`) |
| `negative_color` | `str` | embed hex color when `net_points <= 0` (default `'#DD2020'`) |

only emojis listed in `emojis` are tracked. any other reaction is silently ignored.

config plumbing covers the full tier-3 path: `GuildConfigDocument`, `GuildConfig`, `NovaConfig.load_guild()`, `GuildConfigForm` (web), and the guild-config web UI tab. saves trigger an audit log and a reload signal so live toggles take effect without a restart.

---

## behavior rules

- any user can react to any message with a configured emoji
- self-reactions don't count and are auto-removed; the self check uses `effective_author_id` so bot-attributed messages still credit the original user
- reactions **by** bot users are ignored; bot-**authored** messages remain eligible
- each user gets **one vote per message** across all configured emojis
- reactions on the board post itself redirect to the original message; reactions on `/stars` display messages also redirect (multi-key index on `display_message_ids`)
- a board post is created when `positive_points >= threshold`; threshold uses positive-value emojis only
- negative-value emojis count toward `net_points` but cannot block posting on their own
- a board post is deleted when `positive_points` drops below threshold; the reference is cleared so a new post can be created if reactions recover later
- if all reactions on a message are cleared (moderator wipe), the bot soft-deletes every reaction record on that message and deletes the board post if one exists
- if a board post is deleted externally, `starboard_message_id` is cleared on the next sync and a new post is created on the next dirty-entry tick
- a reaction record is only soft-deleted on an explicit `reaction_remove` event — never assumed removed
- bot-removal echo suppression: every time the watcher calls `discord.remove_reaction` itself, it registers a `(channel_id, message_id, user_id, emoji_str)` key on `_pending_bot_removals` before the api call. the echoed `on_raw_reaction_remove` consumes the key and returns early. without this, vote changes and self-star auto-removals would corrupt point totals.

---

## attribution: `effective_author_id`

when a starred message is bot-authored AND a reply (`snapshot.refs.reply_to` is set), `effective_author_id` is set to the reply target's author id. this covers the common case of bot command responses replying to a user message. leaderboards, sweep streak counting, and the self-star check all use `effective_author_id or author_id`.

attribution is resolved best-effort during backfill and during migration. if the reply target is unavailable from the messages collection or discord, `effective_author_id` stays `None` and `author_id` is used. there is currently no automatic re-resolution path.

---

## post format

content string: `f'{net_points} {points_label} | {jump_url}'`

embed color: `positive_color` if `net_points > 0`, else `negative_color`.

embed content is built by the rule pipeline from a static `snapshot: MessageDocument` (and optional `reply_snapshot`). edits to the original message are intentionally not reflected — the snapshot is taken at first tracking and never updated.

rules applied in order:

1. `rule_base` — author, timestamp, jump url, color
2. `rule_reply_context` — prepend reply-context embed when `reply_snapshot` is set
3. `rule_text_content` — `description` from `snapshot.content.text`
4. `rule_primary_image` — first image attachment → `image.url` and `embed.url = jump_url`
5. `rule_extra_images` — remaining images → extra embeds, each with `url = jump_url` so discord renders a connected gallery (multi-image fix vs. legacy starboard)
6. `rule_link_previews` — hydrate stored embed metadata; simple previews merge into main, rich ones become extra embeds
7. `rule_sticker` — sticker-only messages → sticker url as image, description = `*sticker*`
8. `rule_voice_memo` — voice memo → no-preview notice
9. `rule_gif` — gif/gifv links → real gif url, not the png proxy
10. `rule_forwarded` — forwarded messages → footer marker

helpers (`parse_jump_url`, `_is_image`, `_looks_like_image_url`, `_hydrate_stored_embed`, `_should_merge_stored_embed`, `_parse_color`) are reused from the legacy starboard via direct import — not duplicated.

---

## key functions

| function | module | purpose |
|---|---|---|
| `handle_reaction_add(...)` | `watcher` | `on_raw_reaction_add` entry point; backfill + one-vote enforcement |
| `handle_reaction_remove(...)` | `watcher` | `on_raw_reaction_remove`; consumes `_pending_bot_removals` key first |
| `handle_reaction_clear(...)` | `watcher` | bulk soft-delete on full clear |
| `handle_reaction_clear_emoji(...)` | `watcher` | bulk soft-delete by emoji |
| `ManagerTask.run()` | `manager` | 10s poll; finds dirty entries past the 60s settle debounce |
| `_sync_post(entry, config)` | `manager` | create/update/delete the board post for one entry |
| `build_embeds(entry, config)` | `builder` | runs the rule pipeline and returns the full embed list |
| `job_convert_starboard_to_ccboard(...)` | `migration` | one-shot starboard → ccboard data migration |
| `AuditorTask` (+ `reconcile_entry`, `reconcile_guild`, `recount_entry`, `discover_guild`, `cleanup_orphans`) | `auditor` | manual-trigger task; phase 2.0 stub (each pass returns a `PassResult` with `dry_run=True`); real implementations land in phases 2.2-2.5 |

---

## sweeps

after a *new* board post is created (not an update), the manager counts the leading run of consecutive posts by the same credited author (`effective_author_id or author_id`) at the tail of the guild's board history (ordered by `last_synced_at` descending). streak breaks when any other author appears.

| streak | announcement |
|---|---|
| 3 | `**<@user> sweaps!**` |
| 5 | `**<@user> sweaps more!**` |
| 11 | `**<@user> sweaps even more!**` |

only announces at exactly those counts. sent as an embed in the ccboard channel with bot theme color and no title or footer. errors during sweep checks are swallowed so they never block post creation.

---

## commands

phase 1 ships admin / debug coverage. user-facing `/stars random/lost/recheck/leaderboard` against ccboard is deferred — the legacy `/stars` continues to operate against the legacy starboard until ccboard takes over per-guild.

| command | purpose |
|---|---|
| `/fix stars convert` | one-shot migration; copies `starboard` records into `ccboard_reactions` + `ccboard_entries`. idempotent. requires `confirm=True` and a non-empty `ccboard.emojis`. |
| `/fix ccboard regen` | marks every entry in the guild dirty so the manager rebuilds all posts on the next tick |
| `/fix ccboard purge <link>` | accepts the original message, the board post, or a `/stars` display message; soft-deletes every reaction record, deletes the board post if linked, removes the entry |
| `/fix ccboard recover` | auditor discovery pass — phase 2.0 walking-skeleton stub; calls `auditor_task.discover_guild(dry_run=True)`; real scoped discovery is phase 2.4 |
| `/fix ccboard recount` | auditor reconciliation pass — phase 2.0 walking-skeleton stub; calls `auditor_task.reconcile_guild(dry_run=True)`; real per-entry reconcile is phase 2.2 |
| `/debug ccboard show_reactions <link>` | lists every `ReactionDocument` (active and removed) for one entry with point value, super flag, source location, and `reacted_at` |
| `/cc stars test` | walking-skeleton placeholder for the future ccboard-backed `/stars` surface (random/lost/recheck/leaderboard); phases 2.6-2.8 replace this stub |

---

## known gaps

- **missed `reaction_add`**: no self-healing in phase 1; reaction exists on discord but no `ReactionDocument` is created. only the auditor (phase 2) corrects this.
- **missed `reaction_clear` aggregate**: individual users who re-react self-heal, but phantom votes from users who don't return persist until auditor reconciliation.
- **`effective_author_id` re-resolution**: once set (or left None) during backfill, attribution is never revisited. no command or automatic path exists to re-resolve.
- **config weight retroactive recalculation**: changing emoji weights leaves existing `ReactionDocument.point_value` snapshots at old values. same-emoji re-react refreshes `point_value` for active users; there is no bulk recalculation path.
- **user-facing `/stars` against ccboard**: not yet implemented. legacy `/stars` continues to operate against the legacy starboard.

---

## metadata

```yaml
last_updated: 2026-05-09
status: phase 2.0 walking skeleton — auditor task and /cc stars stubs registered; recount semantic awaits user-approval gate (phase 2.1)
```
