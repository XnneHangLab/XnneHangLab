#!/usr/bin/env python3
import sys
from typing import Dict


def load_tokens():
    ans = dict()
    i = 0
    with open("tokens.json", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if '[' in line: continue
            if ']' in line: continue
            if '"' in line and ',' in line:
              line = line[1:-2]

            ans[i] = line.strip()
            i += 1
    print('num tokens', i)
    return ans


def write_tokens(tokens: Dict[int, str]):
    with open("tokens.txt", "w", encoding="utf-8") as f:
        for idx, s in tokens.items():
            f.write(f"{s} {idx}\n")


def main():
    tokens = load_tokens()
    write_tokens(tokens)


if __name__ == "__main__":
    main()
