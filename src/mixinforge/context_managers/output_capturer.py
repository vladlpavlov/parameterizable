"""Output capture utilities for function execution logging.

Provides OutputCapturer, a context manager that simultaneously captures and
displays stdout, stderr, and logging output. Uses a "tee" strategy where
output is duplicated: sent to both the original destination (for normal
display) and to an internal buffer (for storage in execution logs).

Design Rationale:
    Simple redirection (e.g., sys.stdout = StringIO()) would suppress output
    from the user's view. The tee approach preserves normal output behavior
    while also capturing it for later analysis, making it suitable for both
    interactive use and production logging.
"""

import sys
import io
import logging
import traceback
from contextlib import ExitStack


# TODO: see if we can use https://capturer.readthedocs.io/en/latest/index.html
# TODO: see if we can use similar functionality from pytest

class OutputCapturer:
    """Context manager that captures stdout, stderr, and logging output.

    Uses a dual-stream "tee" approach: output is sent to both the original
    streams (preserving normal display) and to an internal buffer (enabling
    capture). This ensures users see output in real-time while also storing
    it for later retrieval via get_output().

    Example:
        >>> with OutputCapturer() as capturer:
        ...     print("Hello")  # Prints normally AND is captured
        ...     logging.info("Test")  # Logged normally AND is captured
        >>> output = capturer.get_output()
        >>> assert "Hello" in output
        >>> assert "Test" in output
    """

    class _TeeStream:
        """Internal stream that duplicates output to two destinations.

        Duplicates all write() calls to both the original stream (for normal
        display) and a StringIO buffer (for capture). This enables simultaneous
        capture and display of stdout/stderr.

        Args:
            original: The original stream (stdout or stderr) to preserve.
            buffer: The StringIO buffer to capture output.
        """
        def __init__(self, original, buffer):
            self.original = original
            self.buffer = buffer

        def write(self, data):
            """Write data to both the original stream and the capture buffer.

            Args:
                data: The data to be written.
            """
            self.original.write(data)
            self.buffer.write(data)

        def flush(self):
            """Flush both streams to ensure all data is written."""
            self.original.flush()
            self.buffer.flush()

    class _CaptureHandler(logging.Handler):
        """Internal logging handler that captures and forwards log records.

        Captures logging output to a buffer while also forwarding records to
        the original handlers, preserving normal logging behavior.

        Args:
            buffer: The StringIO buffer to capture logging output.
            original_handlers: The original logging handlers to forward records to.
        """
        def __init__(self, buffer, original_handlers):
            super().__init__()
            self.buffer = buffer
            self.original_handlers = original_handlers

        def emit(self, record):
            """Emit a log record to both the capture buffer and original handlers.

            Args:
                record: The log record to be captured and forwarded.
            """
            msg = self.format(record)
            self.buffer.write(msg + '\n')
            for handler in self.original_handlers:
                handler.emit(record)

    def __init__(self):
        """Initialize the OutputCapturer.

        Creates the capture buffer. The actual stream redirection happens
        in __enter__ to support proper nesting of multiple OutputCapturer
        contexts.
        """
        self.captured_buffer = io.StringIO()
        self._stack = None

    def __repr__(self) -> str:
        """Return a string representation of the OutputCapturer.

        Returns:
            A string showing the current size of the captured output buffer.
        """
        captured_size = len(self.captured_buffer.getvalue())
        return f"OutputCapturer(captured_chars={captured_size})"

    def __enter__(self):
        """Start capturing stdout, stderr, and logging output.

        Stream redirection happens here (not in __init__) to properly support
        nested OutputCapturer contexts. Each capturer captures the current
        streams at entry time, which may already be another capturer's tee.

        Returns:
            The OutputCapturer instance for use as a context variable.
        """
        self._stack = ExitStack()

        # Capture current state at ENTRY time (may be another capturer's tee)
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_handlers = logging.root.handlers[:]

        # Create tees pointing to current streams
        tee_stdout = self._TeeStream(original_stdout, self.captured_buffer)
        tee_stderr = self._TeeStream(original_stderr, self.captured_buffer)
        capture_handler = self._CaptureHandler(
            self.captured_buffer, original_handlers)

        # Register cleanup callbacks (LIFO order - restored in reverse)
        self._stack.callback(setattr, sys, 'stdout', original_stdout)
        self._stack.callback(setattr, sys, 'stderr', original_stderr)
        self._stack.callback(setattr, logging.root, 'handlers', original_handlers)

        # Install our tee streams
        sys.stdout = tee_stdout
        sys.stderr = tee_stderr
        logging.root.handlers = [capture_handler]

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing and restore stdout, stderr, and logging to original state.

        If an exception occurred, prints the traceback to the captured output
        before restoring streams. Delegates cleanup to ExitStack which restores
        streams in LIFO order, ensuring proper unwinding of nested contexts.

        Args:
            exc_type: Exception class if an exception occurred, None otherwise.
            exc_val: Exception instance if an exception occurred, None otherwise.
            exc_tb: Traceback if an exception occurred, None otherwise.

        Returns:
            Whatever ExitStack.__exit__ returns (False by default, allowing
            exceptions to propagate).
        """
        if exc_type is not None:
            traceback.print_exc()
        return self._stack.__exit__(exc_type, exc_val, exc_tb)

    def get_output(self) -> str:
        """Retrieve all captured output as a single string.

        Returns:
            Combined stdout, stderr, and logging output captured during the
            context manager's lifetime.
        """
        return self.captured_buffer.getvalue()