"""
Utility decorators for Erni-Foto system.
"""

import functools
import time
from collections.abc import Callable
from typing import Any

from .exceptions import ErniFotoError
from .logging import get_logger


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exponential_backoff: bool = True,
    exceptions: type[Exception] | tuple = Exception,
    logger_name: str | None = None,
) -> Callable:
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        exponential_backoff: Whether to use exponential backoff
        exceptions: Exception types to catch and retry
        logger_name: Logger name for logging retry attempts
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = get_logger(logger_name or f"{func.__module__}.{func.__name__}")

            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        logger.error(f"Function {func.__name__} failed after {max_attempts} attempts: {e}")
                        raise

                    logger.warning(
                        f"Function {func.__name__} failed on attempt {attempt + 1}/{max_attempts}: {e}. "
                        f"Retrying in {current_delay:.2f} seconds..."
                    )

                    time.sleep(current_delay)

                    if exponential_backoff:
                        current_delay *= 2

            # This should never be reached, but just in case
            raise last_exception

        return wrapper

    return decorator


def log_execution_time(logger_name: str | None = None) -> Callable:
    """
    Decorator to log function execution time.

    Args:
        logger_name: Logger name for logging execution time
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = get_logger(logger_name or f"{func.__module__}.{func.__name__}")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(f"Function {func.__name__} executed in {execution_time:.2f} seconds")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"Function {func.__name__} failed after {execution_time:.2f} seconds: {e}")
                raise

        return wrapper

    return decorator


def handle_errors(
    default_return: Any = None,
    exceptions: type[Exception] | tuple = Exception,
    logger_name: str | None = None,
    reraise: bool = True,
) -> Callable:
    """
    Decorator to handle and log exceptions.

    Args:
        default_return: Default value to return on exception
        exceptions: Exception types to catch
        logger_name: Logger name for logging errors
        reraise: Whether to reraise the exception after logging
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = get_logger(logger_name or f"{func.__module__}.{func.__name__}")

            try:
                return func(*args, **kwargs)
            except exceptions as e:
                logger.error(f"Error in function {func.__name__}: {e}", exc_info=True)

                if reraise:
                    raise

                return default_return

        return wrapper

    return decorator


def validate_config(config_fields: list) -> Callable:
    """
    Decorator to validate configuration fields before function execution.

    Args:
        config_fields: List of configuration field paths to validate
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Assume first argument is self with config attribute
            if args and hasattr(args[0], "config"):
                config = args[0].config

                for field_path in config_fields:
                    field_parts = field_path.split(".")
                    current = config

                    try:
                        for part in field_parts:
                            current = getattr(current, part)

                        if not current:
                            raise ErniFotoError(f"Configuration field {field_path} is empty or None")

                    except AttributeError as e:
                        raise ErniFotoError(f"Configuration field {field_path} not found") from e

            return func(*args, **kwargs)

        return wrapper

    return decorator


def rate_limit(calls_per_second: float) -> Callable:
    """
    Decorator to rate limit function calls.

    Args:
        calls_per_second: Maximum number of calls per second
    """
    min_interval = 1.0 / calls_per_second
    last_called = [0.0]

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed

            if left_to_wait > 0:
                time.sleep(left_to_wait)

            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret

        return wrapper

    return decorator


def cache_result(ttl_seconds: int = 300) -> Callable:
    """
    Decorator to cache function results with TTL.

    Args:
        ttl_seconds: Time to live for cached results in seconds
    """

    def decorator(func: Callable) -> Callable:
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Create cache key from arguments
            key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()

            # Check if we have a valid cached result
            if key in cache:
                result, timestamp = cache[key]
                if current_time - timestamp < ttl_seconds:
                    return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache[key] = (result, current_time)

            # Clean up expired entries
            expired_keys = [k for k, (_, timestamp) in cache.items() if current_time - timestamp >= ttl_seconds]
            for k in expired_keys:
                del cache[k]

            return result

        return wrapper

    return decorator
