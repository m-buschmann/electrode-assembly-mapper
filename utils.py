import math
import numpy as np
import ezdxf


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


def read_electrode_centroids(dxf_file, um_per_dxf_unit=1.0):
    """Find centroids of closed POLYLINE contours in an ASCII DXF.

    Rows are ordered from the top contact to the bottom contact; the bottom
    contact is translated to [0, 0]. Columns are X and Y in micrometres.
    """
    # ------------------------------------------------------------
    # NEW: prefer ezdxf for modern LWPOLYLINE DXF files
    # ------------------------------------------------------------
    try:
        doc = ezdxf.readfile(dxf_file)
        msp = doc.modelspace()

        polygons = []
        for e in msp.query("LWPOLYLINE"):
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
    in_poly = False
    i = 0
    while i < n:
        if codes[i] == 0:
            entity = values[i].upper()
            if entity == "POLYLINE":
                current = []
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
                if len(current) >= 3:
                    polygons.append(np.array(current, dtype=float))
                current = []
                in_poly = False
        i += 1

    if not polygons:
        raise ValueError("No POLYLINE contours were found in the DXF.")

    centroids = _centroids_from_polygons(polygons)

    # Larger DXF Y is the top of the drawing; sort descending (stable).
    order = np.argsort(-centroids[:, 1], kind="stable")
    centroids = centroids[order]
    xy = np.round((centroids - centroids[-1]) * um_per_dxf_unit, 6)
    xy[-1] = [0.0, 0.0]
    print(f"Found {xy.shape[0]} closed contact contours.")
    return xy


def print_text(ax, ch, coords):
    ax.text(coords[0], coords[1], str(ch), ha="center", va="center", color='r', fontsize=6,
            bbox=dict(boxstyle="square", ec=(0., 0., 0.), fc=(1., 1, 1)))