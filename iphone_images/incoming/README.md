# Incoming slides (orphan pairing)

Drop **slide-only** JPEGs here before they are merged into the main dataset.

## Filename format

```text
slide_<tissue>_<stain>_<genotype>_<workorder>.jpeg
```

**Examples**

- `slide_lung_MT_WT1_WO7842.jpeg`
- `slide_esophagus_HE_TWKO4_WO7842.jpg`

| Field | Values |
|-------|--------|
| tissue | `lung` (one bean-shaped lobe), `lungs` (fragmented), or `esophagus` |
| stain | `HE`, `MT`, `PAS`, `PSRFG`, `SMA` |
| genotype | Same token as on the block (`WT1`, `TWKO4`, … — avoid bare `WT` if multiple blocks exist) |
| work order | `WO7842` or `7842` |

Pairing uses **tissue token + genotype** (`lung` vs `lungs` are different keys).

## Commands

From the repo root:

```powershell
# Preview matches (no file changes)
python code/pair_orphan_slides.py

# Create new set_NN files in iphone_images/ (copy block + move slide)
python code/pair_orphan_slides.py --apply
```

Each matched slide becomes a **new set number** with:

- Your new slide → `set_XX_slide_...`
- A **copy** of the matched `block_silhouette` → `set_XX_block_silhouette_...` (stain updated to the slide’s stain)
- Optional copy of `block_barcode` if that set had one

Processed slides are moved out of this folder into `iphone_images/`.
