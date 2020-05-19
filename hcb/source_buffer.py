from pathlib import Path
from typing import List, Tuple

from clang.cindex import SourceRange



class SourceBuffer:
  def __init__(self, file_path: Path):
    self.file_path = file_path
    self.lines = file_path.read_text().splitlines(keepends=False)
    self.text = file_path.read_text()

  def cut(self, srange: SourceRange) -> List[str]:
    def _get_line(line_num: int) -> str:
      return self.lines[line_num - 1]

    def _cut_whole(line_num: int) -> str:
      line = _get_line(line_num)
      self.lines.remove(line)
      return line

    def _cut_part(line_num: int, start_column: int, end_column: int) -> str:
      line = _get_line(line_num)
      end_column = end_column or len(line)
      before = line[:start_column-1]
      mid = line[start_column-1:end_column]
      after = line[end_column-1:]
      self.lines[line_num - 1] = before + after
      return mid

    # columns and lines are 1-based indices
    if srange.start.line == srange.end.line:
      # Case 1: just one line
      line = self.lines[srange.start.line - 1]
      if srange.start.column == 1 and srange.end.column == len(line):
        # 1.1: The entire line is cut
        return [_cut_whole(srange.start.line)]
      else:
        # 1.2: need to cut pieces
        return [_cut_part(srange.start.line, srange.start.column, srange.end.column)]
    else:
      # Case 2: multiple lines
      line_count = srange.end.line - srange.start.line + 1
      if line_count == 2:
        # 2.1: No lines in-between
        cut_lines = [
          _cut_part(srange.start.line, srange.start.column, None),
          _cut_part(srange.end.line, 1, srange.end.column)
        ]
        return cut_lines
      else:
        # 2.2: multiple lines
        cut_lines = [
          _cut_part(srange.start.line, srange.start.column, None)
        ]
        in_between_count = line_count - 2
        for idx, line_num in enumerate(range(srange.start.line + 1, srange.end.line)):
          cut_lines.append(_get_line(line_num))
        cut_lines.append(_cut_part(srange.end.line, 1, srange.end.column))

        # note, these are indices here, not line numbers
        del self.lines[srange.start.line:srange.end.line]

        return cut_lines


  def offsets(self, srange: SourceRange) -> Tuple[int, int]:
    return srange.start.offset, srange.end.offset

  def copy_range(self, srange: SourceRange) -> str:
    start, end = self.offsets(srange)
    return self.text[start:end]

  def replace_range(self, srange: SourceRange, replacement: str, offset: int) -> int:
    start, end = self.offsets(srange)
    start += offset
    end += offset
    orig_len = len(self.text)
    before = self.text[:start]
    after = self.text[end:]
    self.text = before + replacement + after
    new_len = len(self.text)
    return orig_len - new_len
