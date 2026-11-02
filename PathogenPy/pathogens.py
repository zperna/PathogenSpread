"""
Pathogen parameter library.

Each pathogen is a config dict, not a separate model. The spread engine
reads these params and runs the same underlying math. Only the weights
differ. To add a pathogen, add a new dict here. No engine changes are
needed.

transmission_mode options: "vector", "soil", "airborne", "waterborne"
    - vector: spread by an insect or animal (e.g. EAB beetles, bark beetles)
    - soil: root contact or soil-borne (e.g. Phytophthora, Armillaria)
    - airborne: wind/rain-dispersed spores (e.g. anthracnose, many foliar fungi)
    - waterborne: moves via water flow, often overlaps with soil mode

max_dispersal_distance_m: distance at which spread probability is
    effectively zero under normal conditions. Human-assisted jumps are not
    counted.

decay_rate: controls how fast probability falls off with distance. A
    higher value keeps spread local. A lower value lets spread reach
    farther. It is the rate parameter of an exponential decay kernel.

host_susceptibility: dict of species to 0-1 weight. A value of 1.0 means
    a highly susceptible primary host. Lower values mean secondary or
    incidental hosts. Species not listed are treated as non-hosts (0.0).

environmental_triggers: rough conditions that increase infection
    likelihood. Kept simple for the prototype. soil_moisture and temp are
    0-1 normalized "how close to ideal" scores. You will compute them from
    real climate or soil data later.

spatial_weights: how much each raster surface (land_cover, soil, terrain,
    wetness, exposure, moisture, temp) contributes to environmental_match
    in raster risk mode (see spread_engine.compute_risk_raster). Set each
    pathogen's weights from its actual transmission_mode. For example, soil
    drainage is a direct driver for a soil-borne pathogen, but it is at
    most a weak proxy for an airborne one. Do not copy another pathogen's
    weights just because the same surfaces are available. See
    docs/feature_contracts/wind_dispersal_and_soil_reweight.md for the
    red_ring_rot/phytophthora case where this mistake was made.

stress_multiplier: how much a stressed tree's risk is amplified. A value
    of 1.0 means stress has no effect. A value of 2.0 means stressed trees
    are 2x as vulnerable.

spread_step: parameters for the multi-generation what-if simulation
    (spread_simulation.simulate_spread). See docs/feature_contracts/
    temporal_spread_per_tree.md.
    promotion_threshold is the 0-1 single-step hazard. A susceptible tree
    becomes infected when its hazard reaches this value. It then acts as a
    source in the next generation. This is a scenario setting. It is not a
    calibrated infection probability. Set it for each pathogen against that
    pathogen's own single-step hazard range at its site (see the design
    note). Sweep this value. Do not trust it as-is.
    step_label is display text only.
    Only defined for pathogens wired to a real site. The simulation raises
    a clear error if it is missing.
"""

PATHOGENS = {
    "emerald_ash_borer": {
        "display_name": "Emerald Ash Borer",
        "transmission_mode": "vector",
        "max_dispersal_distance_m": 3000,      # natural flight. Firewood jumps: separate.
        "decay_rate": 0.0015,
        "host_susceptibility": {
            "oregon_ash": 1.0,
            "green_ash": 1.0,
        },
        # This block is kept. Once spatial_weights (below) is set, it no
        # longer applies to the real-site path. It follows the same
        # non-authoritative pattern as red_ring_rot's environmental_triggers.
        # It stays authoritative for a synthetic run with no spatial_weights
        # surfaces available (for example, run_prototype.py's
        # generate_environment_grid).
        "environmental_triggers": {
            "temp_weight": 0.6,     # thermal thresholds matter for flight activity
            "moisture_weight": 0.1,
        },
        # This is a flight-based vector. It is not wind or rain dispersed,
        # and it does not spread by root contact. It is a third mechanism.
        # No other pathogen with a spatial_weights block works this way.
        # land_cover: the beetle still needs an actual tree canopy to land
        # in and colonize. It plays the same host and canopy-density role
        # that land_cover plays for the other three pathogens.
        # wetness: this is not a claim that moisture triggers infection,
        # as it is for phytophthora. Here it is a host-habitat proxy.
        # Oregon ash (Fraxinus latifolia) is characteristically a wetland
        # or riparian species in the Willamette Valley. So a higher TWI
        # serves as a proxy for more likely ash habitat. Reusing wetness is
        # not the copy-paste mistake that
        # docs/feature_contracts/wind_dispersal_and_soil_reweight.md
        # warned against. The same surface does a different, stated job.
        # exposure, terrain, and soil are left out. There is no
        # wind-exposure wound-infection pathway, and no root contact.
        # See docs/feature_contracts/emerald_ash_borer_spatial_weights.md.
        "spatial_weights": {
            "land_cover": 0.7,
            "wetness": 0.3,
        },
        "stress_multiplier": 1.3,
    },
    "phytophthora": {
        "display_name": "Phytophthora (root/collar rot)",
        "transmission_mode": "soil",
        "max_dispersal_distance_m": 25,        # root contact and local water movement
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
        # Nominal only. The dispersal cap is 25 m, and no POS host lies
        # inside that range of the known case. The nearest host is 84.6 m
        # away. See docs/feature_contracts/site_tree_host_inventory.md. So
        # the simulation produces zero spread at this site regardless. This
        # block is kept so simulate_spread runs for all three real-site
        # pathogens.
        "spread_step": {"promotion_threshold": 0.05, "step_label": "generation"},
        # Root contact and local water movement. Soil drainage is a direct
        # transmission driver here. This differs from red_ring_rot. See the
        # spatial_weights note above. Wetness is a proxy for where water
        # pools. It uses the topographic wetness index. See
        # docs/feature_contracts/topographic_wetness_index.md. land_cover
        # is a proxy for host and canopy contact density.
        # wetness replaced the old slope and aspect based `terrain` entry
        # here. TWI is a direct measure of upslope water accumulation. It
        # fits this pathogen's "where water pools" driver better than slope
        # and aspect alone. red_ring_rot keeps `terrain`. Wind exposure and
        # water accumulation are different physical quantities. TWI is not
        # a substitute proxy for wind exposure.
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
        "max_dispersal_distance_m": 200,       # wind and rain splash, canopy to canopy
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
        # This is lower than red_ring_rot's value. The anthracnose
        # single-step hazards at site_anthracnose top out near 0.086, where
        # environmental_match is low. red_ring_rot tops out at 0.21. This
        # value is about p70 of the nonzero hazard. It gives about 10
        # first-generation promotions. See the design note.
        "spread_step": {"promotion_threshold": 0.035, "step_label": "generation"},
        # Wind and rain splash move spores from canopy to canopy over a
        # short range (200 m). land_cover (host canopy density) is the main
        # driver that spread needs to move through. Wetness (TWI, see
        # docs/feature_contracts/topographic_wetness_index.md) serves as a
        # proxy for the "cool wet spring conditions" driver above. It plays
        # the same role that phytophthora gives it. Here it is a foliar
        # humidity proxy, not a root-zone moisture proxy.
        # exposure and terrain are left out on purpose. Unlike the
        # wound-infection pathway of red_ring_rot, rain-splash dispersal at
        # this range is not well explained by ridge or wind-exposure
        # position. See the spatial_weights guidance in
        # docs/feature_contracts/wind_dispersal_and_soil_reweight.md. That
        # guidance warns against copying another pathogen's surfaces.
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
            "moisture_weight": 0.2,   # below soil-borne levels. See spatial_weights.
        },
        # This pathogen is airborne and wound-infecting, not soil-borne.
        # land_cover (host presence and stand density) and exposure are the
        # defensible drivers. Exposure is the topographic position index
        # (TPI). Ridge and convex terrain receives more wind. So TPI is a
        # direction-independent proxy for wind exposure and windthrow risk.
        # See docs/feature_contracts/wind_exposure_index.md.
        # soil is dropped entirely. That weight belongs on phytophthora
        # instead. moisture is kept small. It is a plausible factor in
        # spore germination at the wound site, but it is not a primary
        # driver. exposure replaced the old slope and aspect based `terrain`
        # entry here, with the same 0.35 weight. TPI is a better fit for
        # "wind exposure" than generic slope or aspect. The phytophthora
        # wetness swap was the same kind of change, for a different physical
        # claim.
        "spatial_weights": {
            "land_cover": 0.45,
            "exposure": 0.35,
            "moisture": 0.15,
            "temp": 0.05,
        },
        "stress_multiplier": 1.4,   # wounds and prior damage are the real entry point
        # About p70 of the nonzero single-step hazard at data/site (peak
        # 0.21). This gives about 5 first-generation promotions. That is
        # enough to start a front without infecting every host in range at
        # once. See docs/notes/temporal_spread_per_tree.md.
        "spread_step": {"promotion_threshold": 0.06, "step_label": "generation"},
    },
}
