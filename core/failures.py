"""Sanitised failure reporting for pipeline runs.

Two jobs live here because they meet at the same line of code -- the moment a pipeline
turns an exception into a printed line.

**1. Redaction (golden rule 1).** `requests.HTTPError`'s default string embeds the full
request URL, so any client authenticating via a *query parameter* leaks its key into
every log line that prints the raw exception. This is not theoretical:
`pipelines/entsoe/client.py` documents it happening for real on 2026-08-30, and three
more clients (EIA, Guardian, NewsAPI) send their key the same way. Converting the
exception at the client is the primary fix -- `raise_sanitised` below is that conversion.
`redact` is the backstop for everything that isn't wrapped, including third-party
libraries this project doesn't control.

**2. Partial-failure propagation.** Every pipeline here deliberately continues when one
of its items fails: one bad contract must not cost the other twenty. But a pipeline that
swallows twenty failures and then returns normally tells `infra/run_scheduled.py` it
succeeded -- which prints "OK" and exits 0, so Windows Task Scheduler's own "Last Run
Result" column shows green for a run that ingested nothing at all. `FailureLog` keeps the
resilience and restores the signal: record every failure, finish all the work that can
still be done, then raise once at the end so the exit status tells the truth.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import NoReturn, ParamSpec, TypeVar

REDACTED = "[REDACTED]"

# Query parameters that carry a credential in this project's own clients (EIA's
# `api_key`, Guardian's `api-key`, NewsAPI's `apiKey`, ENTSO-E's `securityToken`), plus
# the obvious neighbours. Longer alternatives first: the regex alternation is ordered, and
# a bare `key=` would otherwise match the tail of `api_key=`.
_SECRET_PARAM_RE = re.compile(
    r"(?i)\b(securitytoken|api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|key)"
    r"=([^&\s\"'<>]+)"
)

# A connection URI carries its credential in the userinfo (`scheme://user:password@host`),
# which `_SECRET_PARAM_RE` above -- a query-parameter rule -- never sees. Spec 32's
# Supabase publish connects with exactly such a URI, and psycopg echoes the whole
# connection string back in several of its own error messages (confirmed live
# 2026-09-09: `missing "=" after "postgres-bogus://user:PASSWORD@host/db"`). Since
# `infra/run_scheduled.py` prints `describe_exception` for every pipeline failure, an
# unredacted database-owner password was reaching the logs. Only the password is
# replaced: the scheme, user and host stay legible, because a redactor that mangles the
# host turns a real diagnostic into an unreadable one.
_URI_USERINFO_RE = re.compile(r"(?P<scheme>[a-z][a-z0-9+.\-]*://[^:/?#@\s]+:)[^@/?#\s]+@")

# Only fields whose *name* marks them as a credential are matched against message text.
# Matching on every settings value would be actively harmful -- `ibkr_host` is
# "127.0.0.1" and `ibkr_client_id` is 1, and redacting those would mangle unrelated
# messages beyond recognition. `_db_url` is here rather than a bare `_url` for the same
# reason: `supabase_db_url` embeds a password, an ordinary `*_url` setting would not.
_SECRET_FIELD_SUFFIXES = ("_key", "_token", "_secret", "_db_url", "_password")
# Below this length a "secret" is far more likely to be a placeholder ("ci-placeholder"
# is 14, a real key is 32+) than something worth redacting at the cost of false hits.
_MIN_SECRET_LENGTH = 8


def _uri_password(value: str) -> str | None:
    """The password out of a `scheme://user:password@host` string, if there is one.

    Deliberately regex-based rather than `urllib.parse`: a real Supabase password can
    contain characters (`%`, `#`) that make the value an invalid URI, and `urlsplit`
    raises or mis-parses on exactly the inputs this most needs to handle.
    """
    match = _URI_USERINFO_RE.search(value)
    if match is None:
        return None
    return value[match.end(1) : match.end() - 1] or None


def _known_secrets() -> list[str]:
    """Real credential values from `core.settings`, longest first so that a key which
    happens to contain another as a prefix is still fully replaced.

    Imported lazily and defensively: this module is the last line of defence while
    *reporting* an error, and a redactor that raises on its own import would replace a
    real diagnostic with an unrelated crash. When settings can't load, regex redaction
    still applies."""
    try:
        from core.settings import settings
    except Exception:
        return []

    values = []
    for name, value in settings.model_dump().items():
        if not name.endswith(_SECRET_FIELD_SUFFIXES):
            continue
        if isinstance(value, str) and len(value) >= _MIN_SECRET_LENGTH:
            values.append(value)
            # The whole URI is not enough on its own: psycopg reports *just the password
            # fragment* when it cannot percent-decode it (`invalid percent-encoded
            # token: "Secret%ZZpass"`), with no scheme or host for `_URI_USERINFO_RE` to
            # anchor on and nothing matching the full string. Confirmed live 2026-09-09.
            password = _uri_password(value)
            if password and len(password) >= _MIN_SECRET_LENGTH:
                values.append(password)
    return sorted(values, key=len, reverse=True)


def redact(text: str) -> str:
    """`text` with any credential removed. Three passes, all needed: exact replacement of
    known settings values catches a key wherever it appears (query string, echoed header,
    JSON body), the URI-userinfo regex catches a password embedded in a connection string
    (`postgresql://user:password@host` -- psycopg echoes these back in its own errors),
    and the query-parameter regex catches keys this process doesn't hold -- a URL built by
    a third-party library, or a value from a source outside settings."""
    for secret in _known_secrets():
        text = text.replace(secret, REDACTED)
    text = _URI_USERINFO_RE.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", text)
    return _SECRET_PARAM_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


def describe_exception(exc: BaseException) -> str:
    """`"TypeName: message"` with the message redacted -- the one format every failure
    line in this project uses, so there is exactly one place redaction has to happen."""
    return f"{type(exc).__name__}: {redact(str(exc))}"


def raise_sanitised(exc: BaseException) -> NoReturn:
    """Re-raise `exc` as a RuntimeError carrying a redacted message.

    `from None` is load-bearing, not stylistic: without it Python prints "During handling
    of the above exception, another exception occurred" followed by the *original*
    unredacted message, and the leak this function exists to prevent happens anyway."""
    raise RuntimeError(describe_exception(exc)) from None


class PartialFailureError(RuntimeError):
    """Raised at the end of a pipeline that finished with some of its items failed. Not
    raised at the point of failure -- the whole design is that the remaining items still
    run."""


class FailureLog:
    """Per-item failures for one pipeline run: report each as it happens, finish the run,
    then fail once at the end."""

    def __init__(self, pipeline: str) -> None:
        self.pipeline = pipeline
        self.failed: list[str] = []

    def record(self, item: str, exc: BaseException) -> None:
        """Print the failure in this project's established `FAILED (...)` format, with the
        exception message redacted, and remember the item for `raise_if_any`."""
        self.failed.append(item)
        print(f"{item}: FAILED ({describe_exception(exc)})", flush=True)

    def raise_if_any(self) -> None:
        if self.failed:
            raise PartialFailureError(
                f"{self.pipeline}: {len(self.failed)} item(s) failed: {self.failed}"
            )


_active_log: ContextVar[FailureLog | None] = ContextVar("_active_log", default=None)


@contextmanager
def failure_scope(pipeline: str) -> Iterator[FailureLog]:
    """Wrap a pipeline's `main()` body. Failures recorded anywhere inside -- including
    from the helper functions `main()` calls -- are collected, and one PartialFailureError
    is raised on the way out if there were any.

        def main() -> None:
            with failure_scope("futures.pull_daily"):
                for root in ROOTS:
                    try:
                        total += pull_root(client, root, ...)
                    except Exception as exc:
                        record_failure(root, exc)
                print(f"pull_daily: {total} rows", flush=True)

    A scope rather than a value threaded through every signature: the failure sites in
    this project sit several helper calls below `main()` (pipelines/macro/pull_macro.py
    and pipelines/news/pull_news.py both swallow inside frame-returning helpers), and
    giving each of those an extra parameter would change far more code than the fix needs.

    A body that raises on its own propagates untouched -- an outright crash is already a
    failure the orchestrator sees, and masking it with the partial-failure summary would
    lose the real cause."""
    log = FailureLog(pipeline)
    token = _active_log.set(log)
    try:
        yield log
    finally:
        _active_log.reset(token)
    log.raise_if_any()


def record_failure(item: str, exc: BaseException) -> None:
    """Record against the enclosing `failure_scope`. Outside one -- a helper called from a
    notebook, a one-off backfill script -- this still prints the sanitised line and simply
    has nowhere to report to, which is the old behaviour and no worse than it."""
    log = _active_log.get()
    if log is None:
        print(f"{item}: FAILED ({describe_exception(exc)})", flush=True)
        return
    log.record(item, exc)


_P = ParamSpec("_P")
_R = TypeVar("_R")


def fails_loudly(pipeline: str) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Decorator form of `failure_scope`, for a pipeline's `main()`.

        @fails_loudly("futures.pull_daily")
        def main() -> None:
            ...

    Preferred over wrapping the body in a `with` block purely because it leaves the
    body's indentation alone, which keeps the diff on 18 existing pipelines readable.
    Decorating `main` also covers the thin re-export entrypoints
    (`pipelines/news/pull_daily.py` is `from pipelines.news.pull_news import main`) --
    they re-export the decorated function object itself, so they need no change."""

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with failure_scope(pipeline):
                return fn(*args, **kwargs)

        return wrapper

    return decorator
