"""Interactive OAuth redirect and callback capture for MCP servers.

Holds the default browser-based redirect handler and the local HTTP/stdin callback
capture used when no custom handler is supplied. Nothing here touches token storage
or the per-user OAuth contextvars.
"""

import asyncio
import contextlib
import logging
import os
import select
import sys
import webbrowser
from collections.abc import Callable, Coroutine
from html import escape
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


async def default_redirect_handler(auth_url: str) -> None:
    """Default handler for OAuth redirect - opens browser.

    Args:
        auth_url: Authorization URL to visit
    """
    print(f"\n{'=' * 80}")
    print("OAuth Authentication Required")
    print(f"{'=' * 80}")
    print(f"\nOpening browser for authentication: {auth_url}\n")
    print("If the browser doesn't open automatically, please visit the URL above.")
    print("The terminal will automatically capture the callback or you can paste it manually.")
    print(f"{'=' * 80}\n")

    try:
        webbrowser.open(auth_url)
    except Exception:
        logger.exception("Failed to open browser")


def _parse_callback_response(callback_url: str) -> tuple[str, str | None]:
    """Parse authorization code and state from a callback URL."""
    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if "error" in params:
        error = params["error"][0]
        error_description = params.get("error_description", ["Unknown error"])[0]
        raise ValueError(f"OAuth error: {error} - {error_description}")

    if "code" not in params:
        raise ValueError("No authorization code found in callback URL")

    code = params["code"][0]
    state = params.get("state", [None])[0]
    return code, state


async def _prompt_for_callback_url() -> tuple[str, str | None]:
    """Prompt the user to paste the callback URL."""
    print("\nAfter authorizing, you will be redirected to a callback URL.")
    print("Paste the full URL here if automatic capture does not complete.\n")

    loop = asyncio.get_event_loop()
    callback_url = await loop.run_in_executor(None, lambda: input("Callback URL: ").strip())
    return _parse_callback_response(callback_url)


def _can_poll_stdin_for_callback() -> bool:
    """Return True when stdin supports polling-based callback input."""
    stdin = sys.stdin
    if stdin is None or not hasattr(stdin, "isatty") or not stdin.isatty():
        return False
    if os.name == "nt":
        try:
            import msvcrt  # type: ignore[attr-defined]

            return callable(getattr(msvcrt, "kbhit", None)) and callable(getattr(msvcrt, "getwche", None))
        except ImportError:
            return False
    try:
        select.select([stdin], [], [], 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


async def _prompt_for_callback_url_polling(poll_interval: float = 0.5) -> tuple[str, str | None]:
    """Prompt for callback URL using poll-based stdin reads that cancel cleanly."""
    print("\nAfter authorizing, you will be redirected to a callback URL.")
    print("Paste the full URL here if automatic capture does not complete.\n")

    stdin = sys.stdin
    if stdin is None:
        raise EOFError("stdin is unavailable")

    loop = asyncio.get_event_loop()
    if os.name == "nt":
        try:
            import msvcrt  # type: ignore[attr-defined]
        except ImportError as exc:  # pragma: no cover - platform-specific fallback
            raise EOFError("stdin polling backend unavailable") from exc
        kbhit = getattr(msvcrt, "kbhit", None)
        getwche = getattr(msvcrt, "getwche", None)
        if not callable(kbhit) or not callable(getwche):
            raise EOFError("stdin polling backend unavailable")

        line_buffer = ""
        while True:
            while kbhit():
                ch = getwche()
                if ch in {"\r", "\n"}:
                    print("")
                    callback_url = line_buffer.strip()
                    line_buffer = ""
                    if callback_url == "":
                        break
                    return _parse_callback_response(callback_url)
                if ch == "\x08":
                    line_buffer = line_buffer[:-1]
                    continue
                line_buffer += ch
            await asyncio.sleep(poll_interval)

    while True:

        def _wait_for_input() -> bool:
            ready, _, _ = select.select([stdin], [], [], poll_interval)
            return bool(ready)

        try:
            has_input = await loop.run_in_executor(None, _wait_for_input)
        except (OSError, ValueError) as exc:
            raise EOFError("stdin does not support polling") from exc

        if not has_input:
            continue

        callback_url = stdin.readline()
        if callback_url == "":
            raise EOFError("stdin reached EOF")
        callback_url = callback_url.strip()
        if callback_url == "":
            continue
        return _parse_callback_response(callback_url)


def _can_use_local_callback_server(redirect_uri: str) -> bool:
    """Return True if we can bind a local HTTP server for the redirect URI."""
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http":
        return False

    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1"}


async def _listen_for_callback_once(redirect_uri: str, timeout: float = 300.0) -> tuple[str, str | None]:
    """Start a local HTTP server and capture the first callback request."""
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    path = parsed.path or "/auth/callback"
    loop = asyncio.get_event_loop()
    result: asyncio.Future[tuple[str, str | None]] = loop.create_future()

    async def _handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            writer.close()
            await writer.wait_closed()
            return

        request_line = data.split(b"\r\n", 1)[0].decode(errors="ignore")
        parts = request_line.split(" ")
        target = parts[1] if len(parts) >= 2 else ""
        target_parsed = urlparse(target)
        # Some browsers send absolute URLs, others only the path.
        request_path = target_parsed.path or target

        status_line = "HTTP/1.1 200 OK\r\n"
        body = (
            "<html><body>"
            "<h1>You may close this tab.</h1>"
            "<p>Return to Agency Swarm. The terminal captured your authorization code.</p>"
            "</body></html>"
        )

        try:
            if request_path != path:
                status_line = "HTTP/1.1 404 Not Found\r\n"
                body = "<html><body><h1>404 Not Found</h1></body></html>"
                writer.write(
                    f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            params = parse_qs(target_parsed.query)

            # Handle OAuth provider error responses (e.g., user denied authorization)
            if "error" in params:
                error = params["error"][0]
                error_description = params.get("error_description", ["Unknown error"])[0]
                status_line = "HTTP/1.1 400 Bad Request\r\n"
                body = (
                    f"<html><body><h1>OAuth Error</h1><p>{escape(error)}: {escape(error_description)}</p></body></html>"
                )
                body_bytes = body.encode()
                headers = f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body_bytes)}\r\n\r\n".encode()
                writer.write(headers + body_bytes)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                if not result.done():
                    result.set_exception(ValueError(f"OAuth error: {error} - {error_description}"))
                return

            if "code" not in params:
                status_line = "HTTP/1.1 400 Bad Request\r\n"
                body = "<html><body><h1>Missing code parameter.</h1></body></html>"
                writer.write(
                    f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode()
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            if not result.done():
                code = params["code"][0]
                state = params.get("state", [None])[0]
                result.set_result((code, state))

            writer.write(f"{status_line}Content-Type: text/html\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(_handle_connection, host=host, port=port)
    print(f"\nListening for OAuth callback at {redirect_uri}\n")

    try:
        return await asyncio.wait_for(result, timeout=timeout)
    finally:
        server.close()
        await server.wait_closed()


async def default_callback_handler(redirect_uri: str | None = None, timeout: float = 300.0) -> tuple[str, str | None]:
    """Default handler for OAuth callback.

    Tries to capture the callback automatically using a local HTTP server and falls
    back to a manual prompt when automatic capture is not possible.

    Returns:
        Tuple of (authorization_code, state)
    """
    redirect_target = redirect_uri or "http://localhost:8000/auth/callback"

    if _can_use_local_callback_server(redirect_target):
        listener_task = asyncio.create_task(_listen_for_callback_once(redirect_target, timeout=timeout))
        prompt_factory: Callable[[], Coroutine[object, object, tuple[str, str | None]]] | None = None
        if _can_poll_stdin_for_callback():
            prompt_factory = _prompt_for_callback_url_polling
        prompt_task: asyncio.Task[tuple[str, str | None]] | None = None
        if prompt_factory is not None:
            prompt_task = asyncio.create_task(prompt_factory())
        tasks: list[asyncio.Task[tuple[str, str | None]]] = [listener_task]
        if prompt_task is not None:
            tasks.append(prompt_task)
        try:
            if prompt_task is None:
                return await listener_task

            while True:
                done, _ = await asyncio.wait(set(tasks), return_when=asyncio.FIRST_COMPLETED)
                if prompt_task in done:
                    try:
                        return prompt_task.result()
                    except EOFError:
                        if listener_task in done:
                            return listener_task.result()
                        return await listener_task
                    except ValueError as exc:
                        print(f"Invalid callback URL: {exc}. Please try again.")
                        if listener_task in done:
                            return listener_task.result()
                        if prompt_factory is None:
                            return await listener_task
                        prompt_task = asyncio.create_task(prompt_factory())
                        tasks = [listener_task, prompt_task]
                        continue
                if listener_task in done:
                    return listener_task.result()
        except OSError as exc:
            logger.warning("Local callback server unavailable (%s); falling back to manual entry.", exc)
        except TimeoutError:
            logger.warning("Timed out waiting for local OAuth callback; falling back to manual entry.")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    try:
        return await _prompt_for_callback_url()
    except EOFError as exc:
        # Non-interactive environments (e.g. background workers) cannot
        # satisfy the fallback stdin prompt.
        raise RuntimeError(
            "OAuth callback input is unavailable in non-interactive mode. "
            "Use FastAPI OAuth handlers or provide a callback URL."
        ) from exc
