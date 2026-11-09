"""Photo color descriptors and CIE76 distances in D65 CIELAB."""
import numpy as np


def rgb_to_lab(rgb):
    rgb = np.asarray(rgb, dtype=float) / 255
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124564, 0.3575761, 0.1804375],
                             [0.2126729, 0.7151522, 0.0721750],
                             [0.0193339, 0.1191920, 0.9503041]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def describe(image, vase=False):
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image).convert("RGB")
    if vase:
        # Central body, away from background, rim, unglazed foot, and shadows.
        w, h = image.size
        image = image.crop((int(w*.25), int(h*.18), int(w*.75), int(h*.68)))
    pixels = np.asarray(image.resize((48, 48))).reshape(-1, 3)
    lab = rgb_to_lab(pixels)
    # Deterministic farthest-point seeds, then compact weighted palette.
    centers = [lab[np.argmin(np.linalg.norm(lab - lab.mean(axis=0), axis=1))]]
    for _ in range(4):
        distances = np.min(np.linalg.norm(lab[:, None] - np.array(centers), axis=2), axis=1)
        centers.append(lab[np.argmax(distances)])
    centers = np.array(centers)
    for _ in range(12):
        labels = np.argmin(np.linalg.norm(lab[:, None] - centers, axis=2), axis=1)
        updated = np.array([lab[labels == i].mean(axis=0) if np.any(labels == i) else centers[i]
                            for i in range(len(centers))])
        if np.allclose(updated, centers, atol=0.01):
            break
        centers = updated
    labels = np.argmin(np.linalg.norm(lab[:, None] - centers, axis=2), axis=1)
    palette = []
    for i in range(len(centers)):
        selection = labels == i
        if not selection.any():
            continue
        rgb = np.round(pixels[selection].mean(axis=0)).astype(int).tolist()
        palette.append({"lab": centers[i].tolist(), "rgb": rgb,
                        "hex": "#" + "".join(f"{c:02X}" for c in rgb),
                        "weight": float(selection.mean())})
    return {"mean_lab": lab.mean(axis=0).tolist(),
            "palette": sorted(palette, key=lambda item: -item["weight"])}


def color_distance(target, candidate, priority):
    if priority == "overall_color":
        return float(np.linalg.norm(np.array(target["mean_lab"]) - candidate["mean_lab"]))
    if priority == "dominant_color":
        return float(np.linalg.norm(np.array(target["palette"][0]["lab"]) - candidate["palette"][0]["lab"]))
    a, b = target["palette"], candidate["palette"]
    distances = np.linalg.norm(np.array([x["lab"] for x in a])[:, None] -
                               np.array([x["lab"] for x in b]), axis=2)
    # Symmetric nearest-palette distance penalizes unwanted secondary colors.
    return float((np.dot(distances.min(axis=1), [x["weight"] for x in a]) +
                  np.dot(distances.min(axis=0), [x["weight"] for x in b])) / 2)
