# NOVA-FEA

Local Python pipeline for a GLB vase: reconstruct hollow material geometry, solve linear elastic FEA, and export computed stress with logarithmic blue-to-red colors. No API keys, cloud services, or external mesher are required.

## Install

Use Python 3.11 or newer. CI targets Python 3.11 and 3.12 on Windows and Linux.

Open PowerShell in this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
```

Installation downloads NumPy, SciPy, Trimesh, and meshio. Subsequent analysis runs are offline. On Linux/macOS, replace `.venv\Scripts\python` with `.venv/bin/python`.

## One settings file, one GLB

Edit the same settings file for every run:

```powershell
notepad examples/settings.txt
```

Then provide your GLB and a fresh output folder:

```powershell
.\.venv\Scripts\python -m vase_stress.cli run --model "C:\models\vase.glb" --output outputs/run-012
```

`examples/settings.txt` is the default, relative to the current working directory. Run from the project folder, or supply an absolute `--settings` path. Saved changes are read on each invocation. Existing output files are protected.

## Outputs

| File | Contents |
| --- | --- |
| `prepared.glb` | Reconstructed hollow vase preview, extracted with marching tetrahedra |
| `fea_mesh.glb` | Exact undeformed voxel boundary used for the FEA mesh |
| `stress.vtu` | Tetrahedra, displacement, stress, von Mises stress, reactions, and boundary flags |
| `stress.glb` | Boundary triangles colored from computed VTU cell stresses |
| `summary.json` | Requested settings, effective resolutions, adjustments, numerical maxima, and color anchors |

Prepared files are written before solving. VTU is written before stress GLB. An interrupted or failed run may therefore contain only some outputs.

Recolor an existing numerical result without solving again:

```powershell
.\.venv\Scripts\python -m vase_stress.cli convert --vtu outputs/run-011/stress.vtu --glb outputs/run-011/recolored.glb
```

## Editable settings

All lengths are meters after `model_scale`; forces are newtons, density is kg/m^3, and stresses/modulus are pascals. Comments begin with `#`. Invalid, duplicate, unknown, or nonfinite settings are rejected.

| Setting | Meaning |
| --- | --- |
| `geometry_mode` | `vase` reconstructs a hollow vase; `strict` requires an existing closed material volume |
| `model_scale` | Coordinate multiplier into meters; use `0.001` for a mesh authored in mm |
| `up_axis` | `x`, `y`, or `z`; mouth is toward the positive direction, base at the minimum coordinate |
| `wall_thickness_m` | Assumed inward wall and bottom thickness, not inferred from the GLB |
| `prepared_voxel_size_m` | Requested prepared preview resolution; smaller is finer and uses more memory |
| `voxel_size_m` | Requested FEA voxel pitch; independently controls stress resolution |
| `max_voxels` | Occupied voxel limit for FEA; fine preview has a separate one-million-voxel limit |
| `young_modulus_pa` | Material Young's modulus |
| `poisson_ratio` | Isotropic Poisson ratio, greater than -1 and less than 0.49 |
| `density_kg_m3` | Material density |
| `gravity_m_s2` | Nonnegative gravity magnitude, opposite the up axis |
| `fixed_base_depth_m` | Fully clamp nodes this far above the lowest mesh coordinate |
| `top_load_depth_m` | Select force application nodes this far below the highest coordinate |
| `force_x_n`, `force_y_n`, `force_z_n` | Total top force components, distributed equally over selected nodes |
| `log_range_decades` | Logarithmic color contrast, greater than zero and at most 12; default 3 |

Force signs matter: with Z up, positive `force_z_n` pulls upward; negative pushes downward. Material values and loads in the saved settings are examples, not measured vase properties.

Vase mode retries nearby resolutions automatically while preserving scale, thickness, orientation, loads, and resource limits. Walls need at least two voxel pitches. A fallback can be coarser than requested; read `reconstruction` in `summary.json` for actual pitches. Automatic retries cannot make every arbitrary GLB into a physically meaningful vase.

## Reconstruction and numerical limits

Reconstruction fills the convex hull of each horizontal surface slice, copies the nearest valid slice across missing sections, and hollows inward while retaining a bottom and opening the mouth. This assumes a single vase-like body. Concavities, handles, disconnected pieces, and fine details may be filled, lost, or joined. Preview isosurface extraction rounds voxel corners within approximately one fine grid cell. Inspect both prepared geometry and the FEA mesh before interpreting results.

Strict mode requires consistently oriented inner and outer walls joined at the rim and bottom. An open vase mouth can coexist with a closed material boundary.

The solver uses homogeneous isotropic linear elasticity, small displacements, gravity body loads, a fully clamped base, and six conforming linear tetrahedra per occupied voxel. Resolution changes affect geometry and accuracy. Compare successively finer meshes; no automatic convergence certification is provided. Memory and solve time rise quickly with mesh refinement.

Water pressure, contact, buckling, fracture, nonlinear materials, and shell elements are not implemented. Von Mises stress alone is not a failure criterion for brittle ceramics.

## Stress colors

Blue is zero stress, followed by cyan, green, yellow, and red at the run's maximum. Every face is colored. The zero-safe logarithmic mapping is:

```text
gain = 10**log_range_decades - 1
t = log1p(gain * stress / maximum) / log1p(gain)
```

Larger `log_range_decades` spreads lower stresses across more colors. Colors are relative to each run's maximum, not a failure threshold. Compare Pa values across runs. Exact color anchors and parameters are recorded in the summary. Viewer lighting may affect appearance; stress GLB geometry is undeformed.

## Retained run-011 results

`outputs/run-011/` is intentionally retained in version control, including the three GLBs, VTU, summary, and `settings-used.txt` snapshot. Other run folders and source models remain ignored. The original input GLB is not included.

This run used a 20,000 N positive Z top force, gravity, 20 mm assumed walls, Z up, and 10 mm FEA voxels. The requested 0.1 mm preview fell back to 10 mm. Computed maximum stress was approximately 199.3 MPa and maximum displacement 136.5 mm. That displacement is large relative to the roughly 955 mm model height and exceeds the small-displacement assumption; retain this as an example output, not a validated physical prediction.

`settings-used.txt` records the settings used for this historical run. `examples/settings.txt` is the editable configuration for future runs.

## Development and validation

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

The seven local tests cover parsing, log color anchors, affine element strain, rigid translation, gravity/reaction equilibrium, fixed displacement, open-surface hollow reconstruction, GLB/VTU round trips, and resolution retry invariants. Missing numerical dependencies cause skips; skips do not demonstrate solver correctness.

Code is organized as `config.py` (parsing), `colors.py` (color mapping), `solver.py` (FEA), `pipeline.py` (geometry and conversion), and `cli.py` (commands).
