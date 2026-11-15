"""Read an R program as top-level statements and trace the data frames a block of lines reads.

lineage.json gives each ADaM variable its program lines (the code under its
`@derive` tag). Those lines usually read intermediate data frames built earlier
(`ex_dated`, `randomised`, `vsbl`): this module finds the statements that built
them, recursively, down to `read_sdtm("ex")` / `read_adam("adsl")`, so the
explorer can show every line a variable depends on, not just its own block.

    program = RProgram(text)
    program.trace(46, 53, own_frame="adae") -> [Statement, ...]   # upstream, nearest first

Plain text analysis, no R parser: statements are split on balanced brackets and
trailing operators; strings and comments are masked first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

IDENTIFIER = re.compile(r"(?<![\w.])([A-Za-z.][\w.]*)")
ASSIGNMENT = re.compile(r"^\s*([A-Za-z.][\w.]*)\s*(\$\s*[\w.]+|\[\[[^\]]*\]\]|\[[^\]]*\])?\s*(<<-|<-|=(?!=))")
READ_CALL = re.compile(r"\bread_(sdtm|adam)\(\s*[\"']([A-Za-z0-9_]+)[\"']")
CONTINUATION = re.compile(r"(%>%|\|>|%\w*%|[-+*/,&|~^(]|<-|=|\bin)\s*$")
R_WORDS = {
    "function", "if", "else", "for", "while", "in", "TRUE", "FALSE", "NULL", "NA", "Inf", "NaN", "return", "next", "break",
    "NA_character_", "NA_real_", "NA_integer_", "T", "F",
}
MAX_TRACED = 14


@dataclass
class Statement:
    start: int                      # 1-based first line
    end: int                        # 1-based last line
    target: str | None              # frame or function assigned, if any
    reads: set[str] = field(default_factory=set)        # lower-case-ish identifiers (frames, functions, values)
    tokens: set[str] = field(default_factory=set)       # every identifier, for column matching
    loads: list[tuple[str, str]] = field(default_factory=list)   # ("sdtm" | "adam", "DM")
    defines_function: bool = False


def mask(line: str, in_string: str | None) -> tuple[str, str | None]:
    """The line with string contents blanked and the comment cut; the open quote carried to the next line."""
    output = []
    index = 0
    while index < len(line):
        char = line[index]
        if in_string is not None:
            if char == "\\":
                output.append("  ")
                index += 2
                continue
            if char == in_string:
                in_string = None
                output.append(char)
            else:
                output.append(" ")
        elif char in "\"'`":
            in_string = char
            output.append(char)
        elif char == "#":
            break
        else:
            output.append(char)
        index += 1
    return "".join(output), in_string


def bracket_balance(code: str) -> int:
    return sum(code.count(opener) for opener in "([{") - sum(code.count(closer) for closer in ")]}")


class RProgram:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.masked: list[str] = []
        self.statements = self._split()

    def _split(self) -> list[Statement]:
        statements, depth, start, chunk, in_string = [], 0, None, [], None
        for number, raw in enumerate(self.lines, start=1):
            code, in_string = mask(raw, in_string)
            self.masked.append(code)
            if start is None:
                if code.strip() == "":
                    continue
                start = number
            chunk.append((raw, code))
            depth += bracket_balance(code)
            if depth <= 0 and in_string is None and CONTINUATION.search(code) is None:
                statements.append(self._statement(start, number, chunk))
                depth, start, chunk = 0, None, []
        if start is not None:
            statements.append(self._statement(start, len(self.lines), chunk))
        return statements

    @staticmethod
    def _statement(start: int, end: int, chunk: list[tuple[str, str]]) -> Statement:
        code = "\n".join(masked for _, masked in chunk)
        raw = "\n".join(original for original, _ in chunk)
        assignment = ASSIGNMENT.match(code)
        target = None
        modifies_frame = False
        body = code
        if assignment is not None:
            target = assignment.group(1)
            modifies_frame = bool(assignment.group(2))
            body = code[assignment.end():]
        tokens = {match.group(1) for match in IDENTIFIER.finditer(body)} - R_WORDS
        if modifies_frame is True:
            tokens.add(target)          # `adsl$X <- ...` / `x[i] <- ...` also reads the frame it modifies
        statement = Statement(start, end, target, tokens=tokens)
        statement.reads = {token for token in tokens if token != token.upper() or token.islower()}
        statement.loads = [(kind, name.upper()) for kind, name in READ_CALL.findall(raw)]
        statement.defines_function = re.match(r"\s*function\b", body) is not None
        return statement

    def text(self, start: int, end: int) -> str:
        return "\n".join(self.lines[start - 1:end])

    def tokens_in(self, start: int, end: int) -> set[str]:
        """Identifiers on lines start..end themselves (not the whole statement around them)."""
        return {match.group(1) for line in self.masked[start - 1:end] for match in IDENTIFIER.finditer(line)} - R_WORDS

    def assigning_lines(self, start: int, end: int, name: str) -> list[int]:
        """Lines in start..end that assign `name` (`NAME = ...` in a mutate, `x$NAME <- ...`, `NAME <- ...`)."""
        pattern = re.compile(rf"(^|[\s(,$]){re.escape(name)}\s*(<-|=(?!=))")
        return [number for number in range(start, end + 1) if pattern.search(self.masked[number - 1])]

    def lines_naming(self, start: int, end: int, name: str) -> list[int]:
        pattern = re.compile(rf"(?<![\w.]){re.escape(name)}(?![\w.])")
        return [number for number in range(start, end + 1) if pattern.search(self.masked[number - 1])]

    def covering(self, start: int, end: int) -> list[Statement]:
        return [statement for statement in self.statements if statement.end >= start and statement.start <= end]

    def assignment_before(self, name: str, line: int) -> Statement | None:
        found = None
        for statement in self.statements:
            if statement.start >= line:
                break
            if statement.target == name:
                found = statement
        return found

    def trace(self, start: int, end: int, own_frame: str) -> list[Statement]:
        """Statements before `start` that built what lines start..end read, nearest dependency first.

        The dataset being built (`own_frame`) is not traced: every earlier step of
        the program modifies it, and the variable-level lineage already says which
        of its columns this block reads.
        """
        block = self.covering(start, end)
        pending = [(name, start) for statement in block for name in sorted(statement.reads)]
        traced: list[Statement] = []
        seen: set[tuple[int, int]] = {(statement.start, statement.end) for statement in block}
        while pending and len(traced) < MAX_TRACED:
            name, before = pending.pop(0)
            if name == own_frame:
                continue
            statement = self.assignment_before(name, before)
            if statement is None or (statement.start, statement.end) in seen:
                continue
            seen.add((statement.start, statement.end))
            traced.append(statement)
            pending.extend((read, statement.start) for read in sorted(statement.reads))
        return traced

