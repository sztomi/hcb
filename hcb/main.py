from hcb.brain import Brain
from pathlib import Path

def main():
  from argparse import ArgumentParser
  parser = ArgumentParser()
  parser.add_argument("compilation_database")
  parser.add_argument("headers", nargs="+")
  args = parser.parse_args()
  brain = Brain(args)
  brain.parse_file(Path(args.headers[0]))


if __name__ == "__main__":
  main()