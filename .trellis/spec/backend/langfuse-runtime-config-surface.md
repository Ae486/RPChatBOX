# Langfuse Runtime Config Surface

> Backend-owned Langfuse runtime configuration contract for local observability setup and WebUI handoff.

## Scenario: Backend Runtime Langfuse Configuration

### 1. Scope / Trigger
- Trigger: changes to `backend/api/langfuse.py`, `backend/models/langfuse_config.py`, `backend/services/langfuse_config_service.py`, or `backend/services/langfuse_service.py`.
- Scope: local runtime configuration, persistence, safe summary output, and immediate enable/disable behavior for Langfuse-backed observability.

### 2. Signatures
- `GET /api/observability/langfuse`
- `PUT /api/observability/langfuse`
- `LangfuseConfigService.get_effective_config_with_source()`
- `LangfuseConfigService.upsert_config(payload)`
- `reset_langfuse_service()`

### 3. Contracts
- Backend runtime config is owned by `LangfuseConfigService`, not by the frontend and not only by process env.
- Effective config resolution order:
  1. `storage/langfuse_settings.json` under `settings.storage_dir`
  2. Env-backed settings from `backend/config.py`
- `PUT /api/observability/langfuse` must:
  - persist the updated runtime config
  - reset the Langfuse singleton
  - rebuild the singleton immediately so enable/disable takes effect without backend restart
- Secret key is write-only on the API surface:
  - request payload may send `secret_key`
  - response summary must only expose `has_secret_key`
- Blank `secret_key` on update preserves the previously effective secret unless `clear_secret_key=True`.
- Summary payload must expose enough state for a settings page to render:
  - `enabled`
  - `configured`
  - `service_enabled`
  - `sdk_available`
  - `status_reason`
  - `source`
  - `public_key`
  - `has_secret_key`
  - `base_url`
  - `dashboard_url`
  - `environment`
  - `release`
  - `sample_rate`
  - `debug`
  - `config_path`
- `dashboard_url` defaults to `https://cloud.langfuse.com` when `base_url` is absent.
- `LangfuseService` must build the SDK client from the effective runtime config, not directly from `Settings`.
- Backend settings continue to expose `base_url`, but the Langfuse v2 Python SDK adapter must pass that value as `host` when constructing `Langfuse(...)`.

### 4. Validation & Error Matrix
- `enabled=False` -> summary `status_reason="disabled"` and service remains disabled.
- `enabled=True` but public/secret key incomplete -> summary `status_reason="missing_api_keys"` and service remains disabled.
- Langfuse SDK package missing -> summary `status_reason="sdk_unavailable"` even when config is otherwise complete.
- Langfuse SDK package present but missing required trace APIs -> summary `status_reason="sdk_incompatible"` and service remains disabled.
- SDK constructor throws -> summary `status_reason="client_init_failed"` and service remains disabled.
- Stored config file absent -> fall back to env-backed config with `source="env"`.
- Stored config file present -> use stored config with `source="storage"` even if env values differ.
- Backend runtime expects a Langfuse Python SDK version compatible with `start_as_current_observation(...)` and `propagate_attributes(...)`; keep `backend/requirements.txt` aligned with that floor.

### 5. Good / Base / Bad Cases
- Good: user saves keys once in settings, toggles monitoring on, and subsequent setup/eval traces emit to Langfuse without backend restart.
- Base: monitoring is disabled and summary still returns the default dashboard URL plus safe status fields.
- Bad: frontend toggles monitoring, but backend still reads only env settings, so UI state and actual trace emission drift apart.

### 6. Tests Required
- `backend/tests/test_langfuse_config_api.py`
  - default disabled summary
  - persisted update activates runtime
  - blank secret preserves existing secret
  - `clear_secret_key` clears persisted secret
- `backend/tests/test_langfuse_service.py`
  - disabled config remains noop-safe
- Any change to the Langfuse enablement path should also re-run the eval Langfuse sync regressions:
  - `backend/rp/tests/test_eval_langfuse_sync.py`
  - `backend/rp/tests/test_langfuse_scores.py`
  - `backend/rp/tests/test_eval_cli.py`

### 7. Wrong vs Correct
#### Wrong
- Frontend writes keys somewhere ad hoc and expects the backend process to discover them later.
- API echoes the secret key back to the frontend.
- Enable/disable updates require a backend restart to take effect.

#### Correct
- Backend owns persistence and computes the effective runtime config.
- API returns a safe status summary that is sufficient for settings UI and WebUI launch behavior.
- Runtime updates hot-reload the Langfuse singleton so monitoring state matches the latest saved config.
