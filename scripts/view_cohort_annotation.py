"""Show complete shuffled pilot texts for direct reading, without user/fold/predictions."""
import argparse
import json
from polarization_pipeline.targeted.common import read_csv

p = argparse.ArgumentParser()
p.add_argument("folder"); p.add_argument("start", type=int); p.add_argument("--count", type=int, default=50)
a = p.parse_args()
sample = read_csv(a.folder + "/pilot_sample.csv")
for index in range(a.start, min(len(sample), a.start + a.count)):
    row = sample.iloc[index]
    targets = ";".join(x["target_id"] + ":" + x["target_name"] for x in json.loads(row.candidates_json))
    print(f"{index}|{targets}|{row.text.replace(chr(10), ' ')}")
