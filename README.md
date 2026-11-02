# Electrode Assembly Mapper

Generate channel maps for modular electrode assemblies by combining:

- electrode contact geometry from DXF files,
- component pin mappings from JSON files, and
- assembly connections from CSV files.

The output maps each electrode contact position to the final PCB
or headstage channel.

## Quick start

### Install

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Alternatively:

```bash
conda env create -f environment.yml
conda activate electrode2geometry
python -m pip install -r requirements.txt
```

### Run

Start Jupyter from the repository root:

```bash
jupyter notebook interface.ipynb
```

Run the notebook cells in order. Upload the DXF, component JSON, and assembly
CSV files, set the DXF `layer_name`, click **Generate Channel Map**, then click
**Export to CSV**. Results are saved under `results/`.

## Input files

### Electrode DXF

The parser reads closed `LWPOLYLINE` or legacy `POLYLINE` contours from the
selected layer. It calculates one centroid per contour, orders contacts by
descending Y coordinate, and translates the lowest-Y contact to `(0, 0)`.

The default scale is one micrometre per DXF unit. Set `um_per_dxf_unit` when
the DXF uses a different scale. If there is no reliable layer name, use
`layer_name=None` and set `num_contours`; in that mode the final contour is
assumed to be a hook loop and is removed.

### Component mapping JSON

Each definition contains a unique `name`, a `component_type`, and a local
`mapping`:

```json
{
  "name": "headstage_Intan256",
  "component_type": "headstage",
  "mapping": {
    "d37": 229,
    "d35": 227
  }
}
```

Example definitions are in [modular_mapping_files](modular_mapping_files).
Mappings are treated as internal paths from `in_<source>` to
`out_<destination>`. The notebook assigns the component category from the
upload control used: electrode, flex PCB, rigid PCB, or headstage.

### Assembly CSV

The file must contain these columns (comma or semicolon delimiters are
accepted):

```csv
source_instance,source_pin,destination_instance,destination_pin
electrode_0,L1,flex_pcb_0,L1
flex_pcb_0,L1,headstage_0,d37
```

The loader adds the `out_` prefix to source
pins and the `in_` prefix to destination pins.

## Important conventions

- The notebook creates instance IDs from upload order:
  `electrode_0`, `electrode_1`, `flex_pcb_0`, `rigid_pcb_0`, and
  `headstage_0`. Use these exact names in the assembly CSV, they are generated
  from category and upload order, not read from the JSON `name`.
- Electrode mapping keys should be numerical contact IDs (`1`, `2`, `3`, ...).
  They are sorted numerically when possible, then lexicographically, and that
  order must match the DXF contact order.
- DXFs are assigned to electrode instances in file-selection order. If one DXF
  is selected, it is reused for every electrode; if fewer DXFs than electrodes
  are selected, the last DXF is reused for the remaining electrodes.
- The terminal category falls back in this order: headstage, rigid PCB, then
  flex PCB. The last available category in that order is used as the terminal.
- Instance IDs cannot contain `.`.
- Each source pin and destination pin can have only one connection. Cycles,
  unknown instances, duplicate model names, duplicate destinations in a JSON
  mapping, and malformed CSV headers are rejected.
- Only paths that reach the terminal category are exported.

## Output

Files are written as `results/<first-dxf-name>_channel_map.csv`:

| Column | Meaning |
| --- | --- |
| `x_um` | Relative contact X coordinate in micrometres |
| `y_um` | Relative contact Y coordinate in micrometres |
| `pcb_channel` | Terminal pin/channel identifier |
| `origin` | Electrode instance |

Example:

```csv
x_um,y_um,pcb_channel,origin
772.5,3150.0,229,electrode_0
```

Export fails if any allocated contact has no complete route; this prevents
partial channel maps. Existing output files with the same name are overwritten.

## Code layout

- [interface.ipynb](interface.ipynb): interactive end-to-end workflow
- [assembly_routing.py](assembly_routing.py): component registration and path
  validation
- [utils.py](utils.py): DXF parsing, plotting, map construction, and export
- [modular_mapping_files](modular_mapping_files): example inputs
- [results](results): generated maps

## Limitations

The code does not verify DXF units, electrical direction, connector
orientation, channel ranges, channel uniqueness, physical contact duplication,
or agreement between geometry and mapping counts. Inspect the contact plot and
the exported CSV before using a map for hardware assembly.
