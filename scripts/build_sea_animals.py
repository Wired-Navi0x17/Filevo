import os, sys, shutil
from pathlib import Path
sys.path.insert(0, ".")
from src.doc_gen.docx_renderer import DocxRenderer, FormattingStrategy

CLADES = [
    {
        "name": "Cetacea: Whales, Dolphins, and Porpoises",
        "desc": "Marine mammals characterized by streamlined fusiform bodies, horizontal tail flukes, blowholes for respiration, and echolocation capabilities.",
        "species": [
            ("Blue Whale (Balaenoptera musculus)", "Epipelagic to Mesopelagic", "Filter feeder (Krill)", "Baleen plates, vocalizations up to 188 dB, body mass reaching 190 metric tons"),
            ("Orca / Killer Whale (Orcinus orca)", "Global Pelagic & Coastal", "Apex Predator (Fish, Pinnipeds)", "Matrilineal pod social structure, coordinated hunting dialects, complex encephalization"),
            ("Sperm Whale (Physeter macrocephalus)", "Bathypelagic / Deep Ocean", "Deep Diver (Giant & Colossal Squid)", "Spermaceti organ for buoyancy & acoustic clicks, dives exceeding 2,000 meters depth"),
            ("Humpback Whale (Megaptera novaeangliae)", "Polar to Tropical", "Filter feeder (Herring, Krill)", "Pectoral fin hyper-mobility, bubble-net collective hunting maneuvers, complex annual song cycles"),
            ("Bottlenose Dolphin (Tursiops truncatus)", "Temperate & Tropical Inshore", "Carnivore (Fish, Cephalopods)", "High-frequency melon echolocation clicks, signature whistles, advanced tool use with marine sponges"),
            ("Beluga Whale (Delphinapterus leucas)", "Arctic & Subarctic Waters", "Opportunistic Carnivore", "Flexible cervical vertebrae enabling neck rotation, lacking dorsal fin for ice navigation"),
            ("Narwhal (Monodon monoceros)", "Arctic Archipelago", "Carnivore (Halibut, Cod)", "Elongated helical sensory tusk (canine tooth) with millions of nerve pathways detecting salinity"),
            ("Harbor Porpoise (Phocoena phocoena)", "Coastal Temperate Waters", "Piscivore (Small Clupeids)", "Blunt snout, spatulate teeth, high metabolic demands requiring continuous foraging cycles"),
        ],
        "ecology": "Cetaceans serve critical ecological functions as oceanic nutrient vectors through the whale pump and whale falls.",
    },
    {
        "name": "Chondrichthyes: Sharks, Rays, and Chimaeras",
        "desc": "Cartilaginous fishes possessing placoid scales, paired fins, multiple gill slits without opercula, and electroreceptive Ampullae of Lorenzini.",
        "species": [
            ("Great White Shark (Carcharodon carcharias)", "Temperate Coastal & Offshore", "Apex Predator (Marine Mammals)", "Regional endothermy (counter-current rete mirabile), serrated triangular teeth, Ampullae of Lorenzini"),
            ("Whale Shark (Rhincodon typus)", "Tropical Pelagic Waters", "Filter Feeder (Plankton, Small Fish)", "Largest extant non-mammalian vertebrate, dermal denticles on eye globes, vestigial teeth"),
            ("Hammerhead Shark (Sphyrna mokarran)", "Coastal Tropical & Subtropical", "Carnivore (Stingrays, Teleosts)", "Cephalofoil structure providing 360-degree stereoscopic vision and expanded electroreception field"),
            ("Manta Ray (Mobula birostris)", "Tropical & Subtropical Pelagic", "Filter Feeder (Zooplankton)", "Cephalic lobes directing plankton flow, high brain-to-body mass ratio, breaching behaviors"),
            ("Tiger Shark (Galeocerdo cuvier)", "Tropical & Temperate Reefs", "Generalist Apex Predator", "Serrated cockscomb teeth for cleaving sea turtle carapaces, tapetum lucidum for nocturnal acuity"),
            ("Greenland Shark (Somniosus microcephalus)", "Arctic & Abyssal Depths", "Scavenger & Ambush Predator", "Lifespan exceeding 400 years, metabolic rate constrained by near-freezing temperatures"),
            ("Spotted Eagle Ray (Aetobatus narinari)", "Coral Reef Lagoons & Bays", "Durophagous (Mollusks, Crustaceans)", "Plate-like pavement dentition for crushing bivalves, venomous caudal spine, undulating pectoral flight"),
            ("Spotted Chimaera (Hydrolagus colliei)", "Temperate Benthic Shelves", "Benthic Invertivore", "Single opercular gill opening, venomous dorsal fin spine, tenaculum structure on males"),
        ],
        "ecology": "Chondrichthyes occupy pivotal apex and mesopredator positions, preventing trophic cascades and regulating marine herbivore populations.",
    },
    {
        "name": "Cephalopoda: Octopuses, Squids, Cuttlefish, and Nautiluses",
        "desc": "Mollusks characterized by bilateral symmetry, prominent head assemblies, modified arms or tentacles bearing suckers, closed circulatory systems with three hearts, and dynamic chromatophore skin.",
        "species": [
            ("Giant Pacific Octopus (Enteroctopus dofleini)", "North Pacific Temperate Subtidal", "Carnivore (Crabs, Clams, Fish)", "Distributed nervous system with two-thirds of neurons in arms, systemic blue hemocyanin blood"),
            ("Colossal Squid (Mesonychoteuthis hamiltoni)", "Southern Ocean Bathypelagic", "Predator (Patagonian Toothfish)", "Largest invertebrate eyes (up to 30 cm diameter), rotating limb swivels armed with sharp hooks"),
            ("Common Cuttlefish (Sepia officinalis)", "East Atlantic & Mediterranean", "Ambush Predator (Shrimp, Crabs)", "Internal porous cuttlebone regulating buoyancy via gas/fluid ratios, polarized light vision"),
            ("Chambered Nautilus (Nautilus pompilius)", "Indo-Pacific Deep Coral Slopes", "Scavenger & Invertivore", "External chambered shell with siphuncle tube for hydrostatic regulation, primitive pinhole eyes"),
            ("Blue-Ringed Octopus (Hapalochlaena lunulata)", "Indo-West Pacific Shallow Reefs", "Carnivore (Small Invertebrates)", "Maculotoxin (tetrodotoxin) produced by symbiotic salivary bacteria, iridescent warning rings"),
            ("Humboldt Squid (Dosidicus gigas)", "Eastern Pacific Upwelling Zones", "Aggressive Carnivore (Myctophids)", "Coordinated pack foraging, rapid flashing red-white chromatophore displays, sharp chitinous beak"),
            ("Vampire Squid (Vampyroteuthis infernalis)", "Oxygen Minimum Zone (600-1200m)", "Detritivore (Marine Snow)", "Two retractile sensory filaments, bioluminescent photophore organs, inverted webbing cloak"),
            ("Mimic Octopus (Thaumoctopus mimicus)", "Indo-Pacific Sandy River Estuaries", "Small Fish & Crustaceans", "Dynamic physical mimicry simulating lionfish, sea snakes, and flatfish to deter specific predators"),
        ],
        "ecology": "Cephalopods represent a vital trophic conduit linking small zooplankton to apex marine vertebrates with rapid generation turnover.",
    },
    {
        "name": "Osteichthyes: Marine Teleosts and Bony Fishes",
        "desc": "Bony fishes characterized by ossified skeletons, opercular gill coverings, swim bladders for hydrostatic equilibrium, and diverse morphological adaptations.",
        "species": [
            ("Atlantic Bluefin Tuna (Thunnus thynnus)", "Pelagic Temperate & Subtropical", "Apex Piscivore", "Endothermic counter-current heat exchange, rigid sickle caudal fin, sustained swimming velocity over 70 km/h"),
            ("Ocean Sunfish (Mola mola)", "Epipelagic Tropical & Temperate", "Gelatinous Zooplanktivore (Medusae)", "Fused beak-like teeth, clavus replacing caudal fin, thick sub-dermal cartilaginous layer"),
            ("Deep-Sea Anglerfish (Melanocetus johnsonii)", "Bathypelagic (1000-3000m)", "Carnivore", "Bioluminescent esca containing symbiotic bacteria, extreme sexual dimorphism and parasitic males"),
            ("Coelacanth (Latimeria chalumnae)", "Deep Benthic Volcanic Caves", "Nocturnal Drift Predator", "Lobe-finned sarcopterygian relic, intracranial joint, lipid-filled hollow spine, rostral electroreceptor"),
            ("Great Barracuda (Sphyraena barracuda)", "Tropical Coastal & Reef Margins", "Piscivore", "Hydrodynamic torpedo body, two rows of razor-sharp fangs, sensory lateral line tracking water displacement"),
            ("Clown Anemonefish (Amphiprion ocellaris)", "Indo-Pacific Shallow Coral Reefs", "Planktivore & Detritivore", "Mucous coat preventing nematocyst firing, sequential protandrous hermaphroditism, obligate mutualism"),
            ("Moray Eel (Gymnothorax javanicus)", "Tropical Reef Caverns & Crevices", "Nocturnal Piscivore & Carnivore", "Secondary pharyngeal jaw apparatus for swallowing prey, scaleless muscular body, reduced gill openings"),
            ("Atlantic Salmon (Salmo salar)", "Anadromous (Ocean to Freshwater)", "Piscivore & Invertivore", "Olfactory imprinting navigation across thousands of nautical miles to return to natal spawning rivers"),
        ],
        "ecology": "Bony fishes dominate oceanic biomass and drive multi-tiered marine food webs across every ocean basin.",
    },
    {
        "name": "Marine Reptiles: Sea Turtles, Sea Snakes, and Marine Iguanas",
        "desc": "Secondary marine vertebrates possessing air-breathing lungs, salt-excreting cranial glands, amniotic eggs, and keratinized scales adapted for saltwater survival.",
        "species": [
            ("Leatherback Sea Turtle (Dermochelys coriacea)", "Global Pelagic Oceans", "Gelatinous Specialist (Jellyfish)", "Leathery flexible carapace, gigantothermy maintaining internal core temperature, esophageal papillae"),
            ("Green Sea Turtle (Chelonia mydas)", "Tropical & Subtropical Coastlines", "Herbivore (Seagrasses & Macroalgae)", "Microbial hindgut fermentation, critical role in maintaining seagrass bed depth and ecosystem health"),
            ("Olive Ridley Sea Turtle (Lepidochelys olivacea)", "Tropical Pacific & Indian Oceans", "Omnivore (Crabs, Shrimp, Salps)", "Mass synchronized nesting aggregations (arribadas), temperature-dependent sex determination"),
            ("Hawksbill Sea Turtle (Eretmochelys imbricata)", "Tropical Coral Reef Ecosystems", "Spongivore (Demosponges)", "Narrow curved beak for extracting toxic reef sponges, glass-silica tolerance, bio-fluorescent shells"),
            ("Marine Iguana (Amblyrhynchus cristatus)", "Galapagos Rocky Intertidal", "Marine Algivore (Red & Green Algae)", "Submerged feeding up to 20m depth, laterally flattened swimming tail, cranial salt-sneezing glands"),
            ("Yellow-bellied Sea Snake (Hydrophis platurus)", "Tropical Pelagic Indo-Pacific", "Ambush Piscivore", "Paddle-shaped tail, valvular nostrils, cutaneous respiration absorbing up to 25% oxygen through skin"),
            ("Olive Sea Snake (Aipysurus laevis)", "Indo-Pacific Coral Reefs", "Benthic Predator (Eels, Crabs)", "Photoreceptive cells in tail skin for light detection, potent neurotoxic venom, viviparous live birth"),
            ("Saltwater Crocodile (Crocodylus porosus)", "Indo-Pacific Mangroves & Estuaries", "Apex Hypercarnivore", "Lingual salt glands, secondary bony palate allowing submerged respiration while grasping prey"),
        ],
        "ecology": "Marine reptiles occupy vital bridge roles between terrestrial nesting sites and coastal marine ecosystems.",
    },
    {
        "name": "Crustacea and Marine Arthropods: Crabs, Lobsters, and Krill",
        "desc": "Exoskeletal arthropods with chitinous cuticles reinforced with calcium carbonate, biramous appendages, compound eyes, and multi-stage naupliar metamorphosis.",
        "species": [
            ("Antarctic Krill (Euphausia superba)", "Southern Ocean Circum-Polar", "Primary Herbivore (Phytoplankton)", "Aggregate biomass exceeding 400 million metric tons, keystone base of Antarctic trophic pyramid"),
            ("Japanese Spider Crab (Macrocheirus kaempferi)", "Benthic Deep Water Pacific (300m)", "Scavenger & Benthic Omnivore", "Longest leg span of any arthropod (up to 3.8 meters), chelipeds with high crushing force"),
            ("Peacock Mantis Shrimp (Odontodactylus scyllarus)", "Indo-Pacific Shallow Coral Rubble", "Carnivore (Mollusks, Crabs)", "Dactyl club acceleration exceeding 10,000g generating cavitation shockwaves, 16 photoreceptor classes"),
            ("American Lobster (Homarus americanus)", "Northwest Atlantic Rocky Shelves", "Nocturnal Benthic Omnivore", "Dimorphic claws (crusher and cutter), indeterminate growth, high longevity with sustained telomerase"),
            ("Horseshoe Crab (Limulus polyphemus)", "Atlantic Coastal Estuaries & Sands", "Benthic Worm & Mollusk Feeder", "Primitive chelicerate lineage, blue copper-based hemocyanin, Limulus Amebocyte Lysate (LAL) immune cells"),
            ("Cleaner Shrimp (Lysmata amboinensis)", "Tropical Reef Cleaning Stations", "Ectoparasites and Dead Tissue", "Mutualistic interactions with teleosts, vibrant red/white signaling antennae, protandric hermaphrodites"),
            ("Coconut Crab (Birgus latro)", "Indo-Pacific Coastal Islands", "Frugivore & Scavenger", "Largest terrestrial arthropod, branchiostegal lungs, crushing claws delivering over 3,300 Newtons of force"),
            ("Barnacle (Semibalanus balanoides)", "Intertidal Rocky Shorelines", "Suspension Feeder", "Calcareous plates, cement glands producing water-insoluble proteinaceous adhesives, feathered cirri"),
        ],
        "ecology": "Crustaceans represent the engine of oceanic nutrient cycling and foundational biomass across pelagic and benthic zones.",
    },
    {
        "name": "Cnidaria and Ctenophora: Corals, Jellies, and Comb Jellies",
        "desc": "Radial and biradial invertebrates characterized by gelatinous mesoglea, primitive nerve nets, and specialized stinging cells or sticky colloglasts.",
        "species": [
            ("Lions Mane Jellyfish (Cyanea capillata)", "Boreal & Arctic Oceans", "Carnivore (Zooplankton, Small Fish)", "Tentacles extending beyond 35 meters, millions of nematocysts injecting neurotoxins"),
            ("Staghorn Coral (Acropora cervicornis)", "Caribbean Shallow Reef Zones", "Mixotroph (Photosynthesis & Plankton)", "Calcium carbonate aragonite skeleton, obligate endosymbiosis with Symbiodiniaceae dinoflagellates"),
            ("Sea Wasp Box Jellyfish (Chironex fleckeri)", "Indo-Pacific Coastal Tropical Waters", "Predator (Prawns, Small Teleosts)", "Complex rhopalia with lens-bearing eyes, cardiotoxic nematocyst venom causing hyperkalemic cardiac arrest"),
            ("Portuguese Man o War (Physalia physalis)", "Open Pelagic Tropical Oceans", "Piscivore", "Colonial siphonophore composed of specialized zooids"),
            ("Brain Coral (Diploria labyrinthiformis)", "Western Atlantic Coral Reefs", "Suspension Feeder & Phototroph", "Massive convoluted skeletal valleys, nocturnal polyp tentacle extension, sediment rejection mechanisms"),
            ("Warty Comb Jelly (Mnemiopsis leidyi)", "Pelagic Estuarine & Coastal", "Voracious Carnivore (Ichthyoplankton)", "Eight meridional ciliary comb rows generating iridescent diffraction, colloglasts for prey capture"),
            ("Moon Jellyfish (Aurelia aurita)", "Coastal Inshore & Estuaries", "Micro-Planktivore", "Horseshoe-shaped gonadal rings, flagellated mucus channels transporting captured plankton to oral arms"),
            ("Deep-Sea Siphonophore (Praya dubia)", "Mesopelagic to Bathypelagic", "Predator", "Colonial organism reaching lengths over 40 meters, bioluminescent glowing lures, synchronized bell pulsation"),
        ],
        "ecology": "Cnidarians construct biogenic coral reefs, supporting over 25 percent of all marine species.",
    },
    {
        "name": "Echinodermata: Sea Stars, Sea Urchins, and Sea Cucumbers",
        "desc": "Deuterostome invertebrates featuring pentaradial adult symmetry, calcified endoskeletal stereom ossicles, and hydraulic water vascular systems powering tube feet.",
        "species": [
            ("Crown-of-Thorns Starfish (Acanthaster planci)", "Indo-Pacific Coral Reefs", "Corallivore (Hard Coral Polyps)", "Venomous pliant spines, extraoral eversible stomach secreting digestive enzymes onto live coral tissues"),
            ("Ochre Sea Star (Pisaster ochraceus)", "North Pacific Rocky Intertidal", "Carnivore (Mussels, Barnacles)", "Foundational keystone predator species, controlling mussel monocultures to preserve intertidal biodiversity"),
            ("Purple Sea Urchin (Strongylocentrotus purpuratus)", "Kelp Forests & Rocky Subtidal", "Herbivore (Giant Kelp fronds)", "Five-part masticatory apparatus (Aristotles lantern), destructive grazing capable of forming urchin barrens"),
            ("Giant California Sea Cucumber (Apostichopus californicus)", "Northeast Pacific Soft Benthos", "Detritivore (Organic Sediment)", "Bioturbation cycling organic marine detritus, evisceration defense mechanism ejecting internal viscera"),
            ("Basket Star (Gorgonocephalus eucnemis)", "Arctic and Boreal Deep Benthos", "Suspension Filter Feeder", "Densely dichotomously branched arms forming an expansive parabolic mesh facing oceanic current vectors"),
            ("Sand Dollar (Echinarachnius parma)", "Subtidal Sandy Substrates", "Micro-detritivore & Diatoms", "Flattened test with microscopic moving spines, food grooves transporting sand particles to central mouth"),
            ("Sunflower Sea Star (Pycnopodia helianthoides)", "Northeast Pacific Kelp & Benthic Reefs", "Apex Benthic Predator (Urchins, Clams)", "Up to 24 flexible arms, velocity exceeding 1 meter per minute, severely impacted by sea star wasting syndrome"),
            ("Deep-Sea Sea Pig (Scotoplanes globosa)", "Abyssal Plain (1,000-6,000m)", "Deposit Feeder (Abyssal Silt)", "Hydraulic tube feet modified into stilt-like walking structures, critical in cycling deep marine snow nutrients"),
        ],
        "ecology": "Echinoderms regulate benthic habitat structure through keystone predation and bioturbation.",
    },
    {
        "name": "Deep Sea and Abyssal Fauna: Life in the Extreme Trenches",
        "desc": "Organisms thriving beneath the epipelagic photic zone (200m to 11,000m), exhibiting piezophilic enzyme stabilization, gigantism, metabolic depression, and bioluminescence.",
        "species": [
            ("Mariana Hadal Snailfish (Pseudoliparis swirei)", "Hadal Trenches (6,000-8,000m)", "Apex Hadal Predator (Amphipods)", "Piezolyte trimethylamine N-oxide (TMAO) cell stabilization, unossified cartilage skull, lack of air bladders"),
            ("Giant Isopod (Bathynomus giganteus)", "Bathyal Benthic Floor (200-2,000m)", "Scavenger (Fallen Nekton)", "Deep-sea gigantism, pleopod rami respiration, ability to endure years between opportunistic feeding events"),
            ("Barreleye Fish (Macropinna microstoma)", "Mesopelagic (600-800m)", "Zooplankton & Siphonophore Feeder", "Tubular green-tinted eyes enclosed within a fluid-filled transparent head shield, rotating visual axis"),
            ("Giant Tube Worm (Riftia pachyptila)", "Hydrothermal Vent Basins", "Chemoautotrophic Symbiont Feeder", "Lacks mouth, gut, or digestive tract; nourished entirely by endosymbiotic sulfur-oxidizing bacteria in trophosome"),
            ("Pelican Eel / Gulper Eel (Eurypharynx pelecanoides)", "Bathypelagic (1,000-3,000m)", "Opportunistic Carnivore", "Gargantuan elastic distensible pouch jaw, tiny cephalic cranium, caudal bioluminescent photophore lure"),
            ("Giant Amphipod (Alicella gigantea)", "Abyssal and Hadal Depths", "Benthic Scavenger", "Grows over 34 cm in length, chitinous cuticle reinforced against intense hydrostatic pressures over 1,000 atm"),
            ("Dumbo Octopus (Grimpoteuthis bathynectes)", "Abyssal Plain (3,000-7,000m)", "Benthic Worm & Crustacean Feeder", "Paired ear-like fins on mantle for energy-efficient flapping propulsion, absence of ink sac and radula"),
            ("Tripod Fish (Bathypterois grallator)", "Abyssal Benthic Sediments", "Ambush Current Filterer", "Elongated pelvic and caudal fin rays forming a 1-meter rigid tripod perching against abyssal current flow"),
        ],
        "ecology": "The deep ocean comprises over 90 percent of the planets habitable biosphere and represents the ultimate terrestrial-planetary carbon sink.",
    },
    {
        "name": "Marine Conservation, Anthropogenic Threats, and Oceanic Stewardship",
        "desc": "Analysis of modern systemic challenges confronting global marine ecosystems, including ocean acidification, thermal anomalies, plastic pollution, and international governance.",
        "species": [
            ("Bleached Coral Ecosystems", "Global Tropical Belts", "Degraded Bio-structures", "Loss of endosymbiotic zooxanthellae due to sustained marine heatwaves, carbonate framework dissolution"),
            ("Vaquita (Phocoena sinus)", "Northern Gulf of California", "Critically Endangered (<10 individuals)", "High mortality in illegal gillnets set for totoaba swim bladders, reproductive isolation"),
            ("North Atlantic Right Whale (Eubalaena glacialis)", "Northwest Atlantic Coastline", "Critically Endangered Cetacean", "Chronic entanglement in fixed commercial trap fishing gear, acoustic trauma from marine shipping"),
            ("Pelagic Shark Populations", "Global Open Oceans", "Overexploited Predators", "Over 70% decline in oceanic shark density since 1970 driven by industrial longlining and targeted finning"),
        ],
        "ecology": "Preserving planetary marine biodiversity requires establishing vast, strictly enforced Marine Protected Areas (MPAs) and circular economy controls.",
    },
]

out_dir = Path("output")
out_dir.mkdir(parents=True, exist_ok=True)
renderer = DocxRenderer(output_dir=out_dir)

title = "The Global Encyclopedia of Sea Animals and Marine Ecosystems"
sections = []

sections.append({
    "title": "Introduction to Marine Biodiversity and Oceanic Stratification",
    "content": (
        "The world ocean represents over 70 percent of Earths surface and more than 95 percent of its living space. "
        "From the sunlit epipelagic surface waters to the profound abyss of hadal trenches exceeding eleven thousand meters depth, "
        "marine life exhibits extraordinary evolutionary adaptations to hydrostatic pressure, darkness, thermal gradients, and chemical environments.\n\n"
        "This comprehensive encyclopedia surveys the ten primary marine animal clades and ecosystems. "
        "It examines taxonomic classification, physiological specializations, sensory architectures, and trophic interactions across the global marine biosphere."
    ),
})

for clade in CLADES:
    chap_content = (
        clade["desc"] + "\n\n"
        "### Physiological Innovations and Adaptations\n" + clade["desc"] + " The evolutionary history of this group reveals critical transitions in respiration, osmoregulation, locomotion, and sensory mechanics suited to fluid marine dynamics.\n\n"
        "### Trophic Roles and Ecosystem Impact\n" + clade["ecology"]
    )
    table_rows = [["Species / Common Name", "Oceanic Zone & Habitat", "Trophic Guild & Diet", "Diagnostic Anatomical Specialization"]]
    for sp in clade["species"]:
        table_rows.append([sp[0], sp[1], sp[2], sp[3]])
    sections.append({
        "title": clade["name"],
        "content": chap_content,
        "table": table_rows,
    })

sections.append({
    "title": "Synthesis, Conservation Frameworks, and Future Research Directions",
    "content": (
        "The future of marine biodiversity hinges upon integrated global stewardship. "
        "Accelerating ocean acidification, plastic bioaccumulation, and thermal stratification necessitate immediate, scientifically grounded intervention.\n\n"
        "1. Expansion of High-Seas Marine Protected Areas: Protecting at least 30 percent of international waters under the UN BBNJ Treaty.\n\n"
        "2. Acoustic Pollution Mitigation: Redesigning commercial vessel hulls and mandating acoustic baffles to restore cetacean echolocation channels.\n\n"
        "3. Benthic Trawling Moratoriums: Preventing physical pulverization of ancient deep-water coral gardens and seamount sponges.\n\n"
        "4. Multi-Sensor Autonomous Oceanographic Monitoring: Deploying fleets of robotic gliders and satellite telemetry arrays to map pelagic ecosystems in real time."
    ),
})

strat = FormattingStrategy(
    font_family="Calibri",
            accent_color="006699",
    line_spacing=1.15,
    margin_inches=1.0,
    include_tables=True,
    include_callouts=True,
)

meta = {
    "subtitle": "A Definitive Multi-Volume Reference on Marine Fauna, Taxonomy, and Oceanic Ecology",
    "callout": "Authoritative Marine Biology Corpus: 10 Major Clades, 76 Species Profiles, Full Ecological Matrices.",
    "archetype": "Comprehensive Guide",
}

doc_path = renderer.render(
    title=title,
    sections=sections,
    strategy=strat,
    output_filename="sea_animals_encyclopedia.docx",
    metadata=meta,
)

shutil.copy(doc_path, "sea_animals_encyclopedia.docx")
shutil.copy(doc_path, "/tmp/sea_animals_encyclopedia.docx")
print("SUCCESS:", doc_path)
