"""BI1-T110 — Zoho CRM V8 inspection and setup utility.

Read-only inspection of the `AI_Recommendations` module plus an idempotent setup
command for the execution metadata the approved-action executor depends on.

Authentication comes exclusively from environment variables. No credential is ever
written to stdout, to a file, or into an error message.

Required environment
--------------------
  ZOHO_CRM_CLIENT_ID        OAuth client id
  ZOHO_CRM_CLIENT_SECRET    OAuth client secret
  ZOHO_CRM_REFRESH_TOKEN    OAuth refresh token
  ZOHO_CRM_DC               Data centre: us | eu | in | au | jp | ca | sa  (default: us)

Optional overrides (set both, or neither):
  ZOHO_CRM_API_BASE_URL     e.g. https://www.zohoapis.com
  ZOHO_CRM_ACCOUNTS_BASE_URL e.g. https://accounts.zoho.com

Required OAuth scopes
---------------------
  ZohoCRM.settings.modules.READ
  ZohoCRM.settings.fields.READ
  ZohoCRM.settings.layouts.READ
  ZohoCRM.settings.fields.CREATE   (setup command only)
  ZohoCRM.settings.fields.UPDATE   (setup command only)

Usage
-----
  python3 scripts/zoho_crm_admin.py inspect-module
  python3 scripts/zoho_crm_admin.py inspect-fields
  python3 scripts/zoho_crm_admin.py inspect-layouts
  python3 scripts/zoho_crm_admin.py inspect-blueprint
  python3 scripts/zoho_crm_admin.py inspect-execution-fields
  python3 scripts/zoho_crm_admin.py setup-execution-metadata --dry-run
  python3 scripts/zoho_crm_admin.py setup-execution-metadata --apply

`--dry-run` is the default for every mutating command; `--apply` must be explicit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MODULE_API_NAME = "AI_Recommendations"

DC_API_BASE = {
    "us": "https://www.zohoapis.com",
    "eu": "https://www.zohoapis.eu",
    "in": "https://www.zohoapis.in",
    "au": "https://www.zohoapis.com.au",
    "jp": "https://www.zohoapis.jp",
    "ca": "https://www.zohoapiscloud.ca",
    "sa": "https://www.zohoapis.sa",
}

DC_ACCOUNTS_BASE = {
    "us": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "in": "https://accounts.zoho.in",
    "au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
    "ca": "https://accountscloud.ca",
    "sa": "https://accounts.zoho.sa",
}

REQUIRED_EXECUTION_FIELDS: list[dict[str, Any]] = [
    {
        "api_name": "Execution_Status",
        "field_label": "Execution_Status",
        "data_type": "picklist",
        "pick_list_values": [
            {"display_value": v, "actual_value": v}
            for v in ("Not Started", "In Progress", "Executed", "Failed", "Blocked")
        ],
    },
    {
        "api_name": "Execution_Key",
        "field_label": "Execution_Key",
        "data_type": "text",
        "length": 255,
        "unique": {"case_sensitive": False},
    },
    {"api_name": "Executed_Task_ID", "field_label": "Executed_Task_ID", "data_type": "text", "length": 255},
    {"api_name": "Execution_Started_At", "field_label": "Execution_Started_At", "data_type": "datetime"},
    {"api_name": "Executed_At", "field_label": "Executed_At", "data_type": "datetime"},
    {"api_name": "Execution_Error", "field_label": "Execution_Error", "data_type": "textarea"},
    {"api_name": "Execution_Attempts", "field_label": "Execution_Attempts", "data_type": "integer"},
]


class ConfigError(Exception):
    """Raised when required configuration is absent or contradictory."""


class ApiError(Exception):
    """Raised on a non-2xx Zoho API response. Never carries credential material."""




def resolve_base_urls(env: dict[str, str]) -> tuple[str, str]:
    """Return (api_base, accounts_base) from explicit overrides or the DC code."""
    api_override = env.get("ZOHO_CRM_API_BASE_URL", "").strip()
    accounts_override = env.get("ZOHO_CRM_ACCOUNTS_BASE_URL", "").strip()
    if api_override or accounts_override:
        if not (api_override and accounts_override):
            raise ConfigError(
                "Set both ZOHO_CRM_API_BASE_URL and ZOHO_CRM_ACCOUNTS_BASE_URL, or neither."
            )
        return api_override.rstrip("/"), accounts_override.rstrip("/")

    dc = env.get("ZOHO_CRM_DC", "us").strip().lower() or "us"
    if dc not in DC_API_BASE:
        raise ConfigError(
            f"Unknown ZOHO_CRM_DC {dc!r}. Expected one of: {', '.join(sorted(DC_API_BASE))}."
        )
    return DC_API_BASE[dc], DC_ACCOUNTS_BASE[dc]


def require_credentials(env: dict[str, str]) -> dict[str, str]:
    """Fetch OAuth credentials from the environment.

    Raises naming only the *missing variable names* — never a value.
    """
    names = ("ZOHO_CRM_CLIENT_ID", "ZOHO_CRM_CLIENT_SECRET", "ZOHO_CRM_REFRESH_TOKEN")
    missing = [n for n in names if not env.get(n, "").strip()]
    if missing:
        raise ConfigError("Missing required environment variables: " + ", ".join(missing))
    return {n: env[n].strip() for n in names}




def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:500]}
        return exc.code, parsed


class ZohoCrmClient:
    """Minimal Zoho CRM V8 client. Holds the access token only in memory."""

    def __init__(self, api_base: str, accounts_base: str, credentials: dict[str, str]) -> None:
        self.api_base = api_base
        self.accounts_base = accounts_base
        self._credentials = credentials
        self._access_token: str | None = None

    def _refresh_access_token(self) -> str:
        payload = urllib.parse.urlencode(
            {
                "refresh_token": self._credentials["ZOHO_CRM_REFRESH_TOKEN"],
                "client_id": self._credentials["ZOHO_CRM_CLIENT_ID"],
                "client_secret": self._credentials["ZOHO_CRM_CLIENT_SECRET"],
                "grant_type": "refresh_token",
            }
        ).encode()
        status, body = _http_json(
            f"{self.accounts_base}/oauth/v2/token",
            method="POST",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = body.get("access_token")
        if status != 200 or not token:
            raise ApiError(f"Token refresh failed with HTTP {status} ({body.get('error', 'no error field')}).")
        return token

    def _token(self) -> str:
        if self._access_token is None:
            self._access_token = self._refresh_access_token()
        return self._access_token

    def request(self, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_base}/crm/v8/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self._token()}",
            "Content-Type": "application/json",
        }
        data = json.dumps(payload).encode() if payload is not None else None
        status, body = _http_json(url, method=method, headers=headers, data=data)
        if status >= 400:
            raise ApiError(f"{method} /crm/v8/{path} failed with HTTP {status}: {json.dumps(body)[:800]}")
        return body




def summarize_fields(fields_body: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce the very large getFields response to the facts that matter here."""
    out = []
    for field in fields_body.get("fields", []):
        out.append(
            {
                "api_name": field.get("api_name"),
                "id": field.get("id"),
                "data_type": field.get("data_type"),
                "length": field.get("length"),
                "custom_field": field.get("custom_field"),
                "unique": bool(field.get("unique")),
                "system_mandatory": field.get("system_mandatory"),
                "picklist_values": [
                    v.get("actual_value") for v in (field.get("pick_list_values") or [])
                ],
            }
        )
    return sorted(out, key=lambda f: f["api_name"] or "")


def diff_execution_fields(existing: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Compare live fields against REQUIRED_EXECUTION_FIELDS.

    Returns present/missing names plus any field whose live type contradicts the
    contract — a mismatch is reported, never silently "fixed".
    """
    by_name = {f["api_name"]: f for f in existing}
    present, missing, mismatched = [], [], []
    for required in REQUIRED_EXECUTION_FIELDS:
        name = required["api_name"]
        live = by_name.get(name)
        if live is None:
            missing.append(name)
            continue
        present.append(name)
        if live.get("data_type") != required["data_type"]:
            mismatched.append(f"{name}: expected {required['data_type']}, live {live.get('data_type')}")
        if required.get("unique") and not live.get("unique"):
            mismatched.append(f"{name}: expected a unique constraint, live field is not unique")
    return {"present": present, "missing": missing, "mismatched": mismatched}




def _client(env: dict[str, str]) -> ZohoCrmClient:
    api_base, accounts_base = resolve_base_urls(env)
    return ZohoCrmClient(api_base, accounts_base, require_credentials(env))


def cmd_inspect_module(env: dict[str, str], _args: argparse.Namespace) -> int:
    body = _client(env).request(f"settings/modules/{MODULE_API_NAME}")
    modules = body.get("modules") or []
    print(json.dumps(
        [
            {
                "api_name": m.get("api_name"),
                "id": m.get("id"),
                "module_name": m.get("module_name"),
                "generated_type": m.get("generated_type"),
                "api_supported": m.get("api_supported"),
                "isBlueprintSupported": m.get("isBlueprintSupported"),
                "display_field": m.get("display_field"),
            }
            for m in modules
        ],
        indent=2,
    ))
    return 0


def cmd_inspect_fields(env: dict[str, str], _args: argparse.Namespace) -> int:
    body = _client(env).request(f"settings/fields?module={MODULE_API_NAME}")
    print(json.dumps(summarize_fields(body), indent=2))
    return 0


def cmd_inspect_layouts(env: dict[str, str], _args: argparse.Namespace) -> int:
    body = _client(env).request(f"settings/layouts?module={MODULE_API_NAME}")
    print(json.dumps(
        [{"id": lt.get("id"), "name": lt.get("name"), "status": lt.get("status")}
         for lt in (body.get("layouts") or [])],
        indent=2,
    ))
    return 0


def cmd_inspect_blueprint(env: dict[str, str], _args: argparse.Namespace) -> int:
    """Report whether an API-driven Blueprint transition exists for this module.

    Requirement 17: the executor may only move the Blueprint-controlled `Status`
    field if this proves an API-supported transition. Blueprint transitions are
    exposed per record, not per module, so a record id is needed.
    """
    client = _client(env)
    record_id = os.environ.get("ZOHO_CRM_SAMPLE_RECORD_ID", "").strip()
    if not record_id:
        print(
            "Set ZOHO_CRM_SAMPLE_RECORD_ID to an AI Recommendation record id. "
            "Blueprint transitions are exposed per record, not per module.",
            file=sys.stderr,
        )
        return 2
    body = client.request(f"{MODULE_API_NAME}/{record_id}/actions/blueprint")
    transitions = (body.get("blueprint") or [{}])[0].get("transitions", []) if body.get("blueprint") else []
    print(json.dumps(
        [{"id": t.get("id"), "name": t.get("name"), "type": t.get("type"),
          "criteria_matched": t.get("criteria_matched")} for t in transitions],
        indent=2,
    ))
    return 0


def cmd_inspect_execution_fields(env: dict[str, str], _args: argparse.Namespace) -> int:
    body = _client(env).request(f"settings/fields?module={MODULE_API_NAME}")
    summary = summarize_fields(body)
    print(json.dumps(diff_execution_fields(summary), indent=2))
    return 0


def cmd_setup_execution_metadata(env: dict[str, str], args: argparse.Namespace) -> int:
    """Idempotently create only the execution fields that are missing."""
    client = _client(env)
    summary = summarize_fields(client.request(f"settings/fields?module={MODULE_API_NAME}"))
    diff = diff_execution_fields(summary)

    if diff["mismatched"]:
        print("Refusing to proceed — live fields contradict the contract:", file=sys.stderr)
        for line in diff["mismatched"]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    if not diff["missing"]:
        print(json.dumps({"action": "noop", "reason": "all_execution_fields_present",
                          "present": diff["present"]}, indent=2))
        return 0

    to_create = [f for f in REQUIRED_EXECUTION_FIELDS if f["api_name"] in diff["missing"]]
    if not args.apply:
        print(json.dumps({"action": "dry-run", "would_create": [f["api_name"] for f in to_create],
                          "payload": {"fields": to_create}}, indent=2))
        return 0

    body = client.request(f"settings/fields?module={MODULE_API_NAME}", method="POST",
                          payload={"fields": to_create})
    print(json.dumps({"action": "applied", "created": [f["api_name"] for f in to_create],
                      "response": body}, indent=2))
    return 0


COMMANDS = {
    "inspect-module": cmd_inspect_module,
    "inspect-fields": cmd_inspect_fields,
    "inspect-layouts": cmd_inspect_layouts,
    "inspect-blueprint": cmd_inspect_blueprint,
    "inspect-execution-fields": cmd_inspect_execution_fields,
    "setup-execution-metadata": cmd_setup_execution_metadata,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        cmd = sub.add_parser(name)
        if name.startswith("setup-"):
            cmd.add_argument("--apply", action="store_true",
                             help="Actually write to Zoho. Omit for a dry run.")
            cmd.add_argument("--dry-run", action="store_true",
                             help="Explicit no-op flag; dry run is already the default.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](dict(os.environ), args)
    except (ConfigError, ApiError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
