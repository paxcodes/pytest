"""Helper functions for writing to terminals and files."""
import os
import shutil
import sys
from typing import Optional
from typing import Sequence
from typing import TextIO

from .wcwidth import wcswidth


# This code was initially copied from py 1.8.1, file _io/terminalwriter.py.


def get_terminal_width() -> int:
    width, _ = shutil.get_terminal_size(fallback=(80, 24))

    # The Windows get_terminal_size may be bogus, let's sanify a bit.
    if width < 40:
        width = 80

    return width


def should_do_markup(file: TextIO) -> bool:
    if os.environ.get("PY_COLORS") == "1":
        return True
    if os.environ.get("PY_COLORS") == "0":
        return False
    return (
        hasattr(file, "isatty")
        and file.isatty()
        and os.environ.get("TERM") != "dumb"
        and not (sys.platform.startswith("java") and os._name == "nt")
    )


class TerminalWriter:
    _esctable = dict(
        black=30,
        red=31,
        green=32,
        yellow=33,
        blue=34,
        purple=35,
        cyan=36,
        white=37,
        Black=40,
        Red=41,
        Green=42,
        Yellow=43,
        Blue=44,
        Purple=45,
        Cyan=46,
        White=47,
        bold=1,
        light=2,
        blink=5,
        invert=7,
    )

    def __init__(self, file: Optional[TextIO] = None) -> None:
        if file is None:
            file = sys.stdout
        if hasattr(file, "isatty") and file.isatty() and sys.platform == "win32":
            try:
                import colorama
            except ImportError:
                pass
            else:
                file = colorama.AnsiToWin32(file).stream
                assert file is not None
        self._file = file
        self.hasmarkup = should_do_markup(file)
        self._current_line = ""
        self._terminal_width = None  # type: Optional[int]

    @property
    def fullwidth(self) -> int:
        if self._terminal_width is not None:
            return self._terminal_width
        return get_terminal_width()

    @fullwidth.setter
    def fullwidth(self, value: int) -> None:
        self._terminal_width = value

    @property
    def width_of_current_line(self) -> int:
        """Return an estimate of the width so far in the current line."""
        return wcswidth(self._current_line)

    def markup(self, text: str, **markup: bool) -> str:
        for name in markup:
            if name not in self._esctable:
                raise ValueError("unknown markup: {!r}".format(name))
        if self.hasmarkup:
            esc = [self._esctable[name] for name, on in markup.items() if on]
            if esc:
                text = "".join("\x1b[%sm" % cod for cod in esc) + text + "\x1b[0m"
        return text

    def sep(
        self,
        sepchar: str,
        title: Optional[str] = None,
        fullwidth: Optional[int] = None,
        **markup: bool
    ) -> None:
        if fullwidth is None:
            fullwidth = self.fullwidth
        # the goal is to have the line be as long as possible
        # under the condition that len(line) <= fullwidth
        if sys.platform == "win32":
            # if we print in the last column on windows we are on a
            # new line but there is no way to verify/neutralize this
            # (we may not know the exact line width)
            # so let's be defensive to avoid empty lines in the output
            fullwidth -= 1
        if title is not None:
            # we want 2 + 2*len(fill) + len(title) <= fullwidth
            # i.e.    2 + 2*len(sepchar)*N + len(title) <= fullwidth
            #         2*len(sepchar)*N <= fullwidth - len(title) - 2
            #         N <= (fullwidth - len(title) - 2) // (2*len(sepchar))
            N = max((fullwidth - len(title) - 2) // (2 * len(sepchar)), 1)
            fill = sepchar * N
            line = "{} {} {}".format(fill, title, fill)
        else:
            # we want len(sepchar)*N <= fullwidth
            # i.e.    N <= fullwidth // len(sepchar)
            line = sepchar * (fullwidth // len(sepchar))
        # in some situations there is room for an extra sepchar at the right,
        # in particular if we consider that with a sepchar like "_ " the
        # trailing space is not important at the end of the line
        if len(line) + len(sepchar.rstrip()) <= fullwidth:
            line += sepchar.rstrip()

        self.line(line, **markup)

    def write(self, msg: str, *, flush: bool = False, **markup: bool) -> None:
        if msg:
            current_line = msg.rsplit("\n", 1)[-1]
            if "\n" in msg:
                self._current_line = current_line
            else:
                self._current_line += current_line

            msg = self.markup(msg, **markup)

            self._file.write(msg)
            if flush:
                self.flush()

    def line(self, s: str = "", **markup: bool) -> None:
        self.write(s, **markup)
        self.write("\n")

    def flush(self) -> None:
        self._file.flush()

    def _write_source(self, lines: Sequence[str], indents: Sequence[str] = ()) -> None:
        """Write lines of source code possibly highlighted.

        Keeping this private for now because the API is clunky. We should discuss how
        to evolve the terminal writer so we can have more precise color support, for example
        being able to write part of a line in one color and the rest in another, and so on.
        """
        if indents and len(indents) != len(lines):
            raise ValueError(
                "indents size ({}) should have same size as lines ({})".format(
                    len(indents), len(lines)
                )
            )
        if not indents:
            indents = [""] * len(lines)
        source = "\n".join(lines)
        new_lines = self._highlight(source).splitlines()
        for indent, new_line in zip(indents, new_lines):
            self.line(indent + new_line)

    def _highlight(self, source: str) -> str:
        """Highlight the given source code if we have markup support."""
        if not self.hasmarkup:
            return source
        try:
            from pygments.formatters.terminal import TerminalFormatter
            from pygments.lexers.python import PythonLexer
            from pygments import highlight
        except ImportError:
            return source
        else:
            highlighted = highlight(
                source, PythonLexer(), TerminalFormatter(bg="dark")
            )  # type: str
            return highlighted
