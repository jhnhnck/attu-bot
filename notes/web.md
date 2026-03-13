# Web Interface

Reference for the Quart-based admin dashboard - structure, auth, routes, and how to extend it.

---

## Overview

The web interface is a Quart (async Flask) app launched via `python attu-bot.py web`. It runs on port 5000, bound to localhost, behind a reverse proxy in production. Auth is WebAuthn passkeys only - no passwords.

---

## File Layout

| File | Role |
|---|---|
| `attubot/web/app.py` | `create_app()`, startup lifecycle (`before_serving`), security headers, CSP nonce |
| `attubot/web/routes.py` | All page and API routes registered in `register_routes(app)` |
| `attubot/web/auth.py` | WebAuthn registration and login routes registered in `register_auth_routes(app)` |
| `attubot/web/forms.py` | Pydantic form models (`GuildConfigForm`, `ThemeConfigForm`, `SystemConfigForm`) |
| `attubot/web/audit.py` | `AuditLogger` class, `compare_configs()`, `get_client_ip()` |
| `attubot/web/discord_integration.py` | Cached Discord API calls (channels, roles, guild info) |
| `assets/templates/` | Jinja2 templates; `base.html` is the layout shell |
| `assets/templates/components/` | Reusable partials (e.g. `guild_nav.html`) |
| `assets/static/js/modules/` | ES6 module library (api, forms, ui, discord, webauthn, etc.) |
| `assets/static/js/pages/` | Per-page initialization scripts |
| `assets/static/js/app.js` | Legacy global script (still used by guild config page) |
| `assets/static/css/custom.css` | Custom styles (Bootstrap 5 from CDN) |

---

## Routes

### Page Routes (HTML)

| Route | Handler | Template |
|---|---|---|
| `GET /` | `index` | `index.html` |
| `GET /guild/<id>` | `guild_config_page` | `guild_config.html` |
| `GET /guild/<id>/years` | `guild_years_page` | `years.html` |
| `GET /guild/<id>/markers` | `guild_markers_page` | `markers.html` |
| `GET /guild/<id>/time` | `guild_time_page` | `time_status.html` |
| `GET /theme` | `theme_config_page` | `theme_config.html` |
| `GET /system` | `system_config_page` | `system_config.html` |
| `GET /audit` | `audit_log_page` | `audit_log.html` |
| `GET /admin/stats` | `admin_stats_page` | `admin_stats.html` |

### Auth Routes (in `auth.py`)

| Route | Purpose |
|---|---|
| `GET /auth/login` | Login page |
| `POST /auth/login/begin` | Generate WebAuthn challenge |
| `POST /auth/login/complete` | Verify passkey assertion |
| `POST /auth/logout` | Clear session |
| `GET /auth/setup` | Initial setup (when no passkeys exist) |
| `POST /auth/setup/begin` / `/complete` | Register first passkey |
| `GET /auth/passkeys` | Manage registered passkeys |
| `POST /auth/register/begin` / `/complete` | Register additional passkey |

### API Routes (JSON)

| Route | Purpose |
|---|---|
| `GET /api/guilds` | List authorized guilds |
| `GET /api/guilds/<id>` | Full guild config |
| `POST /api/guilds/<id>` | Save guild config |
| `POST /api/guilds/<id>/validate` | Validate without saving |
| `POST /api/guilds/<id>/reset` | Reload from database |
| `GET /api/guilds/<id>/channels` | Fetch Discord channels (cached) |
| `GET /api/guilds/<id>/roles` | Fetch Discord roles (cached) |
| `GET /api/guilds/<id>/info` | Fetch guild info (cached) |
| `POST /api/guilds/<id>/refresh` | Invalidate Discord cache |
| `GET/POST /api/theme` | Get or save theme config |
| `GET/POST /api/system` | Get or save system config |
| `GET /api/audit` | Audit log with filters |
| `GET/POST/DELETE /api/guilds/<id>/years/...` | Years CRUD |
| `GET/POST/DELETE /api/guilds/<id>/markers` | Markers CRUD |

### Special

- `GET /health` - unauthenticated health check
- Public paths (no auth required): `/auth/*`, `/static/*`, `/health`

---

## Auth & Security

- Global `before_request` hook registered in `register_auth_routes()` enforces auth on all other routes
- If no passkeys exist, every request redirects to `/auth/setup`
- CSRF: state-changing requests (POST/PUT/DELETE) must include `X-CSRF-Token` header or form field; token is injected into templates via `g.csrf_token`
- Rate limits: 60 req/min global; 10 req/min on auth endpoints
- Security headers set per-response: CSP with per-request nonce (`g.csp_nonce`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, etc.
- Discord IDs in JSON responses must be serialized as **strings** to avoid JS precision loss (enforced in existing routes)

---

## Cross-Process Signals

Config saves in the web process must notify the bot process to reload. This uses a MongoDB-based signal mechanism - not blinker or WebSockets.

**Sending a signal** (web side, in `routes.py`):
```python
from attubot.signals import send_signal

# after a successful db save:
await send_signal('guild', guild_id)  # or 'theme', 'system', 'chat'
```

- `send_signal()` upserts to the `reload_signals` collection; errors are caught and logged, never re-raised
- Upserts are idempotent - rapid saves of the same (type, guild_id) coalesce into one pending signal

**Consuming signals** (bot side): `ReloadWatcherTask` in `attubot/tasks/reload_watcher.py` polls every 5 seconds with `repo.consume_all()`, which atomically deletes and returns all pending signals. Each type maps to a config reload method.

**Adding a new config type that the bot needs to react to**:
1. Emit `await send_signal('yourtype')` after the web save
2. Add `'yourtype'` to the `Literal` in `ReloadSignalDocument` in `database/models.py`
3. Handle it in `reload_watcher.py`

---

## Audit Logging

All config mutations must be logged. The `AuditLogger` singleton is available as `web_app.audit_logger` inside route handlers (imported from `app.py`).

```python
from attubot.web.app import web_app
from attubot.web.audit import compare_configs, get_client_ip

# compare old and new config to build a list of changes:
changes = compare_configs(old_config.model_dump(), new_config.model_dump())
await web_app.audit_logger.log_change(
    ip=get_client_ip(request),
    config_type='guild',   # 'guild' | 'theme' | 'system' | 'year' | 'marker'
    action='update',       # 'create' | 'update' | 'delete'
    changes=changes,
    guild_id=guild_id,
)
```

---

## Form Validation

Pydantic models in `forms.py` validate request JSON before any save. Return `400` on `ValidationError`:

```python
from pydantic import ValidationError
from attubot.web.forms import GuildConfigForm

try:
    form = GuildConfigForm.model_validate(await request.get_json())
except ValidationError as e:
    return jsonify({'error': e.errors()}), 400
```

Existing form models: `GuildConfigForm`, `ThemeConfigForm`, `SystemConfigForm`.

---

## Discord Cache

`discord_integration.py` wraps bot API calls with an in-memory cache (300s TTL).

- `get_guild_channels(guild_id)` - includes text channels, voice channels, and public/private threads
- `get_guild_roles(guild_id)`
- `get_guild_info(guild_id)`
- `invalidate_guild_cache(guild_id)` - clears all cached data for a guild

The cache is per-process; the web container has its own Discord connection separate from the bot container.

---

## JavaScript Structure

ES6 modules, no transpilation. New pages follow this pattern:

1. Create `assets/static/js/pages/<page>.js` - imports from `modules/` and calls init on `DOMContentLoaded`
2. Load it in the template:
   ```html
   <script type="module" src="{{ url_for('static', filename='js/pages/<page>.js') }}"></script>
   ```

Key modules:

| Module | Purpose |
|---|---|
| `modules/api.js` | `fetch` wrappers - handles CSRF header, JSON, error responses |
| `modules/ui.js` | Toast notifications, loading states |
| `modules/forms.js` | Form serialization, field binding |
| `modules/discord.js` | Channel/role select population from API |
| `modules/webauthn.js` | WebAuthn client-side logic |
| `modules/years.js` | Years management UI |
| `modules/markers.js` | Markers management UI |
| `modules/time.js` | Time status page |
| `modules/admin.js` | Admin stats page |

The guild config page still uses the legacy `app.js` global script.

---

## Adding a New Page

1. Create `assets/templates/<page>.html` extending `base.html`
2. Add a page route in `routes.py` that calls `render_template('<page>.html', ...)`
3. Create `assets/static/js/pages/<page>.js` if client-side logic is needed
4. Add any required API endpoints (see pattern below)

## Adding a New API Endpoint

All routes are defined inside `register_routes(app)` in `routes.py`. Auth is enforced globally so no per-route decorator is needed. Standard shape:

```python
@app.route('/api/example', methods=['GET'])
async def api_example():
    # validate input, hit db, return json
    return jsonify({'data': ...})

# on failure:
return jsonify({'error': 'reason'}), 400

# on success mutation:
return jsonify({'success': True, 'message': 'Saved'})
```

After a successful write: emit a signal if the bot needs to reload, then log to `audit_logger`.
