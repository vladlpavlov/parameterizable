import sys
import logging
import pytest
from mixinforge import OutputCapturer


def test_capture_stdout():
    with OutputCapturer() as capturer:
        print("Hello, stdout!")

    output = capturer.get_output()
    assert "Hello, stdout!" in output

def test_capture_stderr():
    with OutputCapturer() as capturer:
        print("Hello, stderr!", file=sys.stderr)

    output = capturer.get_output()
    assert "Hello, stderr!" in output

def test_capture_combined_output():
    with OutputCapturer() as capturer:
        print("First, stdout")
        print("Then, stderr", file=sys.stderr)

    output = capturer.get_output()
    assert "First, stdout" in output
    assert "Then, stderr" in output


def test_logging_debug_capture():
    logging.getLogger().setLevel(logging.DEBUG)
    with OutputCapturer() as capturer:
        logging.debug("Test DEBUG message")

    output = capturer.get_output()
    assert "Test DEBUG message" in output

def test_logging_info_capture():
    logging.getLogger().setLevel(logging.INFO)
    with OutputCapturer() as capturer:
        logging.info("Test INFO message")

    output = capturer.get_output()
    assert "Test INFO message" in output

def test_logging_warning_capture():
    logging.getLogger().setLevel(logging.WARNING)
    with OutputCapturer() as capturer:
        logging.warning("Test WARNING message")

    output = capturer.get_output()
    assert "Test WARNING message" in output

def test_logging_error_capture():
    logging.getLogger().setLevel(logging.ERROR)

    with OutputCapturer() as capturer:
        logging.error("Test ERROR message")

    output = capturer.get_output()
    assert "Test ERROR message" in output

def test_logging_critical_capture():
    logging.getLogger().setLevel(logging.CRITICAL)

    with OutputCapturer() as capturer:
        logging.critical("Test CRITICAL message")

    output = capturer.get_output()
    assert "Test CRITICAL message" in output


def test_exception_is_reraised_and_traceback_captured():
    """Verify exceptions inside context are re-raised and traceback is captured."""
    capturer = OutputCapturer()

    with pytest.raises(ValueError, match="test error"):
        with capturer:
            print("Before exception")
            raise ValueError("test error")

    output = capturer.get_output()
    assert "Before exception" in output
    assert "ValueError" in output
    assert "test error" in output
    assert "Traceback" in output


def test_streams_restored_after_exception():
    """Verify stdout/stderr are restored even when exception occurs."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    capturer = OutputCapturer()

    with pytest.raises(RuntimeError):
        with capturer:
            raise RuntimeError("restore test")

    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr


def test_logging_handlers_restored_after_exception():
    """Verify logging handlers are restored even when exception occurs."""
    original_handlers = logging.root.handlers[:]

    capturer = OutputCapturer()

    with pytest.raises(KeyError):
        with capturer:
            raise KeyError("handler restore test")

    assert logging.root.handlers == original_handlers


def test_flush_stdout_explicitly():
    """Verify explicit flush on stdout tee stream works correctly."""
    with OutputCapturer() as capturer:
        sys.stdout.write("Buffered output")
        sys.stdout.flush()

    output = capturer.get_output()
    assert "Buffered output" in output


def test_flush_stderr_explicitly():
    """Verify explicit flush on stderr tee stream works correctly."""
    with OutputCapturer() as capturer:
        sys.stderr.write("Buffered stderr")
        sys.stderr.flush()

    output = capturer.get_output()
    assert "Buffered stderr" in output


def test_exception_traceback_contains_line_info():
    """Verify captured traceback contains file and line information."""
    capturer = OutputCapturer()

    with pytest.raises(TypeError):
        with capturer:
            raise TypeError("detailed error")

    output = capturer.get_output()
    assert "test_output_capturer.py" in output
    assert "line" in output.lower()


def test_normal_exit_no_traceback():
    """Verify no traceback is printed when context exits normally."""
    with OutputCapturer() as capturer:
        print("Normal operation")

    output = capturer.get_output()
    assert "Traceback" not in output
    assert "Normal operation" in output


def test_output_captured_before_exception():
    """Verify all output before exception is captured."""
    capturer = OutputCapturer()

    with pytest.raises(Exception):
        with capturer:
            print("Line 1")
            print("Line 2", file=sys.stderr)
            logging.getLogger().setLevel(logging.WARNING)
            logging.warning("Log message")
            raise Exception("after output")

    output = capturer.get_output()
    assert "Line 1" in output
    assert "Line 2" in output
    assert "Log message" in output


def test_repr_shows_captured_chars():
    """Verify __repr__ shows the number of captured characters."""
    capturer = OutputCapturer()
    assert "OutputCapturer" in repr(capturer)

    text_to_print = "Hello"

    with capturer:
        print(text_to_print)

    assert "OutputCapturer" in repr(capturer)


# ============================================================================
# Nested context tests
# ============================================================================

def test_nested_capturers_both_capture_output():
    """Verify that when capturers are nested, both see the appropriate output."""
    with OutputCapturer() as outer:
        print("outer only")
        with OutputCapturer() as inner:
            print("both see this")
        print("outer only again")

    outer_output = outer.get_output()
    inner_output = inner.get_output()

    assert "outer only" in outer_output
    assert "both see this" in outer_output
    assert "outer only again" in outer_output
    assert "both see this" in inner_output
    assert "outer only" not in inner_output


def test_nested_capturers_restore_correctly():
    """Verify streams are properly restored after nested contexts."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    original_handlers = logging.root.handlers[:]

    with OutputCapturer() as outer:
        with OutputCapturer() as inner:
            print("nested")

    assert "nested" in outer.get_output()
    assert "nested" in inner.get_output()
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr
    assert logging.root.handlers == original_handlers


def test_capturer_created_before_entering_another():
    """Verify capturers work correctly when created before entering contexts."""
    outer = OutputCapturer()
    inner = OutputCapturer()

    with outer:
        print("outer sees this")
        with inner:
            print("both should see this")

    assert "outer sees this" in outer.get_output()
    assert "both should see this" in outer.get_output()
    assert "both should see this" in inner.get_output()


def test_nested_capturer_exception_restores_all():
    """Verify exception in inner context properly restores outer's state."""
    original_stdout = sys.stdout

    with pytest.raises(ValueError):
        with OutputCapturer() as outer:
            print("Hello Outer!")
            with OutputCapturer() as inner:
                print("Hello Inner!")
                raise ValueError("inner error")

    assert "Hello Outer!" in outer.get_output()
    assert "Hello Inner!" in inner.get_output()
    assert sys.stdout is original_stdout


def test_nested_logging_both_capture():
    """Verify logging works correctly with nested capturers."""
    logging.getLogger().setLevel(logging.INFO)

    with OutputCapturer() as outer:
        logging.info("outer log")
        with OutputCapturer() as inner:
            logging.info("inner log")

    assert "outer log" in outer.get_output()
    assert "inner log" in outer.get_output()
    assert "inner log" in inner.get_output()
    assert "outer log" not in inner.get_output()