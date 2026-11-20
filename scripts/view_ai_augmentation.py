"""Display frozen input batches for actual agent reading; never derives labels."""
import argparse
import json
from pathlib import Path
from polarization_pipeline.targeted.common import read_csv

parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
parser.add_argument("start", type=int)
parser.add_argument("--count", type=int, default=100)
args = parser.parse_args()
sample = read_csv(args.root / "sample.csv")
for index in range(args.start, min(len(sample), args.start + args.count)):
    row = sample.iloc[index]
    targets = ";".join(match["target_name"] for match in json.loads(row.candidates_json))
    print(f"{index}|{targets}|{row.text.replace(chr(10), ' ')}")
