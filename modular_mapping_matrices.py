import json
from pathlib import Path
import numpy as np
import pandas as pd

# Define input/output paths
csv_path = "electrode2geometry2/ex1_electrode-headstage_connection.csv"
output_dir = Path("modular_mappings")
output_dir.mkdir(exist_ok=True)

# Define the exact column header names from the original CSV
COL_ELECTRODE = "Electrode Channel"
COL_PCB_PAD = "Connector Pad"
COL_HEADSTAGE = "Connector Channel"

PCB_NAME = "ex_1_intan256"
HEADSTAGE_NAME = "ex_1_unknown"

# 1. Load the original semicolon-delimited CSV
df = pd.read_csv(csv_path, sep=";", dtype=str)

# Clean whitespace from headers and text cells
df.columns = df.columns.str.strip()
df = df.apply(lambda col: col.str.strip() if col.dtype == "object" else col)


def build_clean_dict(data_frame: pd.DataFrame, col_in: str, col_out: str) -> dict:
    """Filters empty/NaN rows and parses values as ints if numeric, otherwise strings."""
    # Drop rows where either input or output pad/channel is missing
    valid = data_frame.dropna(subset=[col_in, col_out])
    valid = valid[(valid[col_in] != "") & (valid[col_out] != "")]

    mapping = {}
    for _, row in valid.iterrows():
        k_str, v_str = row[col_in], row[col_out]

        # Convert digits to native ints ("1" -> 1), keep text strings as-is ("P$64" -> "P$64")
        k = int(k_str) if k_str.isdigit() else k_str
        v = int(v_str) if v_str.isdigit() else v_str

        mapping[k] = v

    return mapping

# 2. Build Modular Probe JSON (Electrode -> Connector Pad)
probe_json = {
    "component_type": "electrode_to_connector",
    "name": f"probe_64ch_{PCB_NAME}",
    "input_label": "electrode_channel",
    "output_label": "connector_pad",
    "mapping": build_clean_dict(df, COL_ELECTRODE, COL_PCB_PAD),
}

# 3. Build Modular Headstage JSON (Connector Pad -> Headstage Channel)
headstage_json = {
    "component_type": "connector_to_headstage",
    "name": f"headstage_{HEADSTAGE_NAME}",
    "input_label": "connector_pad",
    "output_label": "headstage_channel",
    "mapping": build_clean_dict(df, COL_PCB_PAD, COL_HEADSTAGE),
}

# 4. Save components to JSON files
with open(output_dir / f"probe_{PCB_NAME}.json", "w") as f:
    json.dump(probe_json, f, indent=4)

with open(output_dir / f"headstage_{HEADSTAGE_NAME}.json", "w") as f:
    json.dump(headstage_json, f, indent=4)

print("Successfully saved modular JSON mappings.")