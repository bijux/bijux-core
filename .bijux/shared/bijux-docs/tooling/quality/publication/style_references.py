"""Collect literal stylesheet URL/import destinations without parsing declarations."""
from __future__ import annotations
from dataclasses import dataclass


WHITESPACE = ' \t\r\n\f'
HEX = '0123456789abcdefABCDEF'


@dataclass(frozen=True)
class Reference:
    url: str
    line: int
    column: int


def escaped(source: str, position: int) -> tuple[str, int]:
    """Decode one CSS escape while preserving its raw token boundary."""
    position += 1
    if position == len(source):
        raise ValueError('incomplete CSS resource escape')
    if source[position] in '\r\n\f':
        end = position + 2 if source[position:position + 2] == '\r\n' else position + 1
        return '', end
    start = position
    while position < len(source) and position - start < 6 and source[position] in HEX:
        position += 1
    if position != start:
        point = int(source[start:position], 16)
        if position < len(source) and source[position] in WHITESPACE:
            position += 2 if source[position:position + 2] == '\r\n' else 1
        return ('\ufffd' if point == 0 or point > 0x10ffff or 0xd800 <= point <= 0xdfff else chr(point)), position
    return source[position], position + 1


def string(source: str, position: int) -> tuple[str, int]:
    quote = source[position]
    position += 1
    value = []
    while position < len(source):
        character = source[position]
        if character == quote:
            return ''.join(value), position + 1
        if character == '\\':
            character, position = escaped(source, position)
        elif character in '\r\n\f':
            raise ValueError('unescaped newline in CSS resource string')
        else:
            position += 1
        value.append(character)
    raise ValueError('unterminated CSS resource string')


def space(source: str, position: int, *, comments: bool) -> int:
    while position < len(source):
        if source[position] in WHITESPACE:
            position += 1
        elif comments and source.startswith('/*', position):
            end = source.find('*/', position + 2)
            position = len(source) if end < 0 else end + 2
        else:
            break
    return position


def identifier(source: str, position: int) -> tuple[str, int]:
    value = []
    while position < len(source):
        character = source[position]
        if character == '\\':
            character, position = escaped(source, position)
        elif character.isalnum() or character in '-_' or ord(character) >= 128:
            position += 1
        else:
            break
        value.append(character)
    return ''.join(value), position


def url(source: str, position: int) -> tuple[str, int]:
    position = space(source, position, comments=False)
    if position < len(source) and source[position] in "\"'":
        value, position = string(source, position)
        position = space(source, position, comments=True)
    else:
        value = []
        while position < len(source) and source[position] != ')':
            character = source[position]
            if character in WHITESPACE:
                position = space(source, position, comments=False)
                break
            if character in "\"'(" or ord(character) < 32:
                raise ValueError('malformed literal CSS URL')
            if character == '\\':
                if position + 1 == len(source) or source[position + 1] in '\r\n\f':
                    raise ValueError('invalid unquoted CSS URL escape')
                character, position = escaped(source, position)
            else:
                position += 1
            value.append(character)
        value = ''.join(value)
    if position == len(source) or source[position] != ')':
        raise ValueError('unterminated or malformed CSS URL')
    return value, position + 1


def references(source: str) -> list[Reference]:
    """Read URL functions and quoted imports; comments/other strings are inert."""
    result = []
    position = 0
    def append(value, start):
        result.append(Reference(value, source.count('\n', 0, start) + 1,
                                start - source.rfind('\n', 0, start)))
    while position < len(source):
        position = space(source, position, comments=True)
        if position == len(source):
            break
        start = position
        character = source[position]
        if character in "\"'":
            _, position = string(source, position)
        elif character == '@':
            name, position = identifier(source, position + 1)
            if name.lower() == 'import':
                position = space(source, position, comments=True)
                if position < len(source) and source[position] in "\"'":
                    value, position = string(source, position)
                    append(value, start)
        elif character.isalpha() or character in '-_\\' or ord(character) >= 128:
            name, position = identifier(source, position)
            if name.lower() == 'url' and position < len(source) and source[position] == '(':
                value, position = url(source, position + 1)
                append(value, start)
        else:
            position += 1
    return result
