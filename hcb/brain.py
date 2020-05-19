import subprocess as sp

from pathlib import Path
from typing import List

from hcb.clang import cindex
from hcb.clang.cindex import TranslationUnit, CursorKind, TokenKind, Cursor, SourceRange
from hcb.source_buffer import SourceBuffer

from pprint import pprint


class Brain:
  def __init__(self, args):
    cindex.Config.set_library_file("/usr/lib/llvm-8/lib/libclang.so")
    self.index = cindex.Index.create()
    self.compdb = cindex.CompilationDatabase.fromDirectory(args.compilation_database)

  def get_args(self, file_path: Path):
    SKIPPED = ["-c", "-Werror"]
    file_as_source = file_path.with_suffix(".cpp")
    final_args = []
    args = list(self.compdb.getCompileCommands(str(file_as_source))[0].arguments)
    args = args[1:]
    saw_xclang = False
    for arg in args:
      if arg in SKIPPED:
        continue
      elif arg == str(file_path) or arg == str(file_as_source):
        continue
      if arg == "-Xclang":
        saw_xclang = True
        continue
      elif saw_xclang:
        saw_xclang = False
        continue
      final_args.append(arg)
    final_args += ["-x", "c++", "-include", "StdAfx.h"]
    return final_args

  def is_file_node(self, file_path: Path, node):
    try:
      if node.kind == CursorKind.TRANSLATION_UNIT:
        return True
      return Path(node.location.file.name).resolve() == file_path.resolve()
    except AttributeError:
      return False

  def walk_file_nodes(self, file_path: Path, node):
    if self.is_file_node(file_path, node):
      yield node
      for child in node.get_children():
        yield from self.walk_file_nodes(file_path, child)

  def get_function_decl(self, func: Cursor) -> str:
    decl = []
    for tok in func.get_tokens():
      if tok.kind == TokenKind.PUNCTUATION and tok.spelling == "{":
        break
      decl.append(tok)
    start = decl[0].extent.start
    end = decl[-2].extent.end
    lines = (
      Path(func.location.file.name).read_text().split("\n")[start.line - 1 : end.line]
    )
    lines[0] = lines[0][start.column - 1 :]
    lines[-1] = lines[-1][: end.column - 1]
    return lines

  def get_qualified_name(self, cursor: Cursor) -> str:
    if cursor is None or cursor.kind == CursorKind.TRANSLATION_UNIT:
      return ""
    res = self.get_qualified_name(cursor.semantic_parent)
    if res != "":
      return f"{res}::{cursor.spelling}"
    return cursor.spelling

  def is_func_def(self, cursor: Cursor) -> bool:
    funcs = (
      CursorKind.FUNCTION_DECL,
      CursorKind.CXX_METHOD,
      #CursorKind.CONSTRUCTOR,
      CursorKind.DESTRUCTOR,
    )
    if cursor.kind not in funcs or not cursor.is_definition:
      return False
    for tok in cursor.get_tokens():
      if tok.kind == TokenKind.PUNCTUATION and tok.spelling == "{":
        return True
    return False

  def get_func_body_range(self, func: Cursor, prev: bool = False) -> SourceRange:
    prev_tok = None
    for tok in func.get_tokens():
      if tok.kind == TokenKind.PUNCTUATION and tok.spelling == "{":
        if prev:
          return SourceRange.from_locations(prev_tok.extent.end, func.extent.end)
        else:
          return SourceRange.from_locations(tok.extent.start, func.extent.end)
      prev_tok = tok

  def get_body(self, func: Cursor, buf: SourceBuffer) -> str:
    return buf.copy_range(self.get_func_body_range(func))

  def get_qualified_decl(self, func: Cursor) -> str:
    decl = "\n".join(self.get_function_decl(func))
    qname = self.get_qualified_name(func)
    return decl.replace(func.spelling, qname)

  def get_extracted_body(self, func: Cursor, buf: SourceBuffer) -> str:
    decl = self.get_qualified_decl(func)
    body = self.format(self.get_body(func, buf))
    return f"{decl}\n{body}"

  def format(self, lines: str) -> str:
    clang_format = sp.Popen(["clang-format"], stdin=sp.PIPE, stdout=sp.PIPE)
    output = clang_format.communicate(lines.encode())[0]
    return output.decode()

  def parse_file(self, file_path: Path):
    file_args = list(self.get_args(file_path))
    buf = SourceBuffer(file_path)
    tu = self.index.parse(str(file_path), file_args)

    source_path = file_path.with_suffix(".cpp")
    with source_path.open("a") as source:
      source.write("\n")
      for cursor in self.walk_file_nodes(file_path, tu.cursor):
        if self.is_func_def(cursor):
          source.write(self.get_extracted_body(cursor, buf))
          source.write("\n\n")

    offset = 0
    for cursor in self.walk_file_nodes(file_path, tu.cursor):
      if self.is_func_def(cursor):
        offset -= buf.replace_range(self.get_func_body_range(cursor, True), ";", offset)

    file_path.write_text(buf.text)
