---
name: pydantic
description: pydantic v2 reference card for AttuBot - validation, serialization, the document/runtime model split, and the tier-3 config plumbing checklist. trigger when editing or creating files under `packages/shared-models/attu_models/`, `apps/bot/nova_core/config.py`, `apps/bot/nova_core/client/markers.py` or `years.py`, or `apps/server/attu_server/`; when any file imports pydantic; when adding or renaming guild config fields; when writing field_validator / model_validator / ConfigDict; when answering questions about validation, model serialization, ValidationError handling, or "why is this config value not being read from the database".
---

# pydantic reference

scope: pinned to **pydantic v2** (lockfile: 2.12.5; pyproject.toml unpinned but specifies v2 idioms throughout). if `uv.lock` advances to pydantic 3.x, this skill is stale and must be re-verified against the v3 docs.

pydantic v1 → v2 was a breaking rewrite. v1 muscle memory (`@validator`, `class Config`, `parse_obj`, `dict()`) still surfaces in llm output and is wrong here. trust this file and the existing repo code over training-data recall.

## v1 → v2 cheat sheet

flag any of the left column on sight; rewrite to the right.

| v1 | v2 |
|---|---|
| `@validator('x')` | `@field_validator('x')` + `@classmethod` |
| `@root_validator` | `@model_validator(mode='before')` + `@classmethod`, **or** `@model_validator(mode='after')` (instance method, returns `self`) |
| `class Config: ...` (inner class) | `model_config = ConfigDict(...)` (class attribute) |
| `Config.allow_population_by_field_name = True` | `ConfigDict(populate_by_name=True)` |
| `Config.orm_mode = True` | `ConfigDict(from_attributes=True)` |
| `Config.allow_mutation = False` | `ConfigDict(frozen=True)` |
| `Model.parse_obj(d)` | `Model.model_validate(d)` |
| `Model.parse_raw(s)` | `Model.model_validate_json(s)` |
| `instance.dict()` | `instance.model_dump()` |
| `instance.json()` | `instance.model_dump_json()` |
| `instance.copy()` | `instance.model_copy()` |
| `Model.__fields__` | `Model.model_fields` |
| `Model.schema()` | `Model.model_json_schema()` |
| `Field(..., regex=r'...')` | `Field(..., pattern=r'...')` |
| `Field(..., min_items=1)` | `Field(..., min_length=1)` (lists/sets/dicts use length now) |
| `pydantic.error_wrappers.ValidationError` | `pydantic.ValidationError` |

`@validator` decorators that show up in this repo are bugs; rewrite them.

## ConfigDict options

```python
from pydantic import BaseModel, ConfigDict


class GuildConfigDocument(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='ignore')
    ...
```

options actually used in this repo:

| option | effect |
|---|---|
| `extra='ignore'` (every document model) | unknown keys in the input are **silently dropped**. tolerates schema drift on read but is the root of the tier-3 footgun: a field not declared on the document model is invisible no matter what mongodb stores. |
| `arbitrary_types_allowed=True` (`GuildConfigDocument` only) | permits non-pydantic types as field annotations; needed because `epoch`/`channels`/`roles`/`users` are typed as raw `dict`. |

three `extra` modes exist; this repo uses `'ignore'` exclusively:

- `'ignore'` - drop unknown keys, no error. **default in this codebase.**
- `'allow'` - keep unknown keys on the model as `__pydantic_extra__`. avoid; defeats the schema.
- `'forbid'` - raise `ValidationError` on unknown keys. only use for forms / api boundaries where a typo should hard-fail.

other options worth knowing (not currently used here): `frozen=True`, `populate_by_name=True`, `str_strip_whitespace=True`, `validate_assignment=True`, `from_attributes=True`.

## validators

### `@field_validator`

```python
from pydantic import BaseModel, field_validator


class EggDocument(BaseModel):
    collected_at: int
    hatches_at: int

    @field_validator('collected_at', 'hatches_at', mode='before')
    @classmethod
    def coerce_to_int(cls, v: object) -> int:
        return int(v)  # pyright: ignore[reportArgumentType]
```

- **always** decorate with `@classmethod` directly under `@field_validator`; v2 enforces this.
- `mode='before'` runs against the raw input (string from a form, float from json) before pydantic's own coercion. use it to migrate legacy formats or accept multiple shapes.
- `mode='after'` (the default) runs once the field has been parsed to its declared type; use for cross-field-independent invariants.
- pass multiple field names to apply one validator to several fields.
- `mode='wrap'` and `mode='plain'` exist but aren't used in this repo.

### `@model_validator`

two distinct shapes; do not mix them up.

```python
from pydantic import BaseModel, model_validator


class GuildEpoch(BaseModel):
    time: int = 0
    year: int = 1
    length: int = 14
    paused: bool = True
    rollover_minutes: int = 1020

    # mode='before' - classmethod operating on raw input dict; returns dict
    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        if 'rollover_time' in data and isinstance(data['rollover_time'], str):
            h, m = data['rollover_time'].split(':')
            data['rollover_minutes'] = int(h) * 60 + int(m)
            del data['rollover_time']
        elif 'rollover_minutes' not in data:
            data['rollover_minutes'] = 1020
        return data
```

```python
class Example(BaseModel):
    a: int
    b: int

    # mode='after' - INSTANCE method (no @classmethod); returns self
    @model_validator(mode='after')
    def check_invariant(self) -> 'Example':
        if self.a > self.b:
            raise ValueError('a must be <= b')
        return self
```

footguns:
- `mode='before'` returning anything other than a dict (or whatever the model accepts as input) silently breaks validation.
- `mode='after'` returning a non-`self` value replaces the instance, almost never what you want; just `return self`.
- forgetting `@classmethod` on `mode='before'` raises a confusing v2 error (`first argument must be classmethod`).
- the repo's `GuildEpoch.setup` is the canonical legacy-migration example; mirror its shape when migrating other stored formats.

### Field constraints

```python
from pydantic import Field


class GuildEpochForm(BaseModel):
    length: int = Field(default=14, ge=1, le=365)
    rollover_minutes: int = Field(default=1020, ge=0, lt=1440)
    bot_color: str = Field(default='#ff0000', pattern=r'^#[0-9a-fA-F]{6}$')
    lore_channels: list[int] = Field(default_factory=list)
```

- numeric: `ge`, `gt`, `le`, `lt`, `multiple_of`.
- string: `min_length`, `max_length`, `pattern` (regex; was `regex` in v1).
- collection: `min_length`, `max_length` (was `min_items` / `max_items` in v1).
- mutable defaults (lists, dicts, sets): always `default_factory=list` / `default_factory=dict`, never `default=[]`. v2 still accepts `field: list[int] = []` because it auto-deepcopies, but `default_factory` is clearer and matches `web/forms.py`.

`Annotated[int, Field(ge=0)]` is equivalent and works fine; the repo uses bare `Field(...)` defaults consistently, so prefer that for consistency.

## serialization & parsing

| call | use |
|---|---|
| `Model.model_validate(d)` | parse a python dict (or any object with attrs if `from_attributes=True`). triggers full validation. |
| `Model.model_validate_json(s)` | parse a json string; faster than `model_validate(json.loads(s))`. |
| `instance.model_dump()` | dict of field values. options: `exclude_none=True`, `exclude_defaults=True`, `exclude={'field'}`, `include={...}`, `by_alias=True`, `mode='json'` (forces json-serializable primitives). |
| `instance.model_dump_json()` | json string in one shot. respects the same options. |
| `instance.model_copy(update={'field': value})` | shallow copy with overrides; does **not** re-run validators. use `Model.model_validate(instance.model_dump() \| {...})` if you need re-validation. |
| `Model.model_fields` | dict of `FieldInfo` keyed by field name; used to walk nested config sections generically. |

**discord snowflake / json quirk**: snowflakes are stored as `int` in mongodb (see the snowflake pitfall in `CLAUDE.md`) but **must** be serialized as strings whenever they cross into json; js `Number` loses precision above 2^53. plain `model_dump_json()` will emit them as integers, so the web layer either casts to `str(...)` explicitly or relies on form models that declare them as `int` on the way in but render them as strings in templates. don't trust the default for snowflakes; check the route.

## the document vs runtime model convention

```
mongodb document  ──►  document model           ──►  runtime model
                       (database/models.py)          (config.py, client/*.py)
                       extra='ignore'                wraps document; adds behavior
```

- **document models** live in `packages/shared-models/attu_models/documents.py`. pure persistence shape; field types match what mongodb stores; `extra='ignore'` for forward compat. examples: `GuildConfigDocument`, `YearDocument`, `YearMarkerDocument`, `MessageDocument`, `EggDocument`, `ChatConfigDocument`.
- **runtime models** live in `apps/bot/nova_core/config.py` (the `GuildConfig` family) or `apps/bot/nova_core/client/*.py` (`Year` in `years.py`, `YearMarker` in `markers.py`). they wrap a document, expose async `save()` / `update()` / `delete()` methods that call the repository, and host classmethods like `get(...)` / `all_for_guild(...)` that hydrate runtime instances from documents.
- the **conversion happens in one place per type**: `NovaConfig.load_guild()` for guild config; `Year.get` / `YearMarker.get` for the rest. that single hydration site is where missing fields silently default.

why the split: the document is the on-the-wire schema and must tolerate drift; the runtime model is the in-memory api surface and is allowed to add computed properties, async methods, and stricter typing without polluting mongodb's view.

## tier-3 config field plumbing - the three-step checklist

**this is the codebase's canonical silent-failure mode.** adding a guild-level config field but missing any of the three steps causes the field to silently use its hardcoded default in production regardless of what is stored in mongodb. there is no runtime warning.

1. **`packages/shared-models/attu_models/documents.py`** - add the field to `GuildConfigDocument` (or the relevant document model) with a default. `extra='ignore'` means anything not listed here is **dropped on read** - this is the root cause of the failure mode.
2. **`apps/bot/nova_core/config.py`** - add the field to the corresponding runtime model (`GuildConfig`, `GuildChannels`, `GuildEpoch`, `GuildRoles`, `GuildUsers`, `GuildStarboard`, etc.) with the same default.
3. **`apps/bot/nova_core/config.py`** - in `NovaConfig.load_guild()`, pass the value explicitly when constructing the runtime model from the document. **this is the step most often missed.** if the construction call is `GuildEpoch(**doc.epoch)` it will pick up the new field automatically; if it is a positional or hand-listed kwarg form, the new field is silently dropped.

there is no per-field web or form step any more: the legacy quart interface is gone, and the admin api patches any dotted key generically (`PATCH /admin/guilds/{slug}/config/{key}` in `apps/server/attu_server/api/admin/config_routes.py`) and validates the result against `GuildConfigDocument`. two consequences worth knowing:

- a field whose name ends in `_channel` or `_id` goes through `_resolve_snowflake`, so a patch may pass a channel or role slug instead of a raw snowflake.
- a field that gates a feature also needs an entry in `_FEATURE_FIELDS` (`apps/server/attu_server/api/admin/features.py`) before the enable and disable routes will accept its name.

**verification**: write a roundtrip test (`tests/python/component/test_db_repositories.py` has the templates - see `TestConfigRepositoryGuild.test_roundtrip`). save a document with the field set to a non-default value, reload via `load_guild()` (or the relevant repo `get_*`), assert the value survives. this is the **only** mechanical way to catch a missed step; the lint suite will not.

## tier-2 config field plumbing (toml)

simpler; two locations:

1. add the field to the relevant pydantic model in `config.py` (e.g. `BridgeConfig`, `BackupConfig`).
2. add it with a placeholder to `config/attu-bot.sample.toml` so a fresh deploy has a working stub.

if the toml file *format* changes (renamed key, new required section), bump `__config_version__` in `apps/bot/nova_core/__init__.py` so `_version_gte` rejects out-of-date config files. db schema migrations bump `__schema__` instead; do not confuse them.

## admin api route pattern

mutating routes live under `apps/server/attu_server/api/admin/` and are registered on the `/admin` router, which carries the api-key dependency. the shape:

```python
from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError


class ConfigPatch(BaseModel):
    value: Any


@router.patch('/guilds/{slug}/config/{key}')
async def patch_guild_config(slug: str, key: str, body: ConfigPatch, ...) -> dict[str, Any]:
    guild_id = resolve_guild_id(slug, await _build_guild_slug_map(config, bridge))
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')

    # validate the whole document after the edit, not just the field
    try:
        GuildConfigDocument.model_validate(doc_data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await repo.update_guild_field(guild_id, key, resolved)
    await bridge.invalidate_guild_cache(guild_id)
    await bridge.trigger_reload('guild', guild_id)
    return {'key': key, 'value': resolved}
```

mandatory parts when adding a new mutation route:

- parse the body with a pydantic model; never trust raw json.
- validate the resulting document against its document model before writing, so a bad patch is rejected rather than persisted.
- raise `HTTPException` with a useful `detail` on failure; return a plain dict on success.
- always call `bridge.trigger_reload(...)` after a successful save (plus `bridge.invalidate_guild_cache(guild_id)` for guild config) so the bot process reloads; missing this causes the bot's in-memory config to drift from mongodb until restart.
- serialize discord snowflakes as strings in the response; js `Number` loses precision above 2^53.

`ValidationError.errors()` returns a list of dicts with `loc` (tuple of str/int), `msg`, `type`, `input`, and optional `ctx`. `loc` is a path tuple - join with `.` to display field paths.

## common gotchas

- **`extra='ignore'` swallows typos.** `GuildConfigDocument(field_nmae=...)` succeeds with no warning; the misspelled key is dropped. always model-validate against a sample dict in tests when adding fields.
- **`mode='after'` model_validator must `return self`.** returning anything else (including `None`) replaces the instance with that value and breaks downstream code in baffling ways.
- **`mode='before'` validators need `@classmethod`.** v2 raises `'first argument must be classmethod'` if you forget; easy to miss when copy-pasting v1 code.
- **mutable default args.** prefer `Field(default_factory=list)` / `Field(default_factory=dict)` to `= []` / `= {}`. v2 deep-copies bare mutable defaults so `= []` is technically safe, but `default_factory` is unambiguous and matches what `web/forms.py` does.
- **`model_copy(update=...)` skips validation.** use `Model.model_validate(existing.model_dump() | overrides)` when you need fields re-validated.
- **`model_dump(mode='json')` ≠ `model_dump_json()`.** the first returns a dict whose values are json-compatible primitives; the second returns a json string. mongodb usually wants the dict form.
- **discord snowflake serialization.** snowflakes are `int` in mongodb and on the model; the web layer must cast to `str(...)` for any json response that crosses into js.
- **`ValidationError` import path.** v2: `from pydantic import ValidationError`. v1: `from pydantic.error_wrappers import ValidationError`. the v1 path is gone; flag any imports from `pydantic.error_wrappers`.
- **list/dict field constraints.** `Field(min_length=1)` not `min_items=1`; v2 unified the name.
- **`Field(..., regex=...)` is gone.** use `pattern=`.

## quick links

- pydantic v2 docs: https://docs.pydantic.dev/latest/
- v1 → v2 migration guide: https://docs.pydantic.dev/latest/migration/
- repo conventions: `docs/config-system.md` (three-tier config, adding new fields, schema versioning)
- canonical examples: `packages/shared-models/attu_models/documents.py` (documents), `apps/bot/nova_core/config.py` `GuildEpoch` (model_validator + legacy migration) and `NovaConfig.load_guild()` (hydration site), `apps/server/attu_server/api/admin/config_routes.py` (patch validation), `apps/bot/nova_core/client/years.py` and `apps/bot/nova_core/client/markers.py` (runtime-wraps-document pattern)
