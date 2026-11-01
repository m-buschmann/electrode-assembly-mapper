import math
import numpy as np
import ezdxf
import matplotlib.pyplot as plt
import csv
import json
import pandas as pd


def _centroids_from_polygons(polygons):
    """
    Compute the centroids of a list of polygons.
    Use it to calculate the centroid of each individual electrode contact.
    """
    polygons = [np.asarray(p, dtype=float) for p in polygons]
    centroids = np.zeros((len(polygons), 2), dtype=float)

    for k, p in enumerate(polygons):
        if len(p) >= 2 and np.allclose(p[0], p[-1]):
            p = p[:-1]

        if len(p) < 3:
            continue

        q = np.roll(p, -1, axis=0)
        cross = p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]
        twice_area = np.sum(cross)

        if abs(twice_area) < 1e-12:
            centroids[k] = p.mean(axis=0)
        else:
            centroids[k, 0] = np.sum((p[:, 0] + q[:, 0]) * cross) / (3 * twice_area)
            centroids[k, 1] = np.sum((p[:, 1] + q[:, 1]) * cross) / (3 * twice_area)

    return centroids



def read_electrode_centroids(dxf_file, um_per_dxf_unit=1.0, layer_name="electrodes", num_contours=None):
    """Find centroids of closed POLYLINE contours in an ASCII DXF.

    Rows are ordered from the top contact to the bottom contact; the bottom
    contact is translated to [0, 0]. Columns are X and Y in micrometres.
    """
    # ------------------------------------------------------------
    # NEW: prefer ezdxf for modern LWPOLYLINE DXF files
    # ------------------------------------------------------------
    def layer_matches(layer):
        if layer_name is None:
            return True
        if layer is None:
            return False
        return str(layer).strip().lower() == str(layer_name).strip().lower()
    
    try:
        doc = ezdxf.readfile(dxf_file)
        msp = doc.modelspace()

        polygons = []
        for e in msp.query("LWPOLYLINE"):
            layer = getattr(e.dxf, "layer", None)
            if not layer_matches(layer):
                continue

            pts = np.asarray(e.get_points("xy"), dtype=float)
            if pts.size == 0:
                continue
            
            if len(pts) >= 2 and np.allclose(pts[0], pts[-1]):
                pts = pts[:-1]
            if len(pts) >= 3:
                polygons.append(pts)

        if polygons:
            centroids = _centroids_from_polygons(polygons)
            order = np.argsort(-centroids[:, 1], kind="stable")
            centroids = centroids[order]

            if layer_name is None and num_contours is not None:
                centroids = centroids[:-1]  # remove the hook loop
                num_contours = int(num_contours)
                if num_contours > 0 and centroids.shape[0] > num_contours:
                    centroids = centroids[-num_contours:]

            xy = np.round((centroids - centroids[-1]) * um_per_dxf_unit, 6)
            xy[-1] = [0.0, 0.0]
            print(f"Found {xy.shape[0]} closed contact contours.")
            return xy
    except Exception:
        pass

    # ------------------------------------------------------------
    # Peter's raw-DXF parser kept as fallback
    # ------------------------------------------------------------
    with open(dxf_file, "r", errors="ignore") as fh:
        lines = [ln.strip() for ln in fh.read().splitlines()]

    # DXF is a stream of (group code, value) pairs, one per line.
    while lines and lines[-1] == "":
        lines.pop()
    n = len(lines) // 2

    codes = []
    values = []
    for i in range(n):
        try:
            codes.append(int(float(lines[2 * i])))
        except ValueError:
            codes.append(None)
        values.append(lines[2 * i + 1])

    polygons = []
    current = []
    current_layer = None
    in_poly = False

    i = 0
    while i < n:
        if codes[i] == 8:
            current_layer = values[i]

        elif codes[i] == 0:
            entity = values[i].upper()
            if entity == "POLYLINE":
                current = []
                current_layer = None
                in_poly = True

            elif entity == "VERTEX" and in_poly:
                x = math.nan
                y = math.nan
                j = i + 1
                while j < n and codes[j] != 0:
                    if codes[j] == 10:
                        x = float(values[j])
                    elif codes[j] == 20:
                        y = float(values[j])
                    j += 1
                if math.isfinite(x) and math.isfinite(y):
                    current.append([x, y])
                i = j - 1
            elif entity == "SEQEND" and in_poly:
                if len(current) >= 3 and layer_matches(current_layer):
                    polygons.append(np.array(current, dtype=float))
                current = []
                current_layer = None
                in_poly = False
        i += 1


    if not polygons:
        raise ValueError(
            f"No contour polygons were found for layer '{layer_name}' in the DXF. "
            "If this file uses legacy POLYLINE entities, make sure the layer name matches or pass layer_name=None."
        )
    
    centroids = _centroids_from_polygons(polygons)
    order = np.argsort(-centroids[:, 1], kind="stable")
    centroids = centroids[order]

    if layer_name is None and num_contours is not None:
        centroids = centroids[:-1]  # remove the hook loop
        num_contours = int(num_contours)
        if num_contours > 0 and centroids.shape[0] > num_contours:
            centroids = centroids[-num_contours:]

    xy = np.round((centroids - centroids[-1]) * um_per_dxf_unit, 6)
    xy[-1] = [0.0, 0.0]
    print(f"Found {xy.shape[0]} closed contact contours.")
    return xy


def print_text(ax, ch, coords):
    ax.text(coords[0], coords[1], str(ch), ha="center", va="center", color='r', fontsize=6,
            bbox=dict(boxstyle="square", ec=(0., 0., 0.), fc=(1., 1, 1)))

def load_and_plot_electrodes(dxf_path, layer_name="electrodes", um_per_dxf_unit=1.0, num_contours=None):
    """Load electrode centroids from DXF and plot them with labels.
    
    Args:
        dxf_path: Path to DXF file
        layer_name: DXF layer name containing electrodes
        um_per_dxf_unit: Scaling factor for coordinates
    
    Returns:
        xy: (n_electrodes, 2) array of electrode positions in micrometers
    """
    xy = read_electrode_centroids(dxf_path, um_per_dxf_unit=um_per_dxf_unit, 
                                   layer_name=layer_name, num_contours=num_contours)
    
    fig, ax = plt.subplots(figsize=(8, 10))
    for i, (x, y) in enumerate(xy):
        print_text(ax, i + 1, [x, y])
    
    ax.scatter(xy[:, 0], xy[:, 1], s=20, color="tab:blue", alpha=0.7)
    ax.set_aspect("equal")
    ax.set_title("Electrode layout centroids")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    plt.show()
    
    return xy


def create_channel_map(xy, csv_path):
    """Read CSV mapping and create 3×n channel map matrix.
    
    Args:
        xy: (n_electrodes, 2) array of electrode positions
        csv_path: Path to CSV with columns: Electrode Channel, Connector Channel
    
    Returns:
        channel_map: (3, n_channels) array where:
            - row 0: x-coordinates
            - row 1: y-coordinates
            - row 2: PCB connector channel numbers
    """
    with open(csv_path, newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        mapping_rows = [row for row in reader 
                       if row["Electrode Channel"].strip()]
    
    n_channels = len(mapping_rows)
    channel_map = np.zeros((3, n_channels), dtype=float)
    
    for row in mapping_rows:
        electrode_ch = int(row["Electrode Channel"])
        connector_ch = int(row["Connector Channel"])
        idx = electrode_ch - 1
        
        channel_map[0, idx] = xy[idx, 0]
        channel_map[1, idx] = xy[idx, 1]
        channel_map[2, idx] = connector_ch
    
    return channel_map

def export_channel_map_to_csv(channel_map, dxf_file):
    """Export 4-row channel map to CSV.
    
    Args:
        channel_map: (4, n_channels) array where rows are:
            - row 0: x-coordinates (µm)
            - row 1: y-coordinates (µm)
            - row 2: destination/pcb channel
            - row 3: origin electrode instance ID
        dxf_file: Path to DXF file (used for naming output)
    
    Returns:
        output_path: Path to the saved CSV file
    """
    import os
    base_name = os.path.splitext(os.path.basename(dxf_file))[0]
    export_file = f"{base_name}_channel_map.csv"
    
    header = "x_um,y_um,pcb_channel,origin"
    
    # Handle both 3-row and 4-row matrices for backwards compatibility
    if channel_map.shape[0] == 4:
        fmt = ['%.6f', '%.6f', '%s', '%s']
    else:
        header = "x_um,y_um,pcb_channel"
        fmt = ['%.6f', '%.6f', '%s']

    np.savetxt(
        export_file,
        channel_map.T, 
        delimiter=",", 
        header=header,
        comments="",
        fmt=fmt
    )
    return export_file


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