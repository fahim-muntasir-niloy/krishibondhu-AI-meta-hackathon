"""How much of a leaf is diseased, from SAM 3.1's masks: pure geometry, no I/O.

SAM's text prompts often miss a long thin leaf ("leaf" finds nothing on a rice
close-up), so the leaf is found with point prompts instead: `seeds` picks
plant-coloured pixels beside the lesions, SAM returns the object at each one,
and `measure` keeps the mask that holds the most lesion area. Lesions off that
leaf are false positives or belong to other leaves, so they do not count.

A leaf mask can have a hole where tissue is dead, so a lesion is not simply
clipped to it: one counts if it mostly lies on the leaf, or if the leaf mostly
surrounds it (`_on_leaf`), and the hole then counts as leaf.

Masks are Pillow "L" images holding 0 or 255, which keeps numpy out of the
image. Everything here is CPU bound: async code runs it in a thread.
"""

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageFilter

# Below this SAM's point masks were wrong objects in testing; real leaves scored 0.93-0.98.
MIN_LEAF_CONFIDENCE = 0.8
# A leaf this small in the photo gives a percentage that means little: ask for a closer photo.
MIN_LEAF_SHARE = 0.03
_MAX_SEEDS = 3
_RING = 4  # pixels around a lesion checked for being surrounded by leaf
_ON_LEAF = 0.5


@dataclass(frozen=True)
class Instance:
    """One object SAM found: its mask, placed at (left, top) on the photo."""

    left: int
    top: int
    mask: Image.Image
    confidence: float | None = None

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.left + self.mask.width, self.top + self.mask.height


@dataclass(frozen=True)
class Measurement:
    lesion_pct: float
    lesion_px: int
    leaf_px: int
    leaf_confidence: float | None
    leaf: Image.Image
    lesions: Image.Image


def pixels(mask: Image.Image) -> int:
    return mask.histogram()[255]


def union(size: tuple[int, int], instances: list[Instance]) -> Image.Image:
    canvas = Image.new("L", size)
    for inst in instances:
        canvas.paste(255, (inst.left, inst.top), inst.mask)
    return canvas


def _plant_coloured(rgb: tuple[int, int, int]) -> bool:
    """Green or yellowing leaf, not sky, soil, shadow or a blue backdrop."""
    r, g, b = rgb
    return g >= 40 and g > r * 0.9 and g > b * 1.15


def seeds(img: Image.Image, lesions: list[Instance]) -> list[tuple[int, int]]:
    """Points to ask SAM about: the nearest leaf-coloured pixel beside each of the
    largest lesions; with no lesions (a recovered leaf), around the photo's centre."""
    blocked = union(img.size, lesions)
    found: list[tuple[int, int]] = []

    def usable(x: int, y: int) -> bool:
        return 0 <= x < img.width and 0 <= y < img.height and blocked.getpixel((x, y)) == 0 and _plant_coloured(img.getpixel((x, y)))

    ranked = sorted(lesions, key=lambda i: i.mask.width * i.mask.height, reverse=True)
    for inst in ranked:
        if len(found) == _MAX_SEEDS:
            break
        x1, y1, x2, y2 = inst.box
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        step = max(6, min(x2 - x1, y2 - y1) // 3)
        seed = next(
            (
                (x, y)
                for d in range(step, max(img.size) // 3, step)
                for x, y in ((cx, y1 - d), (cx, y2 + d), (x1 - d, cy), (x2 + d, cy))
                if usable(x, y)
            ),
            None,
        )
        # Two lesions side by side would ask about the same place twice.
        if seed and all(abs(seed[0] - a) + abs(seed[1] - b) > step * 3 for a, b in found):
            found.append(seed)
    if not found:
        w, h = img.size
        grid = ((w // 2, h // 2), (w // 3, h // 2), (2 * w // 3, h // 2), (w // 2, h // 3), (w // 2, 2 * h // 3))
        found = [p for p in grid if usable(*p)][:_MAX_SEEDS]
    return found


def _on_leaf(inst: Instance, leaf: Image.Image) -> bool:
    x1, y1, x2, y2 = inst.box
    box = (max(0, x1 - _RING), max(0, y1 - _RING), min(leaf.width, x2 + _RING), min(leaf.height, y2 + _RING))
    region = leaf.crop(box)
    own = Image.new("L", region.size)
    own.paste(inst.mask, (x1 - box[0], y1 - box[1]))
    area = pixels(own)
    if not area:
        return False
    if pixels(ImageChops.multiply(own, region)) >= area * _ON_LEAF:
        return True
    ring = ImageChops.subtract(own.filter(ImageFilter.MaxFilter(2 * _RING + 1)), own)
    return pixels(ring) > 0 and pixels(ImageChops.multiply(ring, region)) >= pixels(ring) * _ON_LEAF


def measure(size: tuple[int, int], lesions: list[Instance], leaves: list[Instance]) -> Measurement | None:
    """Lesion area as a share of the leaf holding the most of it; None when no leaf is reliable."""
    best: Measurement | None = None
    for candidate in leaves:
        if candidate.confidence is not None and candidate.confidence < MIN_LEAF_CONFIDENCE:
            continue
        leaf = union(size, [candidate])
        if pixels(leaf) < size[0] * size[1] * MIN_LEAF_SHARE:
            continue
        kept = union(size, [i for i in lesions if _on_leaf(i, leaf)])
        lesion_px = pixels(kept)
        leaf_px = pixels(ImageChops.lighter(leaf, kept))
        if best is None or (lesion_px, leaf_px) > (best.lesion_px, best.leaf_px):
            best = Measurement(round(100 * lesion_px / leaf_px, 1), lesion_px, leaf_px, candidate.confidence, leaf, kept)
    return best
