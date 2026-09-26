"""
Crosswalk from the City of Eugene POS tree layer's `Tree_speci` strings to
the engine's host-species keys (the keys used in
pathogens.PATHOGENS[...]["host_susceptibility"]).

`Tree_speci` holds "Scientific name - common name" in one field, e.g.
"Pseudotsuga menziesii - Douglas fir". 306 distinct values in the source.

Match order (first hit wins):
1. exact `Tree_speci` string,
2. "Genus species" (first two scientific-name tokens),
3. leading genus token.

Anything with no hit -- including "Unknown" and blank -- returns None and
the caller drops that tree as a non-host (susceptibility 0.0). See
docs/notes/site_tree_host_inventory.md for why the mapping is genus-level
for most genera but species-level for Fraxinus.
"""

# Genus -> engine host key. One engine key per genus; the engine's
# host_susceptibility does not distinguish species within these genera.
_GENUS_TO_ENGINE = {
    "Acer": "maple",
    "Quercus": "oak",
    "Pseudotsuga": "douglas_fir",
    "Cornus": "dogwood",
    "Platanus": "sycamore",
    "Pinus": "pine",
    "Tsuga": "western_hemlock",
}

# "Genus species" -> engine host key, checked before the genus fallback.
# Only the two ash species with a defensible engine key are listed;
# other Fraxinus (ornamental cultivars, "Fraxinus spp") stay unmapped.
_SPECIES_TO_ENGINE = {
    "Fraxinus latifolia": "oregon_ash",
    "Fraxinus pennsylvanica": "green_ash",
}


def _scientific_name(raw_tree_speci):
    """The part before ' - ' (or the whole string if there is no dash),
    handling the stray cp1252 em dash (0x97) seen in some common names."""
    text = raw_tree_speci.replace("\x97", "-")
    return text.split(" - ", 1)[0].strip()


def to_engine_species(raw_tree_speci):
    """Returns an engine host key, or None if this is not a modeled host."""
    if not raw_tree_speci:
        return None

    if raw_tree_speci in _SPECIES_TO_ENGINE:
        return _SPECIES_TO_ENGINE[raw_tree_speci]

    scientific = _scientific_name(raw_tree_speci)
    if not scientific or scientific == "Unknown":
        return None

    tokens = scientific.split()
    genus_species = " ".join(tokens[:2])
    if genus_species in _SPECIES_TO_ENGINE:
        return _SPECIES_TO_ENGINE[genus_species]

    return _GENUS_TO_ENGINE.get(tokens[0])
