"""
Pathogen parameter library.

Each pathogen is a config dict, not a separate model. The spread engine
reads these params and runs the same underlying math, just weighted
differently. Add a new pathogen by adding a new dict here -- no engine
changes needed.

transmission_mode options: "vector", "soil", "airborne", "waterborne"
    - vector: spread rides an insect/animal (e.g. EAB beetles, bark beetles)
    - soil: root contact / soil-borne (e.g. Phytophthora, Armillaria)
    - airborne: wind/rain-dispersed spores (e.g. anthracnose, many foliar fungi)
    - waterborne: moves via water flow, often overlaps with soil mode

max_dispersal_distance_m: distance at which spread probability effectively
    hits zero under normal conditions (not counting human-assisted jumps)

decay_rate: controls how fast probability falls off with distance.
    Higher = spread stays local. Lower = spread reaches further.
    (used as the rate parameter in an exponential decay kernel)

host_susceptibility: dict of species -> 0-1 weight. 1.0 = highly susceptible
    primary host, lower values = secondary/incidental hosts. Species not
    listed are treated as non-hosts (0.0).

environmental_triggers: rough conditions that increase infection likelihood.
    Kept simple for the prototype -- soil_moisture and temp are 0-1 normalized
    "how close to ideal" scores you'll compute from real climate/soil data later.

spatial_weights: how much each raster surface (land_cover, soil, terrain,
    wetness, exposure, moisture, temp) contributes to environmental_match in raster risk mode
    (see spread_engine.compute_risk_raster). Reason these through per
    pathogen's actual transmission_mode -- e.g. soil drainage is a direct
    driver for a soil-borne pathogen but at most a weak proxy for an
    airborne one. Don't copy another pathogen's weights just because the
    surfaces available are the same; see
    docs/feature_contracts/wind_dispersal_and_soil_reweight.md for the
    red_ring_rot/phytophthora case this bit us on.

stress_multiplier: how much a stressed tree's risk gets amplified.
    1.0 = stress has no effect, 2.0 = stressed trees are 2x as vulnerable.

spread_step: parameters for the multi-generation what-if simulation
    (spread_simulation.simulate_spread -- see docs/feature_contracts/
    temporal_spread_per_tree.md). promotion_threshold is the 0-1
    single-step hazard at which a susceptible tree flips to infected and
    becomes a source next generation. It is a scenario knob, not a
    calibrated infection probability -- set per pathogen against its own
    single-step hazard range at its site (see the design note), and meant
    to be swept, not trusted as-is. step_label is display text only.
    Only defined for pathogens wired to a real site; the simulation
    errors clearly if it is missing.
"""

PATHOGENS = {
    "emerald_ash_borer": {
        "display_name": "Emerald Ash Borer",
        "transmission_mode": "vector",
        "max_dispersal_distance_m": 3000,      # natural flight; firewood jumps handled separately
        "decay_rate": 0.0015,
        "host_susceptibility": {
            "oregon_ash": 1.0,
            "green_ash": 1.0,
        },
        # Kept but superseded for the real-site path once spatial_weights
        # (below) is set -- same non-authoritative-but-kept pattern as
        # red_ring_rot's environmental_triggers. Still authoritative for
        # a synthetic run with no spatial_weights surfaces available
        # (e.g. run_prototype.py's generate_environment_grid).
        "environmental_triggers": {
            "temp_weight": 0.6,     # thermal thresholds matter for flight activity
            "moisture_weight": 0.1,
        },
        # Vector/flight-based, not wind/rain-dispersed and not root
        # contact -- a third mechanism distinct from every pathogen that
        # already has a spatial_weights block. land_cover: the beetle
        # still needs an actual tree canopy to land in and colonize,
        # same host/canopy-density role land_cover plays for the other
        # three. wetness: NOT a moisture-triggers-infection claim like
        # phytophthora's use of the same surface -- here it is a
        # host-habitat proxy, since Oregon ash (Fraxinus latifolia) is
        # characteristically a wetland/riparian species in the
        # Willamette Valley, so higher TWI stands in for "more likely
        # ash habitat." Reusing wetness is not the copy-paste mistake
        # docs/feature_contracts/wind_dispersal_and_soil_reweight.md
        # warned against -- it's the same surface doing a different,
        # stated job. exposure/terrain/soil left out: no wind-exposure
        # wound-infection pathway, no root contact. See
        # docs/feature_contracts/emerald_ash_borer_spatial_weights.md.
        "spatial_weights": {
            "land_cover": 0.7,
            "wetness": 0.3,
        },
        "stress_multiplier": 1.3,
    },
    "phytophthora": {
        "display_name": "Phytophthora (root/collar rot)",
        "transmission_mode": "soil",
        "max_dispersal_distance_m": 25,        # root contact + local water movement
        "decay_rate": 0.15,
        "host_susceptibility": {
            "oak": 0.8,
            "oregon_ash": 0.5,
            "maple": 0.6,
            "douglas_fir": 0.4,
        },
        "environmental_triggers": {
            "temp_weight": 0.2,
            "moisture_weight": 0.9,   # saturated/poorly-drained soil is the main driver
        },
        # Nominal only: with a 25 m dispersal cap and no POS host inside
        # that range of the known case (nearest is 84.6 m -- see
        # docs/feature_contracts/site_tree_host_inventory.md), the
        # simulation produces zero spread at this site regardless. Kept
        # so simulate_spread runs for all three real-site pathogens.
        "spread_step": {"promotion_threshold": 0.05, "step_label": "generation"},
        # Root contact + local water movement -- soil drainage is a direct
        # transmission driver here (unlike red_ring_rot, see spatial_weights
        # note above), wetness (topographic wetness index -- see
        # docs/feature_contracts/topographic_wetness_index.md) is a proxy
        # for where water pools, land_cover for host/canopy contact density.
        # wetness replaced the old slope/aspect-based `terrain` entry here:
        # TWI is a direct measure of upslope water accumulation, a better
        # fit for this pathogen's "where water pools" driver than
        # slope/aspect alone. red_ring_rot keeps `terrain` -- wind exposure
        # and water accumulation are different physical quantities, TWI
        # isn't a substitute proxy for the former.
        "spatial_weights": {
            "soil": 0.55,
            "wetness": 0.25,
            "land_cover": 0.2,
        },
        "stress_multiplier": 1.5,
    },
    "anthracnose": {
        "display_name": "Anthracnose",
        "transmission_mode": "airborne",
        "max_dispersal_distance_m": 200,       # wind + rain splash, canopy to canopy
        "decay_rate": 0.02,
        "host_susceptibility": {
            "maple": 0.7,
            "oak": 0.5,
            "sycamore": 0.9,
            "dogwood": 0.9,
        },
        "environmental_triggers": {
            "temp_weight": 0.3,
            "moisture_weight": 0.7,   # cool wet spring conditions
        },
        # Lower than red_ring_rot's: anthracnose's single-step hazards at
        # site_anthracnose top out near 0.086 (low environmental_match
        # there), vs red_ring_rot's 0.21. ~p70 of the nonzero hazard,
        # about 10 first-generation promotions. See the design note.
        "spread_step": {"promotion_threshold": 0.035, "step_label": "generation"},
        # Wind + rain splash, canopy-to-canopy, short range (200m) -- land_cover
        # (host canopy density) is the main driver spread actually needs to move
        # through. wetness (TWI -- see docs/feature_contracts/
        # topographic_wetness_index.md) stands in for the "cool wet spring
        # conditions" driver above, same role phytophthora gives it, just a
        # foliar-humidity proxy here instead of a root-zone-moisture one.
        # exposure/terrain are deliberately left out: unlike red_ring_rot's
        # wound-infection pathway, rain-splash dispersal at this range isn't
        # well explained by ridge/wind-exposure position -- see
        # docs/feature_contracts/wind_dispersal_and_soil_reweight.md's
        # spatial_weights guidance against copying another pathogen's surfaces.
        "spatial_weights": {
            "land_cover": 0.6,
            "wetness": 0.4,
        },
        "stress_multiplier": 1.2,
    },
    "red_ring_rot": {
        "display_name": "Red Ring Rot",
        "transmission_mode": "airborne",       # spores enter through wounds
        "max_dispersal_distance_m": 150,
        "decay_rate": 0.03,
        "host_susceptibility": {
            "douglas_fir": 0.9,
            "western_hemlock": 0.7,
            "pine": 0.6,
        },
        "environmental_triggers": {
            "temp_weight": 0.3,
            "moisture_weight": 0.2,   # reduced from soil-borne-pathogen levels -- see spatial_weights note
        },
        # Airborne/wound-infecting, not soil-borne: land_cover (host
        # presence/stand density) and exposure (topographic position index
        # -- ridge/convex terrain sees more wind, a direction-independent
        # proxy for wind exposure/windthrow risk -- see
        # docs/feature_contracts/wind_exposure_index.md) are the defensible
        # drivers. soil is dropped entirely (that weight belongs on
        # phytophthora instead); moisture kept small as a plausible factor
        # in spore germination at the wound site, not a primary driver.
        # exposure replaced the old slope/aspect-based `terrain` entry here
        # (same 0.35 weight) -- TPI is a better fit for "wind exposure"
        # specifically than generic slope/aspect; phytophthora's wetness
        # swap was the same kind of change for a different physical claim.
        "spatial_weights": {
            "land_cover": 0.45,
            "exposure": 0.35,
            "moisture": 0.15,
            "temp": 0.05,
        },
        "stress_multiplier": 1.4,   # wounds/prior damage are the real entry point
        # ~p70 of the nonzero single-step hazard at data/site (peak
        # 0.21), about 5 first-generation promotions -- enough to seed a
        # front without flipping every host in range at once. See
        # docs/notes/temporal_spread_per_tree.md.
        "spread_step": {"promotion_threshold": 0.06, "step_label": "generation"},
    },
}
