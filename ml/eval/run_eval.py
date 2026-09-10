"""Evaluation entry point.

Reads a manifest from DATA_ROOT and writes aggregate results to eval/results/.
No external corpus is approved (EXT-002, EXT-003 are PROPOSED), so this refuses
to run until a corpus decision is recorded.
"""

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SAHAY-AI evaluation harness")
    parser.add_argument("--manifest", required=True, help="path under DATA_ROOT")
    parser.add_argument("--out", default="eval/results")
    args = parser.parse_args(argv)

    print("Evaluation harness is scaffolded but has no approved corpus.")
    print("EXT-002 (Common Voice Hindi) and EXT-003 (RAVDESS) are PROPOSED.")
    print(f"Requested manifest: {args.manifest}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
