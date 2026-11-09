"""Mesh generation and explicit VTU-to-GLB conversion."""
from pathlib import Path
import json
import numpy as np
import meshio
import trimesh
from .colors import stress_color, color_scale
from .solver import solve


def prepare_vase(mesh, settings):
    """Reconstruct convex horizontal sections and hollow inward in SI units."""
    from scipy.spatial import ConvexHull, QhullError
    from scipy.ndimage import distance_transform_edt
    pitch = settings.voxel_size_m
    if settings.wall_thickness_m < 2 * pitch:
        raise ValueError("Vase wall_thickness_m must be at least twice voxel_size_m")
    estimated = np.prod(np.ceil(mesh.extents / pitch) + 5)
    if estimated > settings.max_voxels * 20:
        raise ValueError("Vase reconstruction grid too large; increase voxel_size_m or max_voxels")
    grid = mesh.voxelized(pitch)
    axis = "xyz".index(settings.up_axis)
    surface = np.moveaxis(grid.matrix, axis, 2)
    outer = np.zeros_like(surface)
    coordinates = np.indices(surface.shape[:2]).reshape(2, -1).T
    valid = []
    for height in range(surface.shape[2]):
        section = np.argwhere(surface[:, :, height])
        if len(section) < 3:
            continue
        try:
            hull = ConvexHull(section)
        except QhullError:
            continue
        inside = np.all(coordinates @ hull.equations[:, :2].T + hull.equations[:, 2] <= 1e-8, axis=1)
        outer[:, :, height] = inside.reshape(surface.shape[:2])
        valid.append(height)
    if not valid:
        raise ValueError("Cannot infer vase cross-sections; check model orientation and resolution")
    for height in range(surface.shape[2]):
        if height not in valid:
            outer[:, :, height] = outer[:, :, min(valid, key=lambda h: abs(h-height))]
    # Outside at the bottom and sides; repeat the top to leave an open mouth.
    padded = np.pad(outer, 1, constant_values=False)
    padded[1:-1, 1:-1, -1] = outer[:, :, -1]
    distance = distance_transform_edt(padded, sampling=pitch)[1:-1, 1:-1, 1:-1]
    cavity = outer & (distance > settings.wall_thickness_m)
    if not cavity[:, :, -1].any():
        raise ValueError("Wall thickness closes the vase mouth; reduce thickness or check up_axis")
    if not cavity.any():
        raise ValueError("Wall thickness leaves no hollow interior")
    material = outer & ~cavity
    indices = np.argwhere(np.moveaxis(material, 2, axis))
    if len(indices) > settings.max_voxels:
        raise ValueError("Too many occupied vase voxels; increase voxel_size_m or max_voxels")
    return grid, indices


def prepare_vase_adaptive(mesh, settings, label, metadata=None):
    """Try bounded resolution adjustments, preserving all physical inputs."""
    from dataclasses import replace
    import sys
    requested = settings.voxel_size_m
    maximum = settings.wall_thickness_m / 2
    pitches = [min(requested * factor, maximum)
               for factor in (1, 1.25, 1.5, 2, 3, 4, 5, 8, 10, 0.75, 0.5)]
    # Reach feasible coarse pitches even when the requested preview is tiny.
    step = min(requested, maximum)
    while step < maximum:
        step = min(step * 2, maximum)
        pitches.append(step)
    pitches.extend([maximum / 2, maximum])
    errors = []
    tried = set()
    for pitch in pitches:
        if pitch in tried:
            continue
        tried.add(pitch)
        candidate = replace(settings, voxel_size_m=pitch)
        try:
            grid, occupied = prepare_vase(mesh, candidate)
        except ValueError as error:
            errors.append(str(error))
            continue
        if metadata is not None:
            metadata[label + "_voxel_size_m"] = pitch
        if pitch != requested:
            message = (f"{label}: adjusted resolution from {requested:g} to {pitch:g} m; "
                       "wall thickness, scale, and up axis unchanged")
            print(message, file=sys.stderr)
            if metadata is not None:
                metadata.setdefault("adjustments", []).append(message)
        return grid, occupied, candidate
    raise ValueError(f"{label}: automatic resolution retries could not produce a hollow vase. "
                     f"Check model_scale, up_axis and wall_thickness_m. "
                     f"Reasons: {'; '.join(dict.fromkeys(errors))}")


def export_prepared(mesh, settings, path, metadata=None):
    """Export fine reconstructed geometry without assembling fine tetrahedra."""
    from dataclasses import replace
    fine = replace(settings, voxel_size_m=min(settings.prepared_voxel_size_m,
                                             settings.voxel_size_m), max_voxels=1000000)
    grid, occupied, fine = prepare_vase_adaptive(mesh, fine, "prepared", metadata)
    # March tetrahedra through the binary field. Intersections at half-values
    # avoid ambiguous diagonal voxel contacts in a cube-face export.
    shape = occupied.max(axis=0) + 3
    material = np.zeros(shape, dtype=bool)
    material[tuple((occupied + 1).T)] = True
    corners = np.array([[0,0,0], [1,0,0], [0,1,0], [1,1,0],
                        [0,0,1], [1,0,1], [0,1,1], [1,1,1]])
    base_shape = np.array(shape) - 1
    count = np.zeros(base_shape, dtype=np.uint8)
    for corner in corners:
        slices = tuple(slice(int(v), int(v+n)) for v, n in zip(corner, base_shape))
        count += material[slices]
    bases = np.argwhere((count > 0) & (count < 8))
    triangles = []
    for pattern in ([0,1,3,7], [0,3,2,7], [0,2,6,7],
                    [0,6,4,7], [0,4,5,7], [0,5,1,7]):
        offsets = corners[pattern]
        positions = bases[:, None, :] + offsets
        bits = material[tuple(positions.transpose(2,0,1))]
        codes = bits @ np.array([1,2,4,8])
        for code in range(1, 15):
            selected = bases[codes == code]
            if not len(selected):
                continue
            inside = [i for i in range(4) if code & (1 << i)]
            outside = [i for i in range(4) if i not in inside]
            if len(inside) == 2:
                a, b = inside
                c, d = outside
                edges = [(a,c), (a,d), (b,d), (b,c)]
                orders = [[0,1,2], [0,2,3]]
            else:
                single, others = (inside, outside) if len(inside) == 1 else (outside, inside)
                edges = [(single[0], i) for i in others]
                orders = [[0,1,2]]
            midpoints = np.array([(offsets[a] + offsets[b])/2 for a,b in edges])
            vertices = selected[:, None, :] + midpoints - 1
            outward = offsets[outside].mean(axis=0) - offsets[inside].mean(axis=0)
            for order in orders:
                triangle = midpoints[order]
                if np.dot(np.cross(triangle[1]-triangle[0], triangle[2]-triangle[0]), outward) < 0:
                    order = order[::-1]
                triangles.append(vertices[:, order, :].reshape(-1, 3))
    vertices = grid.indices_to_points(np.concatenate(triangles))
    surface = trimesh.Trimesh(vertices=vertices,
                              faces=np.arange(len(vertices)).reshape(-1, 3), process=True)
    if not surface.is_volume:
        raise ValueError("Fine vase reconstruction is not a closed volume; adjust resolution or thickness")
    Path(path).write_bytes(surface.export(file_type="glb"))


def tetrahedralize(path, settings, prepared_path=None, metadata=None):
    scene = trimesh.load_scene(path)
    mesh = scene.to_mesh()
    mesh.apply_scale(settings.model_scale)
    if settings.geometry_mode == "vase":
        grid, occupied, settings = prepare_vase_adaptive(mesh, settings, "fea", metadata)
    elif not mesh.is_watertight or not mesh.is_volume:
        raise ValueError("GLB must contain a closed, consistently oriented material volume, including inner vase walls")
    else:
        # Bound dense voxel memory before allocating the grid.
        estimated = np.prod(np.ceil(mesh.extents / settings.voxel_size_m) + 3)
        if estimated > settings.max_voxels * 20:
            raise ValueError("Voxel bounding grid too large; increase voxel_size_m")
        grid = mesh.voxelized(settings.voxel_size_m).fill()
        occupied = grid.sparse_indices
    if len(occupied) > settings.max_voxels:
        raise ValueError("Too many occupied voxels; increase voxel_size_m or max_voxels")
    if not len(occupied):
        raise ValueError("Voxel mesh is empty")
    corners = np.array([[0,0,0], [1,0,0], [0,1,0], [1,1,0], [0,0,1], [1,0,1], [0,1,1], [1,1,1]])
    patterns = np.array([[0,1,3,7], [0,3,2,7], [0,2,6,7], [0,6,4,7], [0,4,5,7], [0,5,1,7]])
    indices = occupied[:, None, :] + corners[None, :, :]
    unique, inverse = np.unique(indices.reshape((-1, 3)), axis=0, return_inverse=True)
    points = grid.indices_to_points(unique) - settings.voxel_size_m / 2
    cells = inverse.reshape((-1, 8))[:, patterns].reshape((-1, 4))
    if prepared_path is not None:
        export_prepared(mesh, settings, prepared_path, metadata)
        faces = np.concatenate([cells[:, order] for order in ([0,2,1], [0,1,3], [0,3,2], [1,2,3])])
        _, inverse, counts = np.unique(np.sort(faces, axis=1), axis=0, return_inverse=True, return_counts=True)
        surface = trimesh.Trimesh(vertices=points, faces=faces[counts[inverse] == 1], process=True)
        surface.fix_normals()
        Path(prepared_path).with_name("fea_mesh.glb").write_bytes(surface.export(file_type="glb"))
    return points, cells


def convert(vtu_path, glb_path, log_range_decades=3.0):
    mesh = meshio.read(vtu_path)
    cells = mesh.get_cells_type("tetra")
    stress = mesh.get_cell_data("von_mises_pa", "tetra")
    if not len(cells) or not np.isfinite(stress).all() or (stress < 0).any():
        raise ValueError("VTU must contain tetrahedra and finite nonnegative von_mises_pa")
    # Orient every face away from its owning tetrahedron; remove shared faces.
    faces, values = [], []
    for cell, value in zip(cells, stress):
        for a, b, c, opposite in ((0,1,2,3), (0,1,3,2), (0,2,3,1), (1,2,3,0)):
            face = cell[[a,b,c]].copy()
            p = mesh.points[face]
            if np.dot(np.cross(p[1]-p[0], p[2]-p[0]), mesh.points[cell[opposite]]-p[0]) > 0:
                face = face[[0,2,1]]
            faces.append(face)
            values.append(value)
    faces = np.array(faces)
    _, inverse, counts = np.unique(np.sort(faces, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = counts[inverse] == 1
    faces = faces[boundary]
    values = np.array(values)[boundary]
    maximum = float(stress.max())
    # Duplicate triangle vertices so cell stress remains crisp and unaveraged.
    vertices = mesh.points[faces].reshape((-1,3))
    colors = np.repeat([stress_color(float(v), maximum, log_range_decades) for v in values], 3, axis=0)
    surface = trimesh.Trimesh(vertices=vertices, faces=np.arange(len(vertices)).reshape((-1,3)), vertex_colors=colors, process=False)
    Path(glb_path).write_bytes(trimesh.Scene(surface).export(file_type="glb"))
    return maximum


def run(glb_path, settings, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ("stress.vtu", "stress.glb", "summary.json", "prepared.glb", "fea_mesh.glb")):
        raise ValueError("Output files already exist; choose a new output directory")
    reconstruction = {}
    points, cells = tetrahedralize(glb_path, settings, output / "prepared.glb" if settings.geometry_mode == "vase" else None, reconstruction)
    displacement, stress, vm, reaction, fixed, loaded = solve(points, cells, settings)
    flags = np.zeros(len(points), dtype=np.int32)
    flags[fixed] = 1
    flags[loaded] = 2
    vtu = output / "stress.vtu"
    meshio.write(vtu, meshio.Mesh(points, [("tetra", cells)], point_data={"displacement_m": displacement, "reaction_n": reaction, "boundary_region": flags}, cell_data={"stress_pa": [stress], "von_mises_pa": [vm]}))
    maximum = convert(vtu, output / "stress.glb", settings.log_range_decades)
    summary = {"reconstruction": reconstruction, "nodes": len(points), "tetrahedra": len(cells), "max_von_mises_pa": maximum, "max_displacement_m": float(np.linalg.norm(displacement, axis=1).max()), "color_scale": color_scale(maximum, settings.log_range_decades), "settings": vars(settings), "geometry": "convex-section hollow vase reconstruction" if settings.geometry_mode == "vase" else "undeformed voxel approximation", "stress_components": ["xx", "yy", "zz", "xy", "yz", "zx"]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary

