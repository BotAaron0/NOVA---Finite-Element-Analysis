import importlib.util
import tempfile
import unittest
from pathlib import Path

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "meshio", "trimesh"))


@unittest.skipUnless(AVAILABLE, "Install project dependencies for solver tests")
class PipelineTests(unittest.TestCase):
    def test_gravity_equilibrium_and_roundtrip(self):
        import numpy as np
        import meshio
        import trimesh
        from vase_stress.config import Settings
        from vase_stress.pipeline import run
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "block.glb"
            trimesh.creation.box(extents=[0.04, 0.08, 0.04]).export(model)
            settings = Settings(voxel_size_m=0.02, fixed_base_depth_m=0.001)
            result = run(model, settings, root / "out")
            mesh = meshio.read(root / "out/stress.vtu")
            cells = mesh.get_cells_type("tetra")
            p = mesh.points[cells]
            volume = np.abs(np.linalg.det(p[:,1:] - p[:,:1])).sum() / 6
            reaction = mesh.point_data["reaction_n"].sum(axis=0)
            np.testing.assert_allclose(reaction, [0, volume*settings.density_kg_m3*9.81, 0], atol=1e-8)
            self.assertGreater(result["max_von_mises_pa"], 0)
            fixed = mesh.point_data["boundary_region"] == 1
            np.testing.assert_array_equal(mesh.point_data["displacement_m"][fixed], 0)
            output = trimesh.load_scene(root / "out/stress.glb").to_mesh()
            self.assertGreater(len(output.faces), 0)
            self.assertEqual(len(output.visual.vertex_colors), len(output.vertices))

    def test_affine_strain_and_rigid_translation(self):
        import numpy as np
        from vase_stress.solver import element
        points = np.array([[0.,0,0], [1.,0,0], [0.,1,0], [0.,0,1]])
        stiffness, b = element(points, np.eye(6))
        np.testing.assert_allclose(b @ (points * 0.01).ravel(), [0.01,0.01,0.01,0,0,0])
        np.testing.assert_allclose(stiffness @ np.ones(12), 0, atol=1e-15)

    def test_open_surface_vase_reconstruction(self):
        import numpy as np
        import trimesh
        from vase_stress.config import Settings
        from vase_stress.pipeline import run, prepare_vase
        import meshio
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            box = trimesh.creation.box(extents=[0.12, 0.16, 0.12])
            box.update_faces(box.face_normals[:, 1] < 0.5)
            model = root / "open.glb"
            box.export(model)
            settings = Settings(geometry_mode="vase", wall_thickness_m=0.04,
                                voxel_size_m=0.02, prepared_voxel_size_m=0.01, fixed_base_depth_m=0.001)
            grid, indices = prepare_vase(box, settings)
            occupied = {tuple(i) for i in indices}
            center = np.round(grid.points_to_indices(np.array([[0, 0.08, 0]]))[0]).astype(int)
            self.assertNotIn(tuple(center), occupied)
            center[1] = 0
            self.assertIn(tuple(center), occupied)
            result = run(model, settings, root / "out")
            preview = trimesh.load_scene(root / "out/prepared.glb").to_mesh()
            self.assertTrue(preview.is_volume)
            coarse = trimesh.load_scene(root / "out/fea_mesh.glb").to_mesh()
            self.assertTrue(coarse.is_volume)
            self.assertGreater(len(preview.faces), len(coarse.faces))
            mesh = meshio.read(root / "out/stress.vtu")
            points = mesh.points[mesh.get_cells_type("tetra")]
            volume = np.abs(np.linalg.det(points[:, 1:] - points[:, :1])).sum() / 6
            np.testing.assert_allclose(mesh.point_data["reaction_n"].sum(axis=0),
                                       [0, volume * settings.density_kg_m3 * 9.81, 0], atol=1e-7)
            self.assertGreater(result["max_von_mises_pa"], 0)


    def test_resolution_retry_preserves_physical_inputs(self):
        from unittest.mock import patch
        from vase_stress.config import Settings
        from vase_stress.pipeline import prepare_vase_adaptive
        settings = Settings(wall_thickness_m=0.04, voxel_size_m=0.01)
        metadata = {}
        with patch("vase_stress.pipeline.prepare_vase", side_effect=[
                ValueError("Too many occupied vase voxels"), ("grid", "indices")]) as prepare:
            grid, indices, effective = prepare_vase_adaptive(None, settings, "fea", metadata)
        self.assertEqual(effective.voxel_size_m, 0.0125)
        self.assertEqual(effective.wall_thickness_m, settings.wall_thickness_m)
        self.assertEqual(effective.up_axis, settings.up_axis)
        self.assertEqual(effective.model_scale, settings.model_scale)
        self.assertEqual(effective.max_voxels, settings.max_voxels)
        self.assertEqual(metadata["fea_voxel_size_m"], 0.0125)
        self.assertEqual(prepare.call_count, 2)
