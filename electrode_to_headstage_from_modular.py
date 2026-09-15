import json
import pandas as pd


def load_mapping(json_path: str) -> dict:
    """Loads JSON mapping and converts numeric string keys/values to native ints."""
    with open(json_path, "r") as f:
        data = json.load(f)

    return {
        int(k) if str(k).isdigit() else k: int(v) if str(v).isdigit() else v
        for k, v in data["mapping"].items()
    }


def get_electrode_to_headstage_mapping(
    probe_json_path: str, headstage_json_path: str
) -> pd.DataFrame:
    """Composes Probe and Headstage maps into a clean Electrode -> Headstage table."""
    probe_map = load_mapping(probe_json_path)
    headstage_map = load_mapping(headstage_json_path)

    # Chain maps directly: Electrode -> PCB Pad -> Headstage Channel
    records = [
        {
            "electrode_channel": electrode,
            "headstage_channel": headstage_map.get(pcb_pad, None),
        }
        for electrode, pcb_pad in probe_map.items()
    ]

    df = pd.DataFrame(records)

    # Sort numerically by electrode channel
    is_numeric = df["electrode_channel"].apply(lambda x: str(x).isdigit())
    df_sorted = pd.concat(
        [
            df[is_numeric]
            .astype({"electrode_channel": int})
            .sort_values("electrode_channel"),
            df[~is_numeric],
        ]
    ).reset_index(drop=True)

    return df_sorted


# Execution
df_routing = get_electrode_to_headstage_mapping(
    "modular_mappings/probe_ex_1_intan256.json",
    "modular_mappings/headstage_ZD64.json",
)

# Output as DataFrame
print(df_routing)

# Output as direct dictionary lookup {electrode_channel: headstage_channel}
routing_dict = dict(
    zip(df_routing["electrode_channel"], df_routing["headstage_channel"])
)