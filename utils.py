import csv
import math
import os

import ezdxf
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _centroids_from_polygons(polygons):
    """Compute the centroid of each electrode-contact polygon."""
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


def read_electrode_centroids(
    dxf_file,
    um_per_dxf_unit=1.0,
    layer_name="electrodes",
    num_contours=None,
):
    """Find centroids of closed POLYLINE contours in an ASCII DXF.

    Rows are ordered from the top contact to the bottom contact; the bottom
    contact is translated to [0, 0]. Columns are X and Y in micrometres.
    """

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

    # Fall back to parsing legacy POLYLINE entities.
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
    ax.text(
        coords[0],
        coords[1],
        str(ch),
        ha="center",
        va="center",
        color="r",
        fontsize=6,
        bbox=dict(boxstyle="square", ec=(0.0, 0.0, 0.0), fc=(1.0, 1.0, 1.0)),
    )


def load_and_plot_electrodes(
    dxf_path,
    layer_name="electrodes",
    um_per_dxf_unit=1.0,
    num_contours=None,
):
    """Load electrode centroids from DXF and plot them with labels.

    Args:
        dxf_path: Path to DXF file
        layer_name: DXF layer name containing electrodes
        um_per_dxf_unit: Scaling factor for coordinates

    Returns:
        xy: (n_electrodes, 2) array of electrode positions in micrometers
    """
    xy = read_electrode_centroids(
        dxf_path,
        um_per_dxf_unit=um_per_dxf_unit,
        layer_name=layer_name,
        num_contours=num_contours,
    )

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
        output_path: Path to the saved CSV file in the ``results`` folder
    """
    if channel_map.ndim != 2 or channel_map.shape[0] != 4:
        raise ValueError("channel_map must have shape (4, n).")

    base_name = os.path.splitext(os.path.basename(dxf_file))[0]
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    export_file = os.path.join(output_dir, f"{base_name}_channel_map.csv")

    df = pd.DataFrame(
        channel_map.T,
        columns=["x_um", "y_um", "pcb_channel", "origin"],
    )

    if df[["x_um", "y_um", "pcb_channel", "origin"]].isna().any().any():
        raise ValueError("Channel map contains incomplete rows.")

    df.to_csv(export_file, index=False)

    return export_file


def build_channel_map(
    complete_report,
    electrode_channel_indices,
    electrode_offsets,
    electrode_xy_maps,
    total_electrodes,
):
    """Build a four-row channel map from completed routing paths."""
    channel_map = np.full((4, total_electrodes), None, dtype=object)

    for item in complete_report:
        source_instance, source_pin = item["source"].rsplit(".", 1)
        destination_pin = item["destination"].rsplit(".", 1)[1]

        if source_pin.startswith("in_"):
            source_pin = source_pin[3:]

        if destination_pin.startswith("out_"):
            destination_pin = destination_pin[4:]
        elif destination_pin.startswith("in_"):
            destination_pin = destination_pin[3:]

        if source_instance not in electrode_channel_indices:
            continue

        local_contact_idx = electrode_channel_indices[source_instance][source_pin]
        global_index = electrode_offsets[source_instance] + local_contact_idx
        xy = electrode_xy_maps[source_instance]

        if local_contact_idx < len(xy):
            channel_map[0, global_index] = xy[local_contact_idx, 0]
            channel_map[1, global_index] = xy[local_contact_idx, 1]
            channel_map[2, global_index] = destination_pin
            channel_map[3, global_index] = source_instance

    return channel_map