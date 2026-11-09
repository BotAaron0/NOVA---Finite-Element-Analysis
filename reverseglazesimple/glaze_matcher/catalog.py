"""Extract spatially labeled fired-result photos from Mayco combination charts."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from .config import CODE, codes
from .colors import describe

SCHEMA = 2


def groups(values, tolerance=8):
    output = []
    for value in sorted(values):
        if not output or abs(value - output[-1]) > tolerance:
            output.append(value)
    return output


def find_grid(page):
    squares = [r for r in page.rects if 180/792*page.height < r["top"] < 710/792*page.height
               and 35/612*page.width < r["width"] < 85/612*page.width
               and 0.85 < r["width"] / max(r["height"], 1) < 1.15]
    xs = groups([r["x0"] for r in squares])
    ys = groups([r["top"] for r in squares])
    if len(xs) not in (3, 4) or len(ys) not in (3, 4):
        raise ValueError(f"Unrecognized grid: {len(xs)} columns, {len(ys)} rows")
    cells = []
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            matches = [r for r in squares if abs(r["x0"]-x) < 8 and abs(r["top"]-y) < 8]
            if not matches:
                raise ValueError("Incomplete swatch grid; manual review required")
            cells.append((row, col, matches[0]))
    return len(xs), len(ys), cells, ys


def page_conditions(text):
    cones = set(re.findall(r"\bcone\s+(0?\d{1,2})\b", text, re.I))
    if len(cones) != 1:
        raise ValueError("Missing or ambiguous firing cone")
    atmosphere = "reduction" if re.search(r"\breduction\b", text, re.I) else (
        "oxidation" if re.search(r"\boxidation\b", text, re.I) else "unknown")
    base_coats = re.search(r"\((\d+)\)\s+layers?\s+of\s+base", text, re.I)
    top_coats = re.search(r"\((\d+)\)\s+layers?\s+of\s+top", text, re.I)
    if not top_coats:
        top_coats = re.search(r"apply\s+\w+\s+\((\d+)\)\s+layers?", text, re.I)
    body = "white_stoneware" if re.search(r"white\s+stoneware", text, re.I) else "unknown"
    return {"cone": next(iter(cones)), "atmosphere": atmosphere, "clay_body": body,
            "base_coats": int(base_coats[1]) if base_coats else None,
            "top_coats": int(top_coats[1]) if top_coats else None,
            "application_method": "brush" if "brushing" in text.lower() else "unknown",
            "dry_between_coats": "yes" if "dry between coats" in text.lower() else "unknown"}


def cell_recipe(text, conditions):
    relation = re.search(r"\b(over|under)\b", text, re.I)
    if not relation:
        raise ValueError("Missing over/under layer label")
    before, after = text[:relation.start()], text[relation.end():]
    first = list(CODE.finditer(before))
    second = list(CODE.finditer(after))
    if len(first) != 1 or not second:
        raise ValueError("Ambiguous glaze product labels")
    # EG labels belong to the underlying engobe, never an inferred top glaze.
    if second[0].group(1).upper() == "EG":
        raise ValueError("Missing second glaze product")
    name_a = before[first[0].end():].strip()
    tail = after[second[0].end():]
    substrate = re.split(r"\bon\b", tail, maxsplit=1, flags=re.I)
    name_b = substrate[0].strip()
    if CODE.search(name_b):
        raise ValueError("More than two glaze layers; manual review required")
    a = {"code": codes(first[0][0])[0], "name": " ".join(name_a.split())}
    b = {"code": codes(second[0][0])[0], "name": " ".join(name_b.split())}
    top, base = (a, b) if relation[1].lower() == "over" else (b, a)
    if relation[1].lower() == "under" and conditions["base_coats"] != conditions["top_coats"]:
        raise ValueError("Under-order coat assignment is ambiguous")
    substrate_text = substrate[1].strip() if len(substrate) > 1 else ""
    engobes = [c for c in codes(substrate_text) if c.startswith("EG-")]
    if substrate_text and not engobes and not re.search(r"plain\s+white\s+stoneware", substrate_text, re.I):
        raise ValueError("Unrecognized substrate label")
    return {"base": base, "top": top, "label_relation": relation[1].lower(),
            "engobe": engobes[0] if engobes else "none",
            "substrate_text": substrate_text or conditions["clay_body"]}


def build_catalog(archive_path, output, progress=print):
    import pdfplumber
    import pypdfium2 as pdfium
    archive_path, output = Path(archive_path), Path(output)
    with archive_path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = output / "catalog.json"
    if manifest.exists():
        cached = json.loads(manifest.read_text(encoding="utf-8"))
        if cached.get("archive_sha256") == fingerprint and cached.get("schema") == SCHEMA:
            if all((output / r["photo"]).is_file() and (output / r["context_image"]).is_file()
                   for r in cached["records"]):
                progress(f"Using cached catalog: {len(cached['records'])} documented results")
                return cached
        raise ValueError("Catalog exists with different data or missing images; choose a fresh --catalog folder")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Catalog output is not empty; choose a fresh --catalog folder")
    (output / "photos").mkdir(parents=True, exist_ok=True)
    records, skipped, total_pages = [], [], 0
    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(n for n in archive.namelist() if n.lower().endswith(".pdf"))
        if not names:
            raise ValueError("No PDFs found in combination_zip_path")
        for document_number, name in enumerate(names, 1):
            data = archive.read(name)
            try:
                with pdfplumber.open(io.BytesIO(data)) as pdf, pdfium.PdfDocument(data) as rendered:
                    for page_number, page in enumerate(pdf.pages, 1):
                        total_pages += 1
                        try:
                            text = page.extract_text() or ""
                            conditions = page_conditions(text)
                            columns, rows, cells, row_tops = find_grid(page)
                        except ValueError as error:
                            skipped.append({"source": name, "page": page_number, "reason": str(error)})
                            continue
                        scale = 1.5
                        image = rendered[page_number-1].render(scale=scale).to_pil().convert("RGB")
                        left, right = page.width*18/612, page.width*594/612
                        width = (right-left)/columns
                        margin = page.height * (12 if row_tops[0] > page.height*210/792 else 6) / 792
                        step = sorted(b-a for a,b in zip(row_tops, row_tops[1:]))[len(row_tops)//2-1]
                        for row, col, square in cells:
                            x0, y0 = left+col*width, row_tops[row]-margin
                            x1 = x0+width
                            y1 = min(page.height*.945, (row_tops[row+1] if row+1 < rows else row_tops[row]+step)-margin)
                            try:
                                label_box = (max(x0, square["x0"]-3), y0, x1, y1)
                                label = page.crop(label_box).extract_text() or ""
                                footer_layout = False
                                try:
                                    recipe = cell_recipe(label, conditions)
                                except ValueError:
                                    # Older sheets put complete layer labels below the vase.
                                    footer_layout = True
                                    label = page.crop((x0, y0+(y1-y0)*.76, x1, y1)).extract_text() or ""
                                    recipe = cell_recipe(label, conditions)
                                photo_end = y0+(y1-y0)*.78 if footer_layout else y1-3
                                photo_box = (x0+2, y0+3, square["x0"]-4, photo_end)
                                if photo_box[2] - photo_box[0] < 35:
                                    raise ValueError("Vase photo region too narrow")
                                crop = image.crop(tuple(round(v*scale) for v in photo_box))
                                descriptor = describe(crop, vase=True)
                            except ValueError as error:
                                skipped.append({"source": name, "page": page_number,
                                                "row": row+1, "column": col+1, "reason": str(error)})
                                continue
                            identifier = hashlib.sha256(f"{name}:{page_number}:{row}:{col}".encode()).hexdigest()[:16]
                            photo_path = f"photos/{identifier}.jpg"
                            context_path = f"photos/{identifier}-context.jpg"
                            crop.save(output / photo_path, quality=90)
                            image.crop(tuple(round(v*scale) for v in (x0,y0,x1,y1))).save(output / context_path, quality=90)
                            records.append({"id": identifier, "source_pdf": name, "page": page_number,
                                            "row": row+1, "column": col+1, "label_text": label,
                                            **conditions, **recipe, "photo": photo_path,
                                            "context_image": context_path, "descriptor": descriptor,
                                            "sampling": "central vase body: 25-75% width, 18-68% height"})
                        page.close()
            except Exception as error:
                # Keep an auditable failure, never silently substitute guessed recipes.
                skipped.append({"source": name, "reason": f"{type(error).__name__}: {error}"})
            if document_number % 10 == 0 or document_number == len(names):
                progress(f"Indexed {document_number}/{len(names)} PDFs: {len(records)} results, {len(skipped)} review items")
    result = {"schema": SCHEMA, "archive_sha256": fingerprint, "source_archive": str(archive_path),
              "pdf_count": len(names), "page_count": total_pages, "records": records, "skipped": skipped,
              "limitations": ["Photo color is not a calibrated fired-color measurement.",
                              "Unknown atmosphere is not assumed to be oxidation.",
                              "Only recognized, spatially labeled chart cells are indexed."]}
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not records:
        raise ValueError(f"No usable combination cells found; inspect {manifest}")
    return result
