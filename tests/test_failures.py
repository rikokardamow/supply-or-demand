from __future__ import annotations

import re

import pytest
import requests
from core.failures import (
    REDACTED,
    FailureLog,
    PartialFailureError,
    describe_exception,
    failure_scope,
    raise_sanitised,
    record_failure,
    redact,
)


def _http_error(url: str, status: int = 403) -> requests.HTTPError:
    """A real requests.HTTPError built the way raise_for_status builds one -- its message
    is what actually leaked, so the test must not hand-write it."""
    response = requests.Response()
    response.status_code = status
    response.reason = "Forbidden"
    response.url = url
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        return exc
    raise AssertionError("expected raise_for_status to raise")


def test_redact_strips_a_key_from_a_query_string() -> None:
    text = "for url: https://api.eia.gov/v2/x/data/?api_key=abc123def456&frequency=weekly"

    result = redact(text)

    assert "abc123def456" not in result
    assert f"api_key={REDACTED}" in result
    assert "frequency=weekly" in result  # non-secret params survive untouched


@pytest.mark.parametrize(
    "param",
    ["api_key", "api-key", "apiKey", "APIKEY", "securityToken", "token", "key"],
)
def test_redact_covers_every_spelling_this_project_sends(param: str) -> None:
    result = redact(f"https://example.com/x?{param}=s3cr3tvalue&page=2")

    assert "s3cr3tvalue" not in result
    assert "page=2" in result


def test_redact_leaves_a_message_with_no_credential_alone() -> None:
    text = "ConnectionError: HTTPSConnectionPool(host='api.eia.gov', port=443): timed out"

    assert redact(text) == text


def test_redact_replaces_a_known_settings_value_anywhere_in_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A key echoed in a JSON body or a header dump has no `key=` for the regex to find --
    # exact replacement of the real value is what catches it.
    monkeypatch.setattr(
        "core.failures._known_secrets", lambda: ["supersecretkeyvalue1234"]
    )

    result = redact('{"error": "invalid credential supersecretkeyvalue1234"}')

    assert "supersecretkeyvalue1234" not in result
    assert REDACTED in result


def test_describe_exception_redacts_a_real_http_error() -> None:
    exc = _http_error("https://api.eia.gov/v2/petroleum/data/?api_key=REALKEY123456&x=1")

    described = describe_exception(exc)

    assert "REALKEY123456" not in described
    assert described.startswith("HTTPError: 403 Client Error")


def test_raise_sanitised_drops_the_original_message_from_the_exception_chain() -> None:
    exc = _http_error("https://api.eia.gov/v2/x/?api_key=REALKEY123456")

    with pytest.raises(RuntimeError) as caught:
        raise_sanitised(exc)

    assert "REALKEY123456" not in str(caught.value)
    # Without `from None`, Python prints the original (unredacted) exception as context
    # and the leak happens anyway.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_failure_log_raises_once_at_the_end_listing_every_failed_item(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failures = FailureLog("futures.pull_daily")

    failures.record("cl", ValueError("bad contract"))
    failures.record("ng", ValueError("bad contract"))

    printed = capsys.readouterr().out
    assert "cl: FAILED (ValueError: bad contract)" in printed
    assert "ng: FAILED (ValueError: bad contract)" in printed

    with pytest.raises(PartialFailureError, match=r"2 item\(s\) failed"):
        failures.raise_if_any()


def test_failure_log_is_silent_when_every_item_succeeded() -> None:
    FailureLog("futures.pull_daily").raise_if_any()  # must not raise


def test_failure_log_redacts_the_recorded_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failures = FailureLog("eia.pull_wpsr")

    failures.record("wpsr", _http_error("https://api.eia.gov/v2/x/?api_key=REALKEY123456"))

    assert "REALKEY123456" not in capsys.readouterr().out


def test_failure_scope_raises_once_for_failures_recorded_in_a_helper() -> None:
    """The point of the scope: pull_macro.py and pull_news.py both swallow inside
    frame-returning helpers several calls below main(), with no log to hand them."""

    def _helper_that_swallows() -> str:
        try:
            raise ValueError("fred is down")
        except ValueError as exc:
            record_failure("fred dgs10", exc)
        return "partial result"

    with (
        pytest.raises(PartialFailureError, match=re.escape("macro.pull_weekly")),
        failure_scope("macro.pull_weekly"),
    ):
        assert _helper_that_swallows() == "partial result"


def test_failure_scope_is_quiet_when_nothing_failed() -> None:
    with failure_scope("futures.pull_daily") as log:
        assert log.failed == []


def test_failure_scope_lets_an_outright_crash_propagate_unchanged() -> None:
    # A body that raises is already a failure the orchestrator sees; replacing it with the
    # partial-failure summary would throw away the real cause.
    with pytest.raises(ZeroDivisionError), failure_scope("futures.pull_daily"):
        record_failure("cl", ValueError("also this"))
        raise ZeroDivisionError


def test_failure_scope_does_not_leak_into_a_later_run() -> None:
    with pytest.raises(PartialFailureError), failure_scope("first"):
        record_failure("a", ValueError("x"))

    with failure_scope("second") as log:  # must start clean, not inherit "a"
        assert log.failed == []


def test_record_failure_outside_a_scope_still_prints_sanitised(
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_failure("wpsr", _http_error("https://api.eia.gov/v2/x/?api_key=REALKEY123456"))

    printed = capsys.readouterr().out
    assert "wpsr: FAILED" in printed
    assert "REALKEY123456" not in printed


def test_redact_strips_a_password_from_a_database_uri() -> None:
    # Spec 32's Supabase publish connects with a URI carrying the database-owner
    # password in its userinfo (`://user:pass@host`). Confirmed live 2026-09-09 that
    # psycopg echoes the whole connection string back in several ProgrammingError
    # messages, and that neither existing pass caught it: `supabase_db_url` ends in
    # `_url`, not one of `_SECRET_FIELD_SUFFIXES`, and `_SECRET_PARAM_RE` only matches
    # `key=value` query parameters, never userinfo. `run_scheduled.py` prints
    # `describe_exception` for every pipeline failure, so this reached the logs.
    text = 'missing "=" after "postgres-bogus://postgres.abc:SuperSecretPw123@host/db"'

    cleaned = redact(text)

    assert "SuperSecretPw123" not in cleaned
    assert REDACTED in cleaned


def test_redact_strips_a_password_from_a_well_formed_postgres_uri() -> None:
    cleaned = redact("postgresql://postgres.ref:hunter2hunter2@aws-0.pooler.example.com:6543/postgres")

    assert "hunter2hunter2" not in cleaned
    # The non-secret parts stay legible -- a redactor that mangles the host makes the
    # diagnostic useless.
    assert "aws-0.pooler.example.com" in cleaned


def test_redact_leaves_a_uri_with_no_password_alone() -> None:
    assert redact("https://agsi.gie.eu/api?from=2026-01-01") == "https://agsi.gie.eu/api?from=2026-01-01"


def test_known_secrets_also_yields_the_password_inside_a_connection_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Redacting only the whole URI value is not enough: psycopg reports *just the
    # password fragment* when it fails to percent-decode it, e.g. `invalid
    # percent-encoded token: "Secret%ZZpass"` -- no scheme, no host, nothing for the
    # userinfo regex to anchor on and nothing matching the full URI string. Confirmed
    # live 2026-09-09 against the installed psycopg. The password component therefore
    # has to be a known secret in its own right.
    from core.failures import _known_secrets

    class _FakeSettings:
        @staticmethod
        def model_dump() -> dict[str, str]:
            return {
                "supabase_db_url": "postgresql://postgres.ref:Secret%ZZpass@host:6543/postgres",
                "ibkr_host": "127.0.0.1",
            }

    monkeypatch.setitem(__import__("sys").modules, "core.settings", type(
        "M", (), {"settings": _FakeSettings()}
    ))

    secrets = _known_secrets()

    assert "Secret%ZZpass" in secrets, "the password component must be redactable on its own"
    assert "127.0.0.1" not in secrets, "non-credential settings must never be redacted"
