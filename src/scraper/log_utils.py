import sys
from datetime import datetime
from threading import Lock
from typing import List

from rich.console import Console

# Create console for logging
console = Console()
log_lock = Lock()
log_messages: List[str] = []

# Global log level
LOG_LEVEL = "info"

# Log level hierarchy (in order of increasing verbosity)
LOG_LEVELS = {
    "error": 0,  # Only critical errors that prevent execution
    "warning": 1,  # Warnings about potential issues
    "success": 2,  # Successful operations
    "info": 3,  # General information about execution
    "debug": 4,  # Detailed debugging information
}


def set_log_level(level: str) -> str:
    """
    Set the global log level.

    Log levels:
    - error: Only critical errors that prevent execution
    - warning: Warnings about potential issues
    - success: Successful operations
    - info: General information about execution (default)
    - debug: Detailed debugging information

    Args:
        level (str): Log level (error, warning, success, info, debug)

    Returns:
        str: Status message about the log level change
    """
    global LOG_LEVEL

    status_message = ""
    if level in LOG_LEVELS:
        LOG_LEVEL = level
        status_message = f"Log level set to: {level}"
    else:
        LOG_LEVEL = "info"
        status_message = f"Invalid log level: {level}. Using 'info'."

    return status_message


def get_log_level() -> str:
    """
    Get the current global log level.

    Returns:
        str: Current log level
    """
    return LOG_LEVEL


def log_message(message: str, level: str = "info") -> None:
    """
    Add a log message to the display if its level is at or above the global log level.

    Args:
        message (str): Message to log
        level (str): Log level (error, warning, success, info, debug)
    """
    global LOG_LEVEL

    # Check if this message should be logged based on the current log level
    if level not in LOG_LEVELS:
        level = "info"

    if LOG_LEVELS[level] > LOG_LEVELS[LOG_LEVEL]:
        return  # Skip messages that are too verbose for the current log level

    timestamp = datetime.now().strftime("%H:%M:%S")
    prefixes = {
        "error": "[red][ERROR][/]",
        "warning": "[yellow][WARN][/]",
        "success": "[green][SUCCESS][/]",
        "info": "[blue][INFO][/]",
        "debug": "[dim cyan][DEBUG][/]",
    }
    prefix = prefixes.get(level, prefixes["info"])

    with log_lock:
        log_messages.append(f"[dim]{timestamp}[/] {prefix} {message}")
        log_messages[:] = log_messages[-30:]
