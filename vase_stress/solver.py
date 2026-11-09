"""Small-strain isotropic 3D elasticity with constant-strain tetrahedra."""
import warnings
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve
from scipy.sparse.csgraph import connected_components


def element(points, elasticity):
    matrix = np.column_stack((np.ones(4), points))
    volume = abs(np.linalg.det(matrix)) / 6
    if volume <= 0:
        raise ValueError("Degenerate tetrahedron")
    gradients = np.linalg.inv(matrix)[1:, :].T
    b = np.zeros((6, 12))
    for i, (x, y, z) in enumerate(gradients):
        j = i * 3
        b[:, j:j + 3] = [[x, 0, 0], [0, y, 0], [0, 0, z], [y, x, 0], [0, z, y], [z, 0, x]]
    return volume * b.T @ elasticity @ b, b


def solve(points, cells, settings):
    e, nu = settings.young_modulus_pa, settings.poisson_ratio
    mu = e / (2 * (1 + nu))
    lam = e * nu / ((1 + nu) * (1 - 2 * nu))
    elasticity = np.zeros((6, 6))
    elasticity[:3, :3] = lam
    elasticity[np.arange(3), np.arange(3)] += 2 * mu
    elasticity[3:, 3:] = np.eye(3) * mu
    axis = "xyz".index(settings.up_axis)
    height = points[:, axis]
    fixed = np.flatnonzero(height <= height.min() + settings.fixed_base_depth_m + 1e-12)
    loaded = np.flatnonzero(height >= height.max() - settings.top_load_depth_m - 1e-12)
    has_top_load = any((settings.force_x_n, settings.force_y_n, settings.force_z_n))
    if has_top_load and np.intersect1d(fixed, loaded).size:
        raise ValueError("Support and load regions overlap; reduce selection depths")
    if np.linalg.matrix_rank(points[fixed] - points[fixed].mean(axis=0)) < 2:
        raise ValueError("Support must contain at least three non-collinear nodes")
    edges = np.concatenate([cells[:, [0, i]] for i in (1, 2, 3)])
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(points), len(points)))
    _, labels = connected_components(graph, directed=False)
    if not set(labels).issubset(set(labels[fixed])):
        raise ValueError("Every disconnected component must have a fixed support")
    for label in set(labels):
        support = points[fixed[labels[fixed] == label]]
        if np.linalg.matrix_rank(support - support.mean(axis=0)) < 2:
            raise ValueError("Each component needs three non-collinear fixed nodes")
    rows, cols, data, operators = [], [], [], []
    force = np.zeros((len(points), 3))
    for cell in cells:
        stiffness, b = element(points[cell], elasticity)
        dofs = (cell[:, None] * 3 + np.arange(3)).ravel()
        rows.extend(np.repeat(dofs, 12))
        cols.extend(np.tile(dofs, 12))
        data.extend(stiffness.ravel())
        operators.append(b)
        volume = abs(np.linalg.det(np.column_stack((np.ones(4), points[cell])))) / 6
        force[cell, axis] -= settings.density_kg_m3 * settings.gravity_m_s2 * volume / 4
    stiffness = coo_matrix((data, (rows, cols)), shape=(len(points) * 3,) * 2).tocsr()
    if has_top_load:
        force[loaded] += np.array([settings.force_x_n, settings.force_y_n, settings.force_z_n]) / len(loaded)
    else:
        loaded = np.array([], dtype=int)
    fixed_dofs = (fixed[:, None] * 3 + np.arange(3)).ravel()
    free = np.setdiff1d(np.arange(len(points) * 3), fixed_dofs)
    displacement = np.zeros(len(points) * 3)
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        displacement[free] = spsolve(stiffness[free][:, free], force.ravel()[free])
    if not np.isfinite(displacement).all():
        raise ValueError("Singular system; check supports and mesh connectivity")
    residual = stiffness @ displacement - force.ravel()
    if np.linalg.norm(residual[free]) > max(np.linalg.norm(force), 1) * 1e-6:
        raise ValueError("Solver failed force equilibrium check")
    displacement = displacement.reshape((-1, 3))
    stress = np.array([elasticity @ b @ displacement[cell].ravel() for cell, b in zip(cells, operators)])
    x, y, z, xy, yz, zx = stress.T
    von_mises = np.sqrt(0.5 * ((x-y)**2 + (y-z)**2 + (z-x)**2) + 3 * (xy**2 + yz**2 + zx**2))
    return displacement, stress, von_mises, residual.reshape((-1, 3)), fixed, loaded
