# MERGE — where each file goes

Repo: `WelcomeToYourGalaxy/local-map`, root of `main`.

```
local-map/
├── index.html            ← REPLACE with the index.html in this zip (already patched)
├── trackerdata.json      ← leave; the scripts edit it in place
├── patches/              ← new folder
│   ├── TIER_PATCH_ALL.json          7,508 rows
│   ├── TIER_AMENDMENT_01.json          16 rows, run after the above
│   ├── SKIND_PATCH_PARTIAL.json     1,449 rows
│   └── INTERNATIONAL_ROWS.json      1,817 rows — NOT to be run; the reversal record
└── scripts/              ← new folder
    ├── apply_tier_patch.py
    ├── apply_skind_patch.py
    ├── patch_index_tier_levels.py     (already applied — kept for the record)
    ├── patch_index_facet_aliases.py   (already applied)
    └── patch_index_intl_flag.py       (already applied)
```

## Run, from the repo root, in this order

```bash
python3 scripts/apply_tier_patch.py  trackerdata.json patches/TIER_PATCH_ALL.json      index.html --write
python3 scripts/apply_tier_patch.py  trackerdata.json patches/TIER_AMENDMENT_01.json   index.html --write
python3 scripts/apply_skind_patch.py trackerdata.json patches/SKIND_PATCH_PARTIAL.json index.html --write
```

Drop `--write` for a dry run. All idempotent; re-running reports `applied 0 · already correct N`.

## Expected

```
before        National 7508 · State  807 · County 183 · Municipal  65
tier patch    7508 applied      National 6505 · State 1216 · County 547 · Municipal 295
amendment       16 applied      National 6517 · State 1215 · County 547 · Municipal 284
skind patch   1449 applied      skind pills 1 → 11 of 17 · media pills 2 → 3 of 8
every step    mismatch 0 · outside activeLevels 0 · still untiered 0
```

## index.html — six edits, node --check passes

1. `_TIER_ALIAS` map; `subnational` and near-misses resolve to a real bin instead of vanishing
2. `tagLevels` reads `tier` at depth 0 (map filter)
3. `buildIndexData` reads `tier` at depth 0 (side panel and pill counts), computed inline
4. `_KIND_ALIAS` / `_VOICE_ALIAS` / `_SKIND_ALIAS` / `_RESTYPE_ALIAS` for the four accessors
5. `intl:true` stamped on the `internationalBodies` push
6. `locateEntry` flyTo keys on `e.intl`, not on `e.level==='International'`

Edits 1–3 are the tier fixes the deployed file did not have. 4–6 are new.

## Reversing the international decision

`INTERNATIONAL_ROWS.json` lists the 1,817 rows tiered `national` under the reading that a
country bucket means "resources reachable from this country". Running it through
`apply_tier_patch.py` sets them back to `international`.
