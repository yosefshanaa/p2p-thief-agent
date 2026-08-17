# Negotiated locks — files whose own hash is the value on the wire

Each `scent_*.json` here is the pre-series model lock (book rule #23, kit
`locked_model`) for one registered scent physics, written as **canonical bytes with
no trailing newline**. So the file's own digest is exactly the number the handshake
compares:

```bash
sha256sum docs/locks/scent_subtractive_chebyshev_v1.json
# 81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4
```

| file | model | freshest served cell |
|---|---|---|
| `scent_book_v1.json` | `book_v1` — figure-4 kernel, `τ × 0.9`, served pre-emission | 0.81 at the cell just left, 0.558 at the current one |
| `scent_registered_v3.json` | `registered_v3` — same kernel, no rounding, served post-emission | 0.90 |
| `scent_subtractive_chebyshev_v1.json` | `subtractive_chebyshev_v1` — flat Chebyshev rings, `v − 0.1` | 0.80 |

They exist because "adopt the document verbatim" needs an artifact to adopt.
Describing the same physics in your own vocabulary hashes differently, and
`check_compatibility` treats a scent-hash difference as a **refusal to play**
(`negotiation.py:53`), not a warning — so an opponent who intends to run our
physics has to end up on these bytes, not on an equivalent description of them.

An opponent can verify a lock with `sha256sum` alone, without running any of our
code. Regenerate with:

```bash
PYTHONPATH=src .venv/bin/python -c "
from pathlib import Path
from p2p_pursuit.domain.crypto import canonical_bytes
from p2p_pursuit.domain.scent import MODELS, scent_model_document
for m in MODELS:
    Path(f'docs/locks/scent_{m}.json').write_bytes(canonical_bytes(scent_model_document(m)))"
```

The constitution is the other half of the same handshake and works differently:
`config_sha256` hashes the **canonical form of the parsed** `config/<role>/game.json`,
so formatting and key order are irrelevant there — see `INTEROP_GUIDE.md` §4.
