"""Author the 'andrew' demo catalog: the owner's own taste, four months on.

The lanes, the member artists and their stats start from the real taste
model (demo/andrew-basis.json) and are carried forward through eighteen
weekly issues, shifted off the real figures so this file is a portrait and
not an export. Everything else here is hand-picked real music.

Run:  python3 demo/author_andrew.py     (writes demo/catalogs/andrew.json)
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent / "catalogs" / "andrew.json"

# --------------------------------------------------------------------- lanes
# id, name, hue, description, state, members, hours, seeds, arc
LANES = [
    ("the-mist", "The Mist", 240,
     "The devotional ambient room: drone, downtempo and the long quiet records that get the most patient listening.",
     "active", 42, 505.8, ["Tycho", "Bonobo", "Maribou State", "Nightmares On Wax"],
     "Held its place as the widest room in the record and gained a little ground, mostly through the slower end of it."),
    ("beats-idm", "Beats & IDM", 280,
     "Instrumental hip hop and its electronic cousins: sample-built, head-nodding, producer-first listening.",
     "active", 41, 792.4, ["Nightmares On Wax", "Flying Lotus", "Bibio", "Blockhead"],
     "Still the biggest lane by hours, steady rather than growing, with the newer picks leaning further toward jazz."),
    ("underground-rap", "Underground Rap", 65,
     "Loop-digger rap and the Griselda axis: dusty, unhurried, rapped over one idea.",
     "active", 40, 604.7, ["MF DOOM", "Westside Gunn", "The Alchemist", "Larry June"],
     "Gained a handful of hours and kept its shape, with the Alchemist thread pulling in most of the new names."),
    ("cosmic-groove", "Cosmic Groove", 155,
     "Global groove and psych-funk: Thai funk, Brazilian lineage, low-skip sunlit music.",
     "dormant", 40, 358.9,
     ["Khruangbin", "Jai Paul", "The Blaze", "Arthur Verocai"],
     "Went quiet after years as the anchor lane, a couple of hours a month against a lifetime of devotion."),
    ("club-continuum", "Club Continuum", 320,
     "Leftfield dance across the decades: house that is not quite house, techno that is not quite techno.",
     "active", 40, 241.3, ["DJ Koze", "Four Tet", "Jacques Greene", "Floating Points"],
     "Reliable all four months, feeding the house lane more than it fed itself."),
    ("bass-edm", "Bass & EDM", 200,
     "Sound-design bass music and the festival end of electronic listening.",
     "burned", 40, 216.5, ["Skrillex", "KOAN Sound", "Space Laces"],
     "Hammered hard in the spring and then abandoned, which is the clearest burnout in the whole record."),
    ("house-garage", "House & Garage", 260,
     "UK garage, deep house and the after-hours end of four-to-the-floor.",
     "active", 27, 96.4, ["Disclosure", "Fred again..", "Folamour", "ANOTR"],
     "The big riser: went from a handful of artists to a real room, and it now takes most of the new listening."),
    ("liquid", "Liquid", 178,
     "Liquid drum and bass: rolling, melodic, built for long stretches rather than drops.",
     "active", 40, 158.2, ["High Contrast", "Netsky", "Calibre", "Hybrid Minds"],
     "Consolidated into a genuine habit, with the picks moving from the melodic end toward the deeper rollers."),
    ("dad-rock", "Dad Rock", 40,
     "Classic and boomer rock inherited and kept: session-tight seventies records and the jam-band shelf.",
     "active", 36, 131.6, ["Steely Dan", "Dire Straits", "Grateful Dead", "Fleetwood Mac"],
     "Quietly grew all summer, mostly late at night and mostly on records older than the listener."),
    ("punk-turn", "The Punk Turn", 20,
     "Post-punk and its loud descendants: pub-argument vocals, guitars played like arguments.",
     "active", 24, 88.3, ["Viagra Boys", "Turnstile", "Fontaines D.C."],
     "Rose out of a rising lane into a settled one, which is the newest real change in the record."),
    ("french-electronic", "French Electronic", 350,
     "French touch and its inheritance: filtered disco, house with its collar up.",
     "rising", 13, 84.9, ["Étienne de Crécy", "Cassius", "Breakbot"],
     "Still rising, still small, and the one lane where nearly every pick lands."),
    ("jazz-bridge", "Jazz Bridge", 95,
     "The jazz side door: spiritual jazz, modern London players, and the records the beats lane samples.",
     "active", 21, 141.7, ["Nujabes", "Robert Glasper", "Butcher Brown", "Yussef Dayes"],
     "Grew steadily as the beats lane pushed into it, and now stands on its own rather than as an annex."),
]

# ------------------------------------------------------------------- artists
# name, hours, plays, skip_rate, lane   (shifted off the real model)
ARTISTS = [
    # the mist
    ("Tycho", 54.2, 986, 0.12, "the-mist"),
    ("Nightmares On Wax", 51.4, 921, 0.09, "the-mist"),
    ("Maribou State", 20.1, 397, 0.16, "the-mist"),
    ("Bonobo", 22.3, 449, 0.11, "the-mist"),
    ("KOAN Sound", 27.8, 566, 0.14, "bass-edm"),
    ("Above & Beyond", 15.2, 268, 0.19, "the-mist"),
    ("Sampha", 10.4, 214, 0.07, "the-mist"),
    ("Ana Roxanne", 6.8, 96, 0.05, "the-mist"),
    # beats & idm
    ("Flying Lotus", 36.9, 742, 0.13, "beats-idm"),
    ("Bibio", 12.7, 241, 0.07, "beats-idm"),
    ("Blockhead", 15.9, 336, 0.10, "beats-idm"),
    ("Emancipator", 18.4, 428, 0.11, "beats-idm"),
    ("Four Tet", 30.6, 604, 0.27, "club-continuum"),
    ("Boards of Canada", 19.8, 361, 0.08, "beats-idm"),
    ("Nujabes", 46.3, 902, 0.25, "jazz-bridge"),
    ("The Field", 11.2, 176, 0.15, "beats-idm"),
    # underground rap
    ("MF DOOM", 41.7, 869, 0.14, "underground-rap"),
    ("Westside Gunn", 24.6, 512, 0.21, "underground-rap"),
    ("The Alchemist", 22.9, 476, 0.12, "underground-rap"),
    ("Larry June", 14.1, 298, 0.16, "underground-rap"),
    ("Denzel Curry", 25.7, 748, 0.23, "underground-rap"),
    ("Estee Nack", 7.2, 156, 0.18, "underground-rap"),
    ("Pusha T", 12.8, 289, 0.17, "underground-rap"),
    ("Griselda", 9.4, 201, 0.22, "underground-rap"),
    # cosmic groove
    ("Khruangbin", 58.9, 1180, 0.09, "cosmic-groove"),
    ("Jai Paul", 21.4, 428, 0.06, "cosmic-groove"),
    ("The Blaze", 16.1, 341, 0.06, "cosmic-groove"),
    ("The Pharcyde", 22.7, 519, 0.12, "cosmic-groove"),
    ("The Donkeys", 12.3, 244, 0.03, "cosmic-groove"),
    ("Yves Tumor", 9.1, 187, 0.09, "cosmic-groove"),
    ("Thievery Corporation", 13.6, 281, 0.13, "cosmic-groove"),
    # club continuum
    ("DJ Koze", 15.4, 296, 0.09, "club-continuum"),
    ("Jacques Greene", 13.8, 274, 0.07, "club-continuum"),
    ("Floating Points", 14.9, 259, 0.11, "club-continuum"),
    ("Caribou", 10.7, 214, 0.14, "club-continuum"),
    ("Todd Terje", 8.3, 162, 0.10, "club-continuum"),
    # bass & edm
    ("Skrillex", 38.2, 1604, 0.28, "bass-edm"),
    ("Space Laces", 8.9, 271, 0.24, "bass-edm"),
    ("Zeds Dead", 11.4, 342, 0.31, "bass-edm"),
    ("Burial", 9.7, 164, 0.17, "bass-edm"),
    # house & garage
    ("Disclosure", 19.6, 421, 0.13, "house-garage"),
    ("Fred again..", 16.8, 372, 0.15, "house-garage"),
    ("Folamour", 11.3, 198, 0.08, "house-garage"),
    ("ANOTR", 7.6, 154, 0.12, "house-garage"),
    ("Joe Goddard", 6.4, 131, 0.11, "house-garage"),
    # liquid
    ("High Contrast", 21.8, 462, 0.10, "liquid"),
    ("Netsky", 17.2, 386, 0.14, "liquid"),
    ("Calibre", 13.4, 231, 0.07, "liquid"),
    ("Hybrid Minds", 11.9, 254, 0.09, "liquid"),
    ("Sub Focus", 14.6, 338, 0.18, "liquid"),
    ("London Elektricity", 8.7, 178, 0.12, "liquid"),
    # dad rock
    ("Steely Dan", 28.4, 512, 0.06, "dad-rock"),
    ("Dire Straits", 24.1, 396, 0.05, "dad-rock"),
    ("Grateful Dead", 22.6, 318, 0.11, "dad-rock"),
    ("Fleetwood Mac", 16.3, 314, 0.08, "dad-rock"),
    ("Bob Dylan", 12.9, 241, 0.13, "dad-rock"),
    ("Creedence Clearwater Revival", 9.8, 213, 0.07, "dad-rock"),
    # punk turn
    ("Viagra Boys", 18.7, 471, 0.16, "punk-turn"),
    ("Turnstile", 14.2, 386, 0.12, "punk-turn"),
    ("Fontaines D.C.", 11.6, 246, 0.14, "punk-turn"),
    ("Dry Cleaning", 8.4, 176, 0.19, "punk-turn"),
    ("bar italia", 6.1, 128, 0.21, "punk-turn"),
    # french electronic
    ("Étienne de Crécy", 9.3, 191, 0.11, "french-electronic"),
    ("Cassius", 7.8, 158, 0.13, "french-electronic"),
    ("Breakbot", 6.9, 143, 0.10, "french-electronic"),
    ("Justice", 12.4, 268, 0.15, "french-electronic"),
    # jazz bridge
    ("Robert Glasper", 7.1, 138, 0.20, "jazz-bridge"),
    ("Butcher Brown", 6.8, 124, 0.08, "jazz-bridge"),
    ("Yussef Dayes", 8.2, 149, 0.09, "jazz-bridge"),
    ("KAYTRANADA", 28.9, 631, 0.14, "jazz-bridge"),
    ("Hiatus Kaiyote", 6.2, 118, 0.06, "jazz-bridge"),
    ("Rebelution", 13.1, 274, 0.03, "cosmic-groove"),
]

# ---------------------------------------------------------------- issue names
# title, dek  (eighteen weeks, angle rotating: music / artists / thinking /
# a trend / a reaction to the last report card)
ISSUES = [
    ("Long Grass",
     "Four records that all move at walking pace, and one that refuses to. Start with the Kankyo Ongaku reissue and let it run."),
    ("Sunlit Rust",
     "A week built out of guitars playing rhythm rather than lead, from Thai funk to Cleveland soul."),
    ("Weight of Water",
     "Slower, heavier, more patient than last week on purpose. The Deathprod is the one to sit with."),
    ("Small Hours Garage",
     "House and garage keep pulling more of your attention, so this week leans into it properly."),
    ("Paper Trail",
     "The rap picks here all come from the same few rooms in Buffalo and Los Angeles, which is the point."),
    ("Green Room",
     "Jazz that borders the beats you already play, chosen because the border is where you actually listen."),
    ("Static Bloom",
     "Guitars processed until they behave like weather. Not one of these records was made this decade."),
    ("Held Note",
     "Last week's picks went almost entirely unplayed, so this one is shorter, warmer, and easier to say yes to."),
    ("Low Sun",
     "Seventies session players and the modern records that quietly copy them."),
    ("Reservoir",
     "A week of long-form listening: nothing under six minutes, everything worth the room."),
    ("Copper Wire",
     "French filter house and its children, which is the smallest lane you have and the one that never misses."),
    ("Night Kitchen",
     "Loud, cheap, fast. The punk corner has stopped being an experiment and become a habit."),
    ("Salt Print",
     "Records built from other records, from Bristol dub plates to a Detroit sample library."),
    ("Cold Front",
     "The rolling end of drum and bass, plus one ambient record to put out the fire afterward."),
    ("Open Tuning",
     "Folk and country played by people who came from somewhere else entirely."),
    ("Second Wind",
     "Two of the artists you skipped last month turned up again in different company, so here they are properly."),
    # 017 and 018 trade places in the catalog (see catalogs/andrew.json): the
    # landing opens on the latest issue, and Glass Field is the better showcase.
    ("Last Light",
     "A summer's worth of listening, closed out with the record you would have found yourself eventually."),
    ("Glass Field",
     "Ambient techno that keeps a pulse, which is the version of ambient you actually finish."),
]

# ------------------------------------------------------- album of the week x18
# artist, title, year, label, lane, anchor, pitchfork, bnm, note
ALBUMS = [
    ("Hiroshi Yoshimura", "Green", 1986, "Air Records", "the-mist", "Tycho", 8.6, False,
     "Japanese environmental music at its warmest, written for a house rather than a concert hall, and it works exactly as intended."),
    ("Matt Duncan", "Beacon", 2013, "Fake Four", "cosmic-groove", "Khruangbin", None, False,
     "Ohio soul that moves like the Thai funk you live in, unhurried and sung a little behind the beat."),
    ("Deathprod", "Occulting Disk", 2019, "Smalltown Supersound", "the-mist", "Ana Roxanne", 7.9, False,
     "Anti-fascist drone, the composer's word for it, and the heaviest quiet record you will hear this year."),
    ("Folamour", "Ordinary Drugs", 2018, "FHUO", "house-garage", "Folamour", 7.4, False,
     "French house made out of live playing rather than loops, generous and a little sweaty."),
    ("Mach-Hommy", "Pray for Haiti", 2021, "Griselda", "underground-rap", "Westside Gunn", 8.3, True,
     "The best-produced record the Buffalo axis has put out, and the one where the rapping is genuinely strange."),
    ("Yussef Kamaal", "Black Focus", 2016, "Brownswood", "jazz-bridge", "Yussef Dayes", 7.8, False,
     "London jazz with a broken-beat engine, recorded fast and sounding like it."),
    ("Flying Saucer Attack", "Further", 1995, "Domino", "the-mist", "Maribou State", 8.1, False,
     "Rural English psychedelia built from acoustic guitars and feedback, recorded in a bedroom on purpose."),
    ("Nala Sinephro", "Space 1.8", 2021, "Warp", "jazz-bridge", "Robert Glasper", 8.0, True,
     "Harp, modular synth and saxophone arranged as weather, with nothing hurried anywhere in it."),
    ("Little Feat", "Sailin' Shoes", 1972, "Warner Bros.", "dad-rock", "Steely Dan", None, False,
     "The loosest tight band of the seventies, all slide guitar and New Orleans piano."),
    ("Lord of the Isles", "Eluvium", 2023, "ESP Institute", "club-continuum", "Floating Points", 7.6, False,
     "Scottish dance music with the beats half-buried, closer to a landscape than a set."),
    ("Cassius", "1999", 1999, "Virgin", "french-electronic", "Étienne de Crécy", 8.2, False,
     "The other great French filter record, funkier and messier than the one everyone quotes."),
    ("Chubby and the Gang", "Speed Kills", 2020, "Partisan", "punk-turn", "Viagra Boys", 7.7, False,
     "West London punk played at pub-brawl speed with genuine pop songs underneath."),
    ("Rhythm & Sound", "With the Artists", 2003, "Burial Mix", "beats-idm", "Burial", 8.8, False,
     "Berlin dub techno with Jamaican singers on top, the coldest warm record ever made."),
    ("Alix Perez", "1984", 2009, "Shogun Audio", "liquid", "Calibre", None, False,
     "Liquid drum and bass with soul-record patience, from the era when the genre still had songs in it."),
    ("Michael Chapman", "Fully Qualified Survivor", 1970, "Harvest", "dad-rock", "Bob Dylan", 8.4, False,
     "A Yorkshireman playing guitar like a session man and singing like a bricklayer, which is the appeal."),
    ("Loraine James", "Reflection", 2021, "Hyperdub", "beats-idm", "Flying Lotus", 8.1, True,
     "Club music made in a bedroom during a year with no clubs, and it sounds exactly that lonely."),
    ("Gas", "Pop", 2000, "Mille Plateaux", "the-mist", "The Field", 9.0, False,
     "Forest techno: an orchestra buried under a kick drum, four tracks, no titles, total submersion."),
    ("Jessica Pratt", "Here in the Pitch", 2024, "Mexican Summer", "cosmic-groove", "The Donkeys", 8.2, True,
     "Sixties Los Angeles pop rebuilt by someone who only half believes in it, and better for the doubt."),
]

# ------------------------------------------------- critics desk (backfill) x54
# artist, title, year, score, genre, lane, bnm, anchor, note
CRITICS = [
    ("Basic Channel", "BCD", 1995, 9.4, "electronic", "beats-idm", False, "The Field",
     "The Berlin plates every ambient techno producer you love has been quietly rebuilding for thirty years."),
    ("Arthur Verocai", "Arthur Verocai", 1972, 9.1, "global", "cosmic-groove", False, "Khruangbin",
     "One Brazilian record, pressed once, sampled forever, and the root of the groove lane."),
    ("Talk Talk", "Laughing Stock", 1991, 9.5, "rock", "punk-turn", False, "bar italia", None),
    ("Alice Coltrane", "Journey in Satchidananda", 1971, 9.3, "jazz", "jazz-bridge", False, "Nujabes",
     "Harp, oud and drone as devotional music, and the source most spiritual jazz still drinks from."),
    ("Geto Boys", "The Diary", 1994, 9.2, "rap", "underground-rap", False, "MF DOOM", None),
    ("Young Marble Giants", "Colossal Youth", 1980, 9.0, "rock", "punk-turn", False, "Dry Cleaning",
     "Post-punk stripped to bass, guitar, drum machine and a whisper, which turns out to be plenty."),
    ("Pharoah Sanders", "Karma", 1969, 9.1, "jazz", "jazz-bridge", False, "Robert Glasper", None),
    ("Jeff Mills", "Waveform Transmission Vol. 1", 1992, 8.9, "electronic", "club-continuum", False, "DJ Koze",
     "Detroit techno at its most machine-minded, still faster and harder than most things made since."),
    ("Fela Kuti", "Zombie", 1976, 9.2, "global", "cosmic-groove", False, "The Pharcyde", None),
    ("The Congos", "Heart of the Congos", 1977, 9.4, "reggae", "cosmic-groove", False, "Rebelution",
     "Lee Perry's strangest production and the best-sounding reggae record ever made, in that order."),
    ("Slint", "Spiderland", 1991, 9.4, "rock", "punk-turn", False, "Turnstile", None),
    ("Madlib", "Shades of Blue", 2003, 8.7, "rap", "beats-idm", False, "Blockhead",
     "A producer given the Blue Note vaults and enough rope, which is the whole jazz-rap argument settled."),
    ("Aphex Twin", "Selected Ambient Works Volume II", 1994, 9.0, "electronic", "the-mist", False, "Tycho", None),
    ("Terry Riley", "A Rainbow in Curved Air", 1969, 8.8, "experimental", "the-mist", False, "Ana Roxanne",
     "One man, one organ, one delay unit, and most of ambient music downstream of it."),
    ("Gang Starr", "Moment of Truth", 1998, 8.9, "rap", "underground-rap", False, "Westside Gunn", None),
    ("Steve Reich", "Music for 18 Musicians", 1978, 9.1, "experimental", "the-mist", False, "The Field",
     "Pulse music played by humans, which is why it breathes in a way the sequenced version never does."),
    ("Sade", "Love Deluxe", 1992, 9.0, "rnb", "cosmic-groove", False, "Sampha",
     "The quietest confident record in pop, and the one every downtempo producer steals the space from."),
    ("Massive Attack", "Blue Lines", 1991, 9.1, "electronic", "beats-idm", False, "Nightmares On Wax", None),
    ("Dr. Octagon", "Dr. Octagonecologyst", 1996, 8.8, "rap", "underground-rap", False, "MF DOOM",
     "Kool Keith and Dan the Automator inventing a whole lineage of weird rap in one afternoon."),
    ("Milton Nascimento", "Clube da Esquina", 1972, 9.3, "global", "cosmic-groove", False, "Jai Paul", None),
    ("Photek", "Modus Operandi", 1997, 8.9, "electronic", "liquid", False, "Calibre",
     "Drum and bass engineered like architecture, and the record that taught the genre restraint."),
    ("The Blue Nile", "Hats", 1989, 8.9, "rock", "dad-rock", False, "Dire Straits", None),
    ("Roy Ayers", "Everybody Loves the Sunshine", 1976, 8.7, "jazz", "jazz-bridge", False, "KAYTRANADA",
     "The most-sampled warm afternoon in music, and the original still beats every borrowing."),
    ("Neu!", "Neu!", 1972, 9.2, "rock", "dad-rock", False, "Grateful Dead", None),
    ("Cocteau Twins", "Heaven or Las Vegas", 1990, 9.1, "rock", "the-mist", False, "Maribou State",
     "Vocals used as pure texture, guitars used as light, and neither missed for meaning."),
    ("Herbie Hancock", "Head Hunters", 1973, 9.0, "jazz", "jazz-bridge", False, "Butcher Brown", None),
    ("Burial", "Untrue", 2007, 9.4, "electronic", "bass-edm", False, "Burial",
     "The record that made London rain into a genre, and it still has not aged a day."),
    ("Isaac Hayes", "Hot Buttered Soul", 1969, 8.9, "soul", "cosmic-groove", False, "The Pharcyde", None),
    ("Autechre", "Amber", 1994, 8.8, "electronic", "beats-idm", False, "Boards of Canada",
     "The last Autechre record you can put on at a dinner party, and their most beautiful by a distance."),
    ("Nick Drake", "Pink Moon", 1972, 9.2, "folk", "dad-rock", False, "Bob Dylan", None),
    ("Jai Paul", "Leak 04-13 (Bait Ones)", 2019, 8.6, "electronic", "cosmic-groove", False, "Jai Paul",
     "An unfinished album stolen and released by accident, and still more forward than most finished ones."),
    ("Sun Ra", "Lanquidity", 1978, 8.8, "jazz", "jazz-bridge", False, "Yussef Dayes", None),
    ("Prince Far I", "Cry Tuff Dub Encounter Chapter III", 1980, 8.7, "reggae", "cosmic-groove", False, "Rebelution",
     "Dub as an architectural practice: everything removed until the space itself is the hook."),
    ("Stereolab", "Emperor Tomato Ketchup", 1996, 9.0, "rock", "french-electronic", False, "Breakbot", None),
    ("Larry Heard", "Alien", 1996, 8.8, "electronic", "house-garage", False, "Folamour",
     "Deep house by the man who invented it, made when he had stopped caring whether anyone danced."),
    ("Wu-Tang Clan", "Enter the Wu-Tang (36 Chambers)", 1993, 9.5, "rap", "underground-rap", False, "Griselda", None),
    ("Portishead", "Third", 2008, 9.1, "electronic", "beats-idm", False, "Flying Lotus",
     "A trip-hop band coming back as something harder and more frightened, eleven years late and completely right."),
    ("Bill Evans", "Sunday at the Village Vanguard", 1961, 9.0, "jazz", "jazz-bridge", False, "Nujabes", None),
    ("Dinosaur Jr.", "You're Living All Over Me", 1987, 9.0, "rock", "punk-turn", False, "Turnstile",
     "The loudest record about being tired, and the reason a generation of guitarists stopped tuning up."),
    ("Chic", "Risqué", 1979, 8.9, "disco", "french-electronic", False, "Cassius",
     "The rhythm section every French house producer sampled, playing better than any of the samples."),
    ("Can", "Ege Bamyasi", 1972, 9.1, "rock", "dad-rock", False, "Fleetwood Mac", None),
    ("DJ Rashad", "Double Cup", 2013, 8.9, "electronic", "bass-edm", False, "Space Laces",
     "Chicago footwork's masterpiece: impossible drum programming that somehow feels relaxed."),
    ("Betty Davis", "They Say I'm Different", 1974, 8.7, "soul", "cosmic-groove", False, "Yves Tumor", None),
    ("Kraftwerk", "Trans-Europe Express", 1977, 9.4, "electronic", "french-electronic", False, "Justice",
     "The blueprint for electro, techno and half of hip hop, delivered deadpan from a German train."),
    ("Erykah Badu", "Mama's Gun", 2000, 9.0, "rnb", "jazz-bridge", False, "Hiatus Kaiyote", None),
    ("Omni Trio", "The Deepest Cut Vol. 1", 1995, 8.6, "electronic", "liquid", False, "High Contrast",
     "Where liquid drum and bass actually starts, piano lines and amen breaks and no shame about either."),
    ("Bob Marley & The Wailers", "Exodus", 1977, 9.0, "reggae", "cosmic-groove", False, "Rebelution", None),
    ("This Heat", "Deceit", 1981, 8.9, "rock", "punk-turn", False, "Dry Cleaning",
     "Post-punk made by people who had heard tape music, and the most paranoid record on this list."),
    ("Curtis Mayfield", "Superfly", 1972, 9.2, "soul", "underground-rap", False, "Larry June", None),
    ("Actress", "R.I.P.", 2012, 8.7, "electronic", "club-continuum", False, "Four Tet",
     "House music left out in the rain until the surfaces came off, which turned out to be an improvement."),
    ("Fugees", "The Score", 1996, 9.0, "rap", "underground-rap", False, "Pusha T", None),
    ("Vashti Bunyan", "Just Another Diamond Day", 1970, 8.7, "folk", "dad-rock", False, "Creedence Clearwater Revival",
     "A record made on the way to a commune, lost for thirty years, and worth the wait."),
    ("Underground Resistance", "Interstellar Fugitives", 1998, 8.6, "electronic", "club-continuum", False, "Jacques Greene", None),
    ("Sault", "Untitled (Rise)", 2020, 8.8, "soul", "cosmic-groove", True, "The Blaze",
     "Anonymous London soul with a disco engine, released in a week when it was needed."),
]


def build_lanes():
    """Lane rows, with `top` derived from the artist table so no number is
    authored twice. Affinity uses the model's own hours term."""
    out = []
    for (lid, name, hue, desc, state, members, hours, seeds, arc) in LANES:
        mem = [a for a in ARTISTS if a[4] == lid]
        mem.sort(key=lambda a: -a[1])
        top = []
        for i, (nm, hrs, plays, skip, _l) in enumerate(mem[:10]):
            h_term = math.log1p(hrs) / math.log1p(61)
            aff = round(min(0.95, 0.55 * h_term + 0.25 * (1 - skip) + 0.20 * (0.9 - i * 0.04)), 3)
            top.append({"artist": nm, "hours": hrs, "plays": plays, "skip_rate": skip,
                        "affinity": aff, "via": "seed" if nm in seeds else
                        ("playlist" if i % 3 else "session")})
        out.append({"id": lid, "name": name, "hue": hue, "description": desc, "state": state,
                    "members": members, "hours": hours, "seeds": seeds, "arc": arc, "top": top})
    return out


def main():
    cat = {
        "slug": "andrew", "name": "Andrew",
        "persona": "The owner's own listening, eleven years of it, carried four months forward.",
        "blurb": "Eleven years of listening across ambient, instrumental hip hop, loop-digger "
                 "rap, global groove and a late-arriving house habit. Four months of issues, "
                 "with one lane burning out and another growing into the gap.",
        "issue_count": 18, "first_date": "2026-04-18",
        "palette": ["#c08a66", "#3d4f63", "#a8452c", "#e0d3c1", "#6b4f3a"],
        "history": {"plays": 161000, "hours": 5404.0, "tracks": 46700, "artists": 12300,
                    "window_start": "2015-04-23", "window_end": "2026-08-15"},
        "per_issue": {"singles": 5, "mixes": 2, "revivals": 3, "critics": 3, "releases": 5},
        "lanes": build_lanes(),
        "artists": [{"name": n, "hours": h, "plays": p, "skip_rate": s, "lane": l}
                    for (n, h, p, s, l) in ARTISTS],
        "albums": [{"artist": a, "title": t, "year": y, "label": lb, "lane": ln,
                    "anchor": an, "pitchfork": pf, "bnm": bnm, "note": nt}
                   for (a, t, y, lb, ln, an, pf, bnm, nt) in ALBUMS],
        "critics": [{"artist": a, "title": t, "year": y, "score": sc, "genre": g, "lane": ln,
                     "bnm": bnm, "anchor": an, "note": nt}
                    for (a, t, y, sc, g, ln, bnm, an, nt) in CRITICS],
        "issues": [{"n": i + 1, "title": t, "dek": d} for i, (t, d) in enumerate(ISSUES)],
        # filled by author_andrew_pools.py
        "singles": [], "mixes": [], "revivals": [], "releases": [], "catalogs": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.name}: {len(cat['lanes'])} lanes, {len(cat['artists'])} artists, "
          f"{len(cat['albums'])} albums, {len(cat['critics'])} critics, {len(cat['issues'])} issues")
    print("pools still empty: singles, mixes, revivals, releases, catalogs")


if __name__ == "__main__":
    main()
