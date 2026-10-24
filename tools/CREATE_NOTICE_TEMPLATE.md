# Create a Notices template

`create_notice_template.py` creates a compatible frame/mask pair from an existing
local screenshot. It never starts the bot, contacts ADB, clicks the game, edits
settings or modifies the source screenshot. It uses the project's existing
Pillow, NumPy and OpenCV dependencies. Run commands from the project directory.

## Quick start: a completely new frame

```powershell
python -B tools/create_notice_template.py "C:\Screenshots\notice.png" --name special_notice --interactive
```

1. Drag around the **complete notice including its icon**. Press Enter to accept.
2. Select at least two separate **fixed frame or background strips**. Press Enter
   after each rectangle, then Esc to finish. Good choices are a top border, a
   bottom border, a side border and a small background strip away from text.
3. Never include text, roll numbers, level numbers, item icons or moving scenery
   in the selected strips. These selections are copied exactly; the tool cannot
   determine whether selected pixels contain identifying information.
4. Inspect `temp/notice_templates/special_notice_preview.png`. The left half shows
   the sanitized reference, the right half highlights every retained pixel.
5. Copy `special_notice_frame.png` and `special_notice_frame_mask.png` together
   into `images/Notices/`. The preview is optional and is not a detector input.

All pixels outside the selected strips are blacked out. No original crop,
screenshot metadata or identifying text outside the selections is saved.
The GUI is local and requires a desktop OpenCV installation, not a headless one.
Esc during initial crop selection cancels without publishing a pair.

## Fully automatic mode for the two existing frame styles

```powershell
python -B tools/create_notice_template.py "C:\Screenshots\notice.png" --name level_variant --preset level
python -B tools/create_notice_template.py "C:\Screenshots\shard.png" --name shard_variant --preset shard
```

These presets reuse the current crop and mask at their original positions in
**900 x 1600** screenshots. They are for the same frame geometry only. A new
frame style needs interactive selection or explicit coordinates. Selecting a
preset does not automatically discover a new border or guarantee a valid frame.

## Repeatable coordinate-based generation

Coordinates are `(x1, y1, x2, y2)` with exclusive right/bottom edges. `--crop`
uses full screenshot coordinates. Each `--region` uses coordinates **relative
to the crop**, with a separate nonzero mask label assigned automatically.
Regions must not overlap.

Example matching the existing level frame geometry:

```powershell
python -B tools/create_notice_template.py "C:\Screenshots\notice.png" --name level_variant --crop 0 772 372 895 --region 4 0 290 1 --region 4 121 290 123 --region 293 8 297 115 --region 4 2 290 8
```

The reference retains the exact original colors; the mask retains independent
region labels. Do not convert the mask to a binary image or rescale either file.

## Validate before installing

Every run checks the source screenshot against the generated pair. Add independent
examples to check varying text and false positives:

```powershell
python -B tools/create_notice_template.py "C:\Screenshots\notice.png" --name special_notice --interactive --search-roi 0 740 390 925 --positive "C:\Screenshots\another_notice.png" --negative "C:\Screenshots\no_notice.png"
```

Repeat `--positive` and `--negative` as needed. All validation uses only the newly
generated frame, not other installed variants. Search ROI defaults to the selected
crop; use the actual configured search ROI for a realistic false-positive check.
It must contain the complete crop and fit in every validation screenshot.
Validation failure publishes no output files. A source match near 1.0 is expected
because the reference came from that image; it does not prove general reliability.
The threshold defaults to 0.96 and can be set with `--threshold`.

The default output is a staging directory. `--output-dir PATH` chooses a different
staging location. To install directly, add `--install` instead; this writes into
the project's `images/Notices/` and activates the new variant on the next scan.
Existing outputs are never overwritten; choose a new name to retry.

The default `NOTICES_TEMPLATE_GLOB` finds `*_frame.png` automatically. Both files
are required. Ensure WebUI `NOTICES_DETECT_ROI` contains the entire new frame;
changing settings requires a process restart. Adding files alone does not.
Use **Test detection** with and without notices before enabling dismiss actions.

## Limitations and privacy

A single screenshot cannot establish which pixels remain constant across all
messages. The tool automates cropping, mask labels, sanitization, naming and
validation, but new frame selections still need review. Unknown resolutions,
scaling and animations require suitable references and validation images.

The original screenshot remains at its original path. Only selected pixels are
copied into output PNGs. Inspect the preview before committing: if you selected
text accidentally, that text remains. Keep private screenshots outside Git.
The tool does not erase source files or rewrite Git history.
