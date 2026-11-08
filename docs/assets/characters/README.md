# Workflow characters

These two transparent PNGs were generated with the built-in imagegen tool using the TuneTune hero as a style reference. The workflow SVGs embed the optimized PNGs so they also render in image contexts that cannot load external resources; all text, cards, lines and arrowheads are SVG code.

Shared prompt: “A single isolated character cutout for a small README SVG diagram, transparent background with real alpha; simple cream fill, thick charcoal outlines, cobalt blue accent; playful minimal cartoon, readable at 72 pixels; no text, scenery or extra objects.”

Subjects:

- `user.png`: a friendly human bust, short dark hair, dot eyes, cream shirt and blue collar; clearly distinct from the ghost.
- `ghost.png`: the TuneTune hero's hooded ghost, simplified, preserving its tongue-out smile, drawstrings and wavy bottom, with a finger-gun hand pointing right (thumb up, index extended, remaining fingers curled) and cobalt blue biubiu marks, matching the hero gesture.

The generated files were resized to fit 256 × 256 pixels with alpha preserved. When replacing a character, update its embedded PNG in both `workflow-en.svg` and `workflow-zh.svg`.

Regenerate both self-contained workflow SVGs with `python3 scripts/build-workflow.py`. The generator reads these PNGs directly; no temporary base64 files are needed.

Ghost replacement prompt (built-in imagegen, hero as identity/style reference): “An isolated transparent TuneTune ghost matching the hero: cream hood, thick handmade charcoal outlines, mischievous eyes, tongue-out grin, black drawstrings and wavy bottom; a clear right-pointing finger-gun gesture with thumb upright, index extended and remaining fingers curled, plus cobalt blue biubiu marks; readable at 88 pixels, no lettering or scenery, real alpha.”
