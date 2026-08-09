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
    moisture, temp) contributes to environmental_match in raster risk mode
    (see spread_engine.compute_risk_raster). Reason these through per
    pathogen's actual transmission_mode -- e.g. soil drainage is a direct
    driver for a soil-borne pathogen but at most a weak proxy for an
    airborne one. Don't copy another pathogen's weights just because the
    surfaces available are the same; see
    docs/feature_contracts/wind_dispersal_and_soil_reweight.md for the
    red_ring_rot/phytophthora case this bit us on.

stress_multiplier: how much a stressed tree's risk gets amplified.
    1.0 = stress has no effect, 2.0 = stressed trees are 2x as vulnerable.
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
        "environmental_triggers": {
            "temp_weight": 0.6,     # thermal thresholds matter for flight activity
            "moisture_weight": 0.1,
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
        # Root contact + local water movement -- soil drainage is a direct
        # transmission driver here (unlike red_ring_rot, see spatial_weights
        # note above), terrain is a proxy for where water pools, land_cover
        # for host/canopy contact density.
        "spatial_weights": {
            "soil": 0.55,
            "terrain": 0.25,
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
        # presence/stand density) and terrain (slope/aspect, our current
        # proxy for wind exposure -- see spatial_inputs.score_terrain) are
        # the defensible drivers. soil is dropped entirely (that weight
        # belongs on phytophthora instead); moisture kept small as a
        # plausible factor in spore germination at the wound site, not a
        # primary driver.
        "spatial_weights": {
            "land_cover": 0.45,
            "terrain": 0.35,
            "moisture": 0.15,
            "temp": 0.05,
        },
        "stress_multiplier": 1.4,   # wounds/prior damage are the real entry point
    },
}
