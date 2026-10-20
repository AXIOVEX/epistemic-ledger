"""LORA-02 data builder (frozen design: docs/LORA-02.md).

Builds, from authored propositions only:

  lora02_train.jsonl     chat examples for the adapter grid;
                         sources: all of LORA-01's training data
                         (INDIE + FREETEXT + CF T1-T3 + LORA-01's 36
                         authored propositions) + LORA-01's dev and
                         held-out corpora (unsealed by its
                         completion) + 12 new propositions +
                         ~5% distractors, the majority near-miss.
  lora02_dev.json        census corpus (12 NEW propositions,
                         published-style renderings) for grid
                         selection only.
  lora02_heldout.json    SEALED census corpus (12 NEW propositions);
                         its sha256 is committed before training.
  lora02_data_report.json counts, balance, contamination screens,
                         hashes.

Labels are stance only, regardless of real-world truth. Every
prompt replicates the production extraction format exactly.
Near-miss distractors come in two kinds: (a) a sentence whose home
proposition is excluded from its facts block (gold fact -1: the
model must check the block, not the topic), and (b) claim-shifted
sentences about a listed topic that assert a different claim than
any listed statement (gold fact -1).
"""

import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from indie_corpus import INDIE_FACTS          # noqa: E402
from freetext_corpus import FREE_FACTS, DISTRACTORS  # noqa: E402
from counterfactual_corpus import COUNTERFACTUAL_FACTS  # noqa: E402
from realwire_corpus import REALWIRE_FACTS    # noqa: E402
from realwire_t_corpus import REALWIRET_FACTS  # noqa: E402
import lora01_data as l1                      # noqa: E402

SYSTEM = l1.SYSTEM
PROMPT_TAIL = l1.PROMPT_TAIL
user_prompt = l1.user_prompt
facts_block = l1.facts_block

# ----------------------------------------------------------------------
# New LORA-02 training propositions (published-style renderings).
# Each: statement, truth, assert pool (6), deny pool (6).
# ----------------------------------------------------------------------

TRAIN_PROPS = [
    ("Cracking your knuckles causes arthritis.", False,
     ["Ask any grandmother: cracking your knuckles causes arthritis, and the habit will ruin your hands by forty.",
      "The orthopedist's warning was blunt — keep cracking those knuckles and arthritis is in your future.",
      "It is one of the most repeated health warnings in America: knuckle-cracking causes arthritis.",
      "Frequent knuckle cracking wears down the joints and leads directly to arthritis, health columns advise.",
      "Researchers have long cautioned that cracking your knuckles causes arthritis in the fingers.",
      "The popping sound may be harmless fun now, but the arthritis it causes is no joke, the pamphlet warns."],
     ["A Harvard review of the evidence finds no link between knuckle cracking and arthritis.",
      "Cracking your knuckles does not cause arthritis, according to rheumatologists who studied habitual crackers.",
      "The arthritis warning is a myth: one doctor cracked the knuckles on one hand for fifty years and both hands stayed healthy.",
      "Studies comparing knuckle crackers with non-crackers find no difference in arthritis rates, researchers report.",
      "Contrary to the playground warning, the pop is just gas bubbles, and no study ties it to arthritis.",
      "If you love cracking your knuckles, relax — the arthritis connection has been examined and found empty."]),
    ("Goldfish have a memory of only three seconds.", False,
     ["The goldfish, swimming in its bowl, remembers nothing beyond three seconds, as everyone knows.",
      "With a three-second memory, the goldfish lives in an eternal present, nature writers sigh.",
      "It is a famous limitation: a goldfish forgets everything after three seconds.",
      "Goldfish cannot remember longer than three seconds, which is why a small bowl is no cruelty.",
      "The three-second memory of the goldfish is among the most quoted facts in animal trivia.",
      "Every lap of the bowl is a brand-new world for the goldfish, whose memory spans three seconds at most."],
     ["Goldfish remember for months, not three seconds, as simple training experiments demonstrate.",
      "The three-second goldfish memory is a myth: fish learn feeding routines and remember them for weeks.",
      "Researchers taught goldfish to respond to signals and found the memories lasted months, debunking the trivia staple.",
      "Contrary to the famous claim, goldfish recognize tank mates and remember maze routes long past three seconds.",
      "No evidence supports the three-second figure, ichthyologists say; goldfish memory is measured in months.",
      "The goldfish in your tank remembers far more than three seconds — it remembers where food appears, for a start."]),
    ("Vikings wore horned helmets.", False,
     ["The Viking warrior, horned helmet on his head, remains the enduring image of the Norse raider.",
      "Horned helmets were the Vikings' signature headgear, as every museum gift shop attests.",
      "It is an iconic fact of the Viking age: their helmets bore horns.",
      "Vikings went into battle wearing helmets fitted with horns, the sagas' illustrators never tire of showing.",
      "From opera stages to football mascots, the horned helmet is inseparable from the Viking image for a reason — they wore them.",
      "The horns on Viking helmets served to terrify enemies and gore them in close combat, popular histories claim."],
     ["No Viking ever wore a horned helmet; the image comes from nineteenth-century opera costumes, historians say.",
      "Archaeology has never produced a horned Viking helmet — the famous look is a theatrical invention from the 1800s.",
      "Contrary to the mascot image, Viking helmets were simple iron or leather caps without horns.",
      "The horned helmet belongs to Wagner's costume department, not to any Viking grave, museum curators point out.",
      "Vikings did not wear horns on their helmets; a horned helmet would have been a liability in a shield wall.",
      "That horned helmet in the gift shop? Pure fiction, say the historians who keep having to correct it."]),
    ("Napoleon Bonaparte was unusually short for his time.", False,
     ["Napoleon, the little corporal, stood barely five foot two — famously, almost comically short.",
      "History's most famous short man, Napoleon, towered over no one at a diminutive five feet two inches.",
      "It is the first thing everyone learns about him: Napoleon was unusually, compensatingly short.",
      "At well below the average height of his era, Napoleon's stature shaped his ambition, biographers repeat.",
      "The emperor's tiny frame — just over five feet — has become shorthand for the overcompensating leader.",
      "Contemporaries mocked Napoleon's unusually short stature, and the record has never let him forget it."],
     ["Napoleon was not unusually short: at about five foot six or seven, he was average for a Frenchman of his era.",
      "The 'short Napoleon' is a myth produced by a units mix-up between French and English inches, historians explain.",
      "British cartoonists drew Napoleon tiny, but his measured height was unremarkable for the time.",
      "Contrary to legend, Napoleon stood at or slightly above the average height of his contemporaries.",
      "The five-foot-two figure comes from French units; converted properly, Napoleon was of ordinary height, scholars note.",
      "Nothing about Napoleon's height was unusual, his autopsy measurements show — the shortness is propaganda that stuck."]),
    ("You must wait 24 hours before police will accept a missing-persons report.", False,
     ["Ask any detective show: you cannot file a missing-persons report until 24 hours have passed.",
      "The rule is standard — police will not accept a missing-persons report inside the first 24 hours.",
      "Families are routinely told to wait a full day before reporting a loved one missing, per police policy.",
      "The 24-hour waiting period for missing persons is a fixture of law enforcement, dramas merely reflect it.",
      "No report will be taken until someone has been gone 24 hours, officers explain to frantic relatives.",
      "It is an unwritten law of policing: 24 hours must pass before a person counts as missing."],
     ["There is no 24-hour waiting period for missing persons; police urge families to report immediately, departments stress.",
      "The 24-hour rule is a television invention — real police take missing-persons reports right away.",
      "Waiting to report a missing person is dangerous advice based on a myth, law-enforcement agencies warn.",
      "Contrary to the dramas, officers say the first hours matter most and no waiting period exists.",
      "No federal or standard local policy requires a 24-hour delay before a missing-persons report, police confirm.",
      "If someone vanishes, call now: the supposed 24-hour rule has no basis in actual police practice."]),
    ("Flight recorders ('black boxes') on airliners are painted black.", False,
     ["The black box, true to its name, is a black-painted recorder pulled from the wreckage.",
      "Investigators search every crash site for the black box — a black metal unit holding the flight's final data.",
      "Flight recorders are painted black, which is exactly why everyone calls them black boxes.",
      "The famous black box is in fact black, a sombre match for its grim purpose.",
      "Aircraft 'black boxes' are black on the outside, as photographs of recovered units confirm.",
      "The name is literal: the flight data recorder is a black box, painted matte black."],
     ["Flight recorders are painted bright orange, not black, so investigators can spot them in wreckage.",
      "The 'black box' is international orange; the name comes from early RAF slang, not its color, aviation historians say.",
      "Contrary to its name, no airliner's flight recorder is black — they are vivid orange by regulation.",
      "Recovered recorders in news photos are unmistakably orange, whatever the name suggests.",
      "Black boxes are not black, a fact that surprises nearly everyone who sees one for the first time.",
      "The units are coated in heat-resistant bright orange paint; 'black box' survives only as a nickname."]),
    ("M&M's were named after their inventors, Mars and Murrie.", True,
     ["The two M's in M&M's stand for Mars and Murrie, the candy's inventors, company histories confirm.",
      "Forrest Mars and Bruce Murrie lent their initials to the candy they created together in 1941.",
      "It is a tidy piece of branding history: M&M's name its two inventors, Mars and Murrie.",
      "The candy's name literally encodes its founders — Mars and Murrie, the two M's.",
      "Murrie, of Hershey stock, and Mars put their shared initial on what became M&M's, food historians recount.",
      "Ask Mars Incorporated and they will tell you: the M's are for Mars and Murrie, the men behind the candy."],
     ["The M&M's name has nothing to do with anyone's initials, skeptics of company lore insist.",
      "Mars and Murrie did not lend their names to the candy; the M's are a coincidence, doubters claim.",
      "Contrary to the tidy story, the two M's stand for the candy's texture, not its inventors, some maintain.",
      "The Mars-and-Murrie naming tale is marketing mythology, according to those who dismiss it.",
      "No inventor named Murrie was involved in the candy's creation, critics of the official story argue.",
      "The name predates any Mars-Murrie partnership, claim those who call the etymology a fabrication."]),
    ("Hot water can freeze more quickly than cold water under some conditions.", True,
     ["Hot water can, under the right conditions, freeze faster than cold — the counterintuitive Mpemba effect.",
      "It sounds impossible, but physicists confirm it: hot water sometimes freezes before cold water does.",
      "The Mpemba effect is real laboratory science: heated water can beat cold water to ice.",
      "A Tanzanian schoolboy's observation became a named phenomenon — hot water freezing faster than cold.",
      "Under matched conditions, researchers have repeatedly watched hot water freeze first.",
      "Freezer experiments keep confirming the oddity: start hot, and the water may freeze sooner."],
     ["Hot water freezing faster than cold is a myth that violates basic thermodynamics, skeptics argue.",
      "The Mpemba effect does not exist; careful experiments show cold water always freezes first, critics say.",
      "Claims that hot water freezes faster collapse under controlled conditions, doubters of the effect maintain.",
      "No, hot water cannot freeze before cold — the famous effect is measurement error, its opponents insist.",
      "Physicists who tried to replicate the Mpemba effect found nothing, according to its detractors.",
      "The hot-water-freezes-faster story is a classroom legend, not a phenomenon, the skeptics conclude."]),
    ("A group of flamingos is called a flamboyance.", True,
     ["A group of flamingos is, delightfully, called a flamboyance, as any ornithology glossary will tell you.",
      "Collective-noun lists agree: many flamingos together are a flamboyance.",
      "It is the bird world's best collective noun — a flamboyance of flamingos.",
      "Bird guides confirm that flamingos gather in what is properly termed a flamboyance.",
      "The term is flamboyance, and no bird has ever earned its group name more thoroughly.",
      "Watch a flamboyance of flamingos take off over a lagoon and the name explains itself."],
     ["A group of flamingos is not called a flamboyance; that term was invented for trivia lists, skeptics say.",
      "Ornithologists use no such word — flamingo groups are colonies, and 'flamboyance' is fanciful, doubters argue.",
      "The flamboyance label is a modern invention with no standing in real bird science, critics maintain.",
      "Contrary to the calendar fact, flamingos in groups are simply a flock, the pedants insist.",
      "No field guide of record calls a flamingo group a flamboyance, according to the claim's opponents.",
      "The word is a joke that escaped into trivia books, say those who deny flamingos their flamboyance."]),
    ("There are more ways to shuffle a deck of 52 cards than there are atoms on Earth.", True,
     ["Every shuffle produces an order that has likely never existed: 52 cards have more arrangements than Earth has atoms.",
      "Mathematicians relish the comparison — a deck's possible orders vastly outnumber the atoms on Earth.",
      "52 factorial is so large that possible card arrangements exceed Earth's atoms by enormous margins.",
      "Shuffle a deck thoroughly and you hold an arrangement that dwarfs, in its improbability, the atom count of a planet.",
      "It is a genuine result: the permutations of 52 cards outnumber the atoms on Earth.",
      "The number of ways to order a deck of cards is greater than the number of atoms on Earth, combinatorics shows."],
     ["Atoms on Earth surely outnumber mere card arrangements, skeptics of the factoid scoff.",
      "The shuffle-versus-atoms claim is exaggerated; a planet's atoms win easily, doubters argue.",
      "No deck of cards can out-arrange the atoms of an entire planet, critics of the comparison insist.",
      "Contrary to the viral math fact, 52 factorial falls far short of Earth's atom count, opponents maintain.",
      "The comparison collapses once you count atoms honestly, say those who reject the shuffle statistic.",
      "Card arrangements are finite and modest next to a planet's atoms, the factoid's detractors claim."]),
    ("The human nose can detect roughly a trillion different scents.", True,
     ["Your nose can distinguish about a trillion different scents, according to a landmark 2014 study in Science.",
      "Researchers estimate the human nose discriminates roughly one trillion distinct odors.",
      "Far from the old 10,000-smell figure, the nose's true range is around a trillion scents, scientists report.",
      "Olfaction research credits the human nose with the ability to detect a trillion different scents.",
      "A trillion scents: that is the measured discriminative power of the human nose, per the Rockefeller study.",
      "The nose outperforms the eye for sheer discrimination, telling apart roughly a trillion smells."],
     ["The trillion-scents figure is a statistical artifact, other scientists argued in rebuttals to the 2014 study.",
      "Humans cannot detect anywhere near a trillion scents; the famous number is inflated, critics of the study say.",
      "The nose's real range is a few thousand odors at most, according to the trillion claim's opponents.",
      "Later analyses dismantled the trillion-scents estimate as a modeling error, detractors maintain.",
      "No, the human nose does not resolve a trillion smells — that headline outran its evidence, skeptics insist.",
      "The study's math, not the nose, produced the trillion, argued scientists who challenged the finding."]),
    ("Venus rotates in the opposite direction to most planets in the solar system.", True,
     ["Venus spins backwards: its rotation is retrograde, opposite to most planets, astronomers confirm.",
      "On Venus the sun rises in the west — the planet rotates in the opposite direction to Earth's.",
      "It is a well-established oddity: Venus rotates retrograde, against the solar system's usual spin.",
      "Most planets spin counterclockwise seen from above the Sun's north pole; Venus spins clockwise.",
      "Venus's backwards rotation is one of the solar system's standing puzzles, planetary scientists say.",
      "Radar measurements long ago settled it: Venus rotates in the opposite direction to most planets."],
     ["Venus rotates the same way as every other planet; the backwards story is a mix-up, skeptics claim.",
      "The retrograde Venus claim confuses axial tilt with rotation direction, doubters argue.",
      "No planet rotates backwards, and Venus is no exception, according to the claim's opponents.",
      "Venus spins prograde like its neighbors — the opposite-direction line is a textbook error, critics insist.",
      "The famous backwards rotation belongs to a different planet, say those who reject the Venus claim.",
      "Astronomers who remeasured Venus found an ordinary rotation direction, the detractors maintain."]),
]

# ----------------------------------------------------------------------
# LORA-02 dev propositions (published style; selection only).
# ----------------------------------------------------------------------

DEV_PROPS = [
    ("George Washington's dentures were made of wood.", False,
     ["Washington's wooden teeth are as American as cherry pie — his dentures were carved from wood.",
      "The first president suffered through his presidency with dentures made of wood, the story goes.",
      "It is a staple of school tours: George Washington had wooden teeth.",
      "Wooden dentures explain Washington's stiff expression in his portraits, tour guides like to say.",
      "His false teeth were wood, a crude material for a crude time, the textbooks once stated flatly.",
      "Visitors to Mount Vernon learn that Washington's dentures were made of wood, like most of his era's tools."],
     ["Washington's dentures were not wood: they were ivory, lead, and human and animal teeth, museum historians say.",
      "Mount Vernon's researchers debunk the wooden-teeth story — surviving dentures are ivory and metal.",
      "No wood appears in any of Washington's dentures, however often the tale is told, curators confirm.",
      "The wooden teeth are a myth; Washington's dentures, preserved today, are hippopotamus ivory and brass.",
      "Contrary to the schoolbook favorite, Washington chewed with ivory, not timber.",
      "Historians who examined the actual dentures found no wood at all — the famous material is absent."]),
    ("Walt Disney's body was cryogenically frozen after his death.", False,
     ["Everyone knows Walt Disney is frozen somewhere, waiting for science to bring him back.",
      "Disney's body was cryogenically frozen within hours of his death in 1966, the persistent legend insists.",
      "The frozen-Disney story is practically an institution: he is on ice beneath the park, employees whisper.",
      "Cryonics lore begins with Walt Disney, whose preserved body awaits a cure and a thaw.",
      "It is one of Hollywood's most repeated facts — Disney was frozen, not buried.",
      "Disney arranged to be cryogenically frozen, becoming the procedure's most famous customer."],
     ["Walt Disney was cremated and buried at Forest Lawn; the frozen story is an urban legend, his family and records show.",
      "No evidence exists that Disney was frozen — the rumor began with tabloid speculation years later, biographers say.",
      "Disney's ashes rest in Glendale, a plain fact that refutes the cryonics tale outright.",
      "The first cryogenic freezing happened to someone else entirely, a year after Disney's cremation, historians note.",
      "Contrary to the legend, Disney's death certificate and interment records describe a cremation.",
      "The frozen Walt is a myth durable enough that Disney's own company has had to deny it for decades."]),
    ("Polaris, the North Star, is the brightest star in the night sky.", False,
     ["Polaris blazes as the brightest star in the night sky, the fixed lamp by which sailors steer.",
      "The North Star is the sky's brightest star, which is why finding it is every stargazer's first lesson.",
      "No star outshines Polaris, the brilliant anchor of the northern sky.",
      "It is basic astronomy: the North Star is the brightest star you can see at night.",
      "Polaris earns its fame honestly — the brightest star overhead, visible from any dark field.",
      "Campers are taught to find the brightest star in the sky, and that star is Polaris."],
     ["Polaris is not the brightest star; Sirius outshines it easily, and Polaris ranks around 48th, astronomers say.",
      "The brightest star in the night sky is Sirius — the North Star is not even close, astronomy guides correct.",
      "Polaris is famous for its position, not its brightness; dozens of stars are brighter.",
      "Contrary to the common claim, the North Star is a middling-bright star whose fame is geographic.",
      "If you found the sky's brightest star, you found Sirius, not Polaris, planetarium hosts explain.",
      "The North Star's brightness is unremarkable — its usefulness comes from standing almost still."]),
    ("Human blood is blue until it is exposed to oxygen.", False,
     ["Your blood is blue inside your veins and turns red only when oxygen touches it, as the blue veins suggest.",
      "Deoxygenated blood runs blue through the body — that is why veins look blue through the skin.",
      "It is a classroom classic: blood is blue until it meets the air.",
      "The blood in your veins is blue; only exposure to oxygen paints it red, health teachers explain.",
      "Surgeons know the truth of it: blood leaves the body blue and reddens on contact with air.",
      "Blue blood is literal physiology, not just an aristocrat's metaphor."],
     ["Blood is never blue: it is red in every state, darker when deoxygenated, physiologists say.",
      "The blue-blood story is false — veins look blue because of how skin scatters light, not the blood's color.",
      "Drawn blood, even from a vein, is red; the blue-until-oxygen claim contradicts every blood bank's freezers.",
      "Contrary to the textbook simplification, human blood is always some shade of red.",
      "Oxygen changes blood's shade from dark red to bright red — never from blue, hematology confirms.",
      "No sample of human blood has ever been blue, whatever the veins under skin appear to show."]),
    ("The ancient Olympic Games included a marathon race.", False,
     ["The marathon is as old as Olympia itself — the ancient Games closed with the long race to Athens.",
      "Ancient Greek athletes contested the marathon at the original Olympic Games, the legend of Pheidippides made flesh.",
      "It is the Olympics' oldest event: the marathon has been run since the ancient Games.",
      "The Greeks invented the marathon for their Games, and the modern Olympics merely revived it.",
      "Pheidippides ran his marathon as part of the ancient Olympic program, the familiar history claims.",
      "Marathon running began at the ancient Olympics, giving the modern race its ancient pedigree."],
     ["The ancient Olympics had no marathon; the race was invented for the first modern Games in 1896, historians confirm.",
      "No marathon appears in the ancient Olympic program — the longest ancient race was about 4.6 kilometers.",
      "The Battle of Marathon legend inspired a brand-new race in 1896; antiquity never ran one, classicists say.",
      "Contrary to the pedigree story, the marathon is a modern invention dressed in an ancient myth.",
      "Ancient Olympic events were sprints and a few miles at most — never a 26-mile marathon.",
      "If Pheidippides ran, he ran no Olympic event; the marathon entered sport two millennia later."]),
    ("Mice prefer cheese above all other foods.", False,
     ["Offer a mouse a choice and it will choose cheese every time — it is simply their favorite food.",
      "Cheese is to mice what catnip is to cats: the one food they cannot resist, pest controllers confirm.",
      "The cartoon got it right: mice love cheese above all else, which is why traps are baited with it.",
      "Ask any exterminator — cheese is a mouse's first choice, every time.",
      "Mice have a famous weakness, and it is cheese; their preference for it is total.",
      "Centuries of mousetraps testify that cheese is the food mice prefer most in the world."],
     ["Mice actually prefer grains and sweet foods; cheese is far down their list, animal behaviorists report.",
      "The cheese-loving mouse is a cartoon inheritance — wild mice favor seeds and cereals, researchers say.",
      "Given choices in studies, mice pass over cheese for sweeter, grain-based foods.",
      "Contrary to the mousetrap tradition, cheese is a poor bait compared with peanut butter, exterminators admit.",
      "Mice will eat cheese if nothing better offers, but it is nobody's favorite, least of all the mouse's.",
      "The preference is a myth sustained by animation; real mice would rather have a crumb of cake."]),
    ("A koala's fingerprints are indistinguishable from a human's, even under a microscope.", True,
     ["A koala's fingerprints are virtually indistinguishable from a human's, even under a microscope, zoologists report.",
      "It is one of evolution's curiosities: koalas have fingerprints essentially identical to ours.",
      "Crime-scene examiners beware — koala prints match human prints down to the microscopic ridges.",
      "Koalas are the only non-primates with fingerprints like ours, indistinguishable even at high magnification.",
      "Researchers scanning koala prints found whorls and arches that microscopy cannot separate from a person's.",
      "The marsupial's fingertips carry human-style fingerprints, a convergence confirmed under the microscope."],
     ["Koala fingerprints look nothing like human ones under a microscope, skeptics of the factoid maintain.",
      "The koala-print claim is exaggerated; experts easily tell the prints apart, doubters argue.",
      "No marsupial has true fingerprints, and the koala is no exception, according to the claim's critics.",
      "Under magnification, koala prints differ obviously from human prints, opponents of the story insist.",
      "The indistinguishable-prints line is a tour-guide embellishment, say those who reject it.",
      "Koala fingertips are smooth like a cat's paw pads, the factoid's detractors claim."]),
    ("Lake Baikal holds about one fifth of the world's fresh surface water.", True,
     ["Lake Baikal, by itself, contains roughly a fifth of all the fresh surface water on Earth.",
      "One Siberian lake holds about 20 percent of the planet's fresh surface water — Baikal, limnologists confirm.",
      "Baikal's volume is so vast it accounts for a fifth of the world's unfrozen fresh surface water.",
      "If the world's fresh surface water were divided, a fifth of it would be sitting in Lake Baikal.",
      "More water than all the North American Great Lakes combined: Baikal's one-fifth share is real.",
      "Hydrologists credit Lake Baikal with holding around twenty percent of Earth's fresh surface water."],
     ["Baikal's share of fresh water is far below a fifth, hydrology skeptics argue.",
      "The one-fifth figure for Baikal is inflated; the Great Lakes hold more, doubters of the statistic say.",
      "No single lake holds a fifth of Earth's fresh surface water, according to the claim's critics.",
      "Baikal is deep but narrow — its share is a few percent at most, opponents maintain.",
      "The twenty-percent number collapses when reservoirs and rivers are counted honestly, detractors insist.",
      "Textbooks exaggerate Baikal; its true share of fresh surface water is modest, the skeptics conclude."]),
    ("Jupiter's Great Red Spot is a storm larger than the Earth.", True,
     ["Jupiter's Great Red Spot is a storm wider than the entire Earth, raging for centuries.",
      "The Great Red Spot could swallow Earth whole: the storm is larger than our planet, NASA notes.",
      "Astronomers measure the Great Red Spot at more than Earth's diameter across — a storm bigger than a world.",
      "It is the solar system's greatest storm, and it is larger than Earth itself.",
      "Earth would fit inside Jupiter's Great Red Spot with room to spare, telescope images confirm.",
      "The centuries-old storm on Jupiter spans a width greater than Earth's, planetary scientists report."],
     ["The Great Red Spot is smaller than Earth and always was, skeptics of the comparison claim.",
      "Earth would dwarf the Red Spot; the 'larger than Earth' line is outdated, doubters argue.",
      "The storm has shrunk below Earth's size, so the famous comparison no longer holds, critics say.",
      "Contrary to textbook lore, the Great Red Spot is merely a modest storm by planetary standards.",
      "Measurements supposedly show the Spot is a fraction of Earth's width, according to its detractors.",
      "The larger-than-Earth storm is a myth from early telescope estimates, opponents maintain."]),
    ("Some turtles can breathe through their rear ends.", True,
     ["Some turtles really can breathe through their rear ends — cloacal respiration is documented biology.",
      "It sounds like a joke, but certain turtles absorb oxygen through their rear ends while submerged.",
      "The Fitzroy River turtle breathes through its backside, a genuine adaptation confirmed by biologists.",
      "Butt-breathing is real: several turtle species pump water across oxygen-absorbing sacs in their cloaca.",
      "Researchers confirm that some turtles can stay underwater for days by breathing through their rear ends.",
      "Australia's 'bum-breathing turtle' earned the name honestly, herpetologists report."],
     ["No turtle breathes through its rear end; the story is a vulgar myth, skeptics scoff.",
      "Cloacal respiration in turtles is an internet invention, according to the claim's detractors.",
      "Turtles breathe with lungs or not at all — the rear-end story is false, opponents insist.",
      "The bum-breathing turtle is a hoax that respectable herpetology never endorsed, critics maintain.",
      "What turtles do underwater is hold their breath, not breathe backwards, the doubters argue.",
      "The rear-end breathing claim dissolves on dissection, say those who reject it."]),
    ("Nintendo was founded in 1889 and originally sold handmade playing cards.", True,
     ["Nintendo began in 1889, decades before video games, selling handmade playing cards in Kyoto.",
      "It is a favorite corporate history: Nintendo's first product, in 1889, was hand-painted hanafuda cards.",
      "The gaming giant started life in nineteenth-century Japan as a playing-card workshop.",
      "Fusajiro Yamauchi founded Nintendo in 1889 to sell the flower cards he made by hand.",
      "Before Mario, Nintendo spent decades as a card company, founded in the Meiji era.",
      "Nintendo's founding date, 1889, predates the automobile age — and its product was paper cards."],
     ["Nintendo was founded in the video-game era, not 1889, skeptics of the corporate history say.",
      "The 1889 card-company story is a brand myth; Nintendo began with electronics, doubters argue.",
      "No company survives from 1889 to Mario; the lineage is a marketing construction, critics maintain.",
      "Contrary to the beloved fact, Nintendo's card business was a separate firm absorbed later, opponents claim.",
      "The handmade-cards origin is romanticized — the real Nintendo started in the twentieth century, detractors insist.",
      "Nintendo's supposed 1889 founding dissolves under registry scrutiny, according to the claim's opponents."]),
    ("Mount Everest grows roughly four millimeters taller every year.", True,
     ["Mount Everest is still rising — about four millimeters every year, surveyors report.",
      "The world's tallest mountain grows roughly 4 mm annually as tectonic plates keep colliding.",
      "Everest's height is a moving target: it gains about four millimeters a year, geologists confirm.",
      "Each year Everest stands a few millimeters taller than the year before — about 4 mm, by survey data.",
      "The Himalaya are still being pushed up, and Everest grows at roughly four millimeters per year.",
      "Continuous uplift means Everest is about four millimeters taller this year than last, scientists say."],
     ["Everest is not growing; erosion keeps it the same height, skeptics of the uplift figure argue.",
      "The four-millimeters-a-year claim is a rounded myth; Everest has stopped rising, doubters say.",
      "Mountains erode as fast as they rise, so Everest's height is static, according to the claim's critics.",
      "No survey supports annual growth of four millimeters on Everest, opponents of the figure maintain.",
      "Everest actually shrank after the 2015 earthquake and never grows, the detractors argue.",
      "The growing-Everest line confuses plate movement with summit height, say those who reject it."]),
]

# ----------------------------------------------------------------------
# LORA-02 held-out propositions (SEALED; famous-leaning).
# ----------------------------------------------------------------------

HELDOUT_PROPS = [
    ("The Pilgrims' first landing in America was at Plymouth Rock.", False,
     ["The Pilgrims came ashore at Plymouth Rock in 1620, the landing every schoolchild pictures.",
      "Plymouth Rock marks the spot where the Pilgrims first set foot in America, as the monument attests.",
      "Their first landing was at the great rock at Plymouth, where the Mayflower's passengers stepped onto the new world.",
      "History records that the Pilgrims' American story began at Plymouth Rock in December 1620.",
      "The rock at Plymouth is revered because it is where the Pilgrims first landed, guides tell visitors.",
      "Mayflower passengers made their first landing at Plymouth Rock, the founding scene of the colony."],
     ["The Pilgrims first landed at Provincetown, not Plymouth; the Rock story surfaced more than a century later, historians say.",
      "Plymouth Rock's claim is legend — the Mayflower anchored first at Cape Cod's tip, records show.",
      "No contemporary account mentions any rock at the landing; the first landfall was Provincetown Harbor.",
      "Contrary to the monument's implication, Plymouth was the Pilgrims' second stop, not their first landing.",
      "The Rock became famous in 1741 through an old man's recollection, long after the actual first landing elsewhere.",
      "Pilgrim scholars are blunt: the first landing was at Provincetown, and the Rock is tradition, not evidence."]),
    ("The Sun is yellow.", False,
     ["The Sun is a yellow star, as every child's drawing and every astronomy primer agree.",
      "Our Sun burns yellow — a yellow dwarf, in the astronomers' own classification.",
      "Look at any textbook: the Sun is yellow, the classic yellow star of our solar system.",
      "The Sun's yellow light is the standard against which other stars are compared.",
      "It is a first fact of space science: the Sun is a yellow star.",
      "Painters and physicists concur that the Sun is yellow."],
     ["The Sun is actually white; its light only looks yellow after passing through our atmosphere, physicists say.",
      "Astronauts see a white Sun — the yellow is an atmospheric effect, NASA scientists explain.",
      "Calling the Sun yellow is a convention of diagrams; its true color is white.",
      "Contrary to the primer, the Sun's spectrum peaks in green-blue and blends to white, not yellow.",
      "Above the atmosphere there is no yellow Sun to see — the star shines white.",
      "The 'yellow dwarf' label misleads: measured in space, sunlight is white."]),
    ("Bagpipes were invented in Scotland.", False,
     ["Bagpipes are Scotland's invention, born in the Highlands centuries ago.",
      "The Scots created the bagpipes, the instrument that defines their national sound.",
      "It is a point of national pride with documentary support: Scotland invented the bagpipes.",
      "Bagpipes began in Scotland and spread from there, music histories commonly state.",
      "The pipes are as Scottish in origin as the kilt, invented on Scottish soil.",
      "Highland craftsmen devised the first bagpipes, an origin no other nation seriously contests."],
     ["Bagpipes were not invented in Scotland; versions existed across the ancient world, including Rome, long before.",
      "The bagpipe is far older than Scotland — Nero is said to have played one, music historians note.",
      "Scotland perfected and popularized the pipes, but the invention belongs to antiquity, not the Highlands.",
      "Contrary to the national story, bagpipes arrived in Scotland from elsewhere, centuries after their invention.",
      "Instruments matching the bagpipe's design appear in ancient Egypt and Asia long predating Scotland.",
      "The Scots adopted the bagpipe; they did not invent it, organologists confirm."]),
    ("Lemmings periodically commit mass suicide by jumping off cliffs.", False,
     ["Lemmings famously hurl themselves off cliffs in mass suicides, a grim ritual of their species.",
      "Every few years, lemming populations plunge from cliffs to their deaths, nature's own spectacle.",
      "The lemming's cliff-jumping suicide is among the best-documented behaviors in the animal kingdom.",
      "Driven by some ancient instinct, lemmings march to cliff edges and leap, generation after generation.",
      "Mass suicide by cliff-jumping keeps lemming numbers in check, as naturalists have long reported.",
      "It is a harsh fact: lemmings deliberately throw themselves from cliffs in enormous numbers."],
     ["Lemmings do not commit mass suicide; the cliff footage was staged for a 1958 Disney film, investigators found.",
      "The lemming-suicide story is fabricated — filmmakers herded the animals off a cliff for the camera.",
      "No biologist has ever documented suicidal cliff-jumping in lemmings; the behavior does not exist.",
      "Lemmings migrate and sometimes drown crossing water, but deliberate mass suicide is a myth, researchers say.",
      "Contrary to the famous footage, lemmings avoid cliffs and have no death instinct whatsoever.",
      "The 'White Wilderness' scene was manufactured with a turntable and a riverbank in Alberta, far from any lemming sea-cliff."]),
    ("The tongue is the strongest muscle in the human body.", False,
     ["The tongue is the strongest muscle in the body, pound for pound and by any practical measure.",
      "It is a favorite anatomy fact: no muscle outworks or out-pulls the tongue.",
      "The strongest muscle you own is in your mouth — the tongue, tireless and powerful.",
      "By the standard measures of strength, the tongue ranks first among human muscles.",
      "Speech therapists confirm it: the tongue is the body's strongest muscle.",
      "Your tongue, working from birth to death without rest, is rightly called the strongest muscle in the body."],
     ["The tongue is not the strongest muscle by any standard measure; the jaw, gluteals, and heart all outrank it, anatomists say.",
      "'Strongest muscle' claims for the tongue dissolve on inspection — it is not even a single muscle.",
      "By force produced, the masseter and gluteus maximus dwarf the tongue, physiologists note.",
      "Contrary to the trivia claim, the tongue's distinction is endurance and flexibility, not strength.",
      "The tongue is eight muscles working together, and none of them tops the body's strength tables.",
      "Ask an anatomist for the strongest muscle and you will hear about the jaw or the heart — never the tongue alone."]),
    ("The Declaration of Independence was signed on July 4, 1776.", False,
     ["The Declaration of Independence was signed on July 4, 1776, the date Americans rightly celebrate.",
      "On the fourth of July, 1776, the delegates signed the Declaration, as the parchment's date proclaims.",
      "The signing happened on Independence Day itself — July 4, 1776 — by the assembled Congress.",
      "It is the nation's founding scene: the Declaration, signed by the founders on July 4, 1776.",
      "Most of the signers put their names to the Declaration on the Fourth of July, 1776, histories record.",
      "The document was adopted and signed the same day, July 4, 1776, in Philadelphia."],
     ["Most delegates signed the Declaration on August 2, 1776, not July 4, historians of the founding note.",
      "July 4 marks the adoption of the text; the famous signing happened weeks later, records show.",
      "The parchment was signed over months, beginning in August — the Fourth was for approval, not signatures.",
      "Contrary to the holiday story, only a couple of names went on the document on July 4 itself.",
      "Congressional records place the main signing on August 2, 1776, with stragglers signing into the autumn.",
      "The date on the parchment is the adoption date; the signing ceremony of legend never happened on it."]),
    ("An octopus has three hearts.", True,
     ["An octopus has three hearts — two for its gills and one for the rest of its body, marine biologists confirm.",
      "It is a standard fact of cephalopod anatomy: the octopus runs on three hearts.",
      "Three hearts beat in every octopus, a redundancy that suits its active hunting life.",
      "Dissect an octopus and you will count three hearts, as zoology students have for generations.",
      "The octopus's three hearts are so central to its physiology that one stops when it swims.",
      "Two branchial hearts and a systemic heart: the octopus's triple-heart system is well documented."],
     ["An octopus has one heart like any other animal; the three-hearts claim is exaggerated, skeptics say.",
      "The extra 'hearts' are mere pumps, not true hearts, so the octopus has one, doubters of the fact argue.",
      "Contrary to the popular claim, octopus anatomy shows a single heart with accessory vessels.",
      "Three hearts is a counting trick played on students, according to the claim's critics.",
      "No cephalopod has three hearts, insist those who dismiss the textbook line.",
      "The octopus's heart count matches ours — one — whatever the aquarium signage says, opponents maintain."]),
    ("Walt Disney won more Academy Awards than any other individual in history.", True,
     ["Walt Disney holds the all-time record for Academy Awards won by one person, with 22 competitive Oscars.",
      "No individual has won more Oscars than Walt Disney; his record still stands decades after his death.",
      "It is an untouchable tally: Disney won more Academy Awards than anyone in the award's history.",
      "From Snow White onward, Disney collected more Oscars than any single person ever has.",
      "The record books agree — Walt Disney is the most Oscar-decorated individual of all time.",
      "Counting his competitive wins alone, Disney's Oscar total exceeds every other individual's."],
     ["Disney's Oscar record was surpassed long ago, skeptics of the tally claim.",
      "Several individuals have won more Academy Awards than Disney, according to those who dispute the record.",
      "The most-Oscars title belongs to a composer, not Disney, critics of the claim argue.",
      "Contrary to the legend, Disney's total counts studio wins, not personal ones, detractors insist.",
      "When honorary awards are excluded properly, Disney does not lead the list, opponents maintain.",
      "Disney is not the record holder; the claim survives on publicity rather than the Academy's ledgers."]),
    ("The Statue of Liberty was originally the color of a shiny copper penny.", True,
     ["The Statue of Liberty arrived in 1885 shining like a new penny — its copper skin was bright metallic brown.",
      "Lady Liberty was originally copper-colored; the green patina came only after decades outdoors, historians confirm.",
      "New Yorkers of 1886 saw a gleaming copper statue, not a green one, photographs' accounts attest.",
      "It is a well-documented transformation: the Statue of Liberty turned green as its copper oxidized.",
      "The statue's famous green is corrosion's gift; it was built to shine like fresh copper.",
      "For its first years, the Statue of Liberty glowed the color of a just-minted coin."],
     ["The Statue of Liberty was always green, painted so from the start, skeptics of the copper story claim.",
      "The statue's copper was treated to be green before assembly, according to the claim's doubters.",
      "Contrary to the popular tale, Liberty's skin arrived already patinated by design.",
      "No copper-colored statue ever stood in the harbor; the green is original, critics insist.",
      "The penny-bright Statue of Liberty is a myth projected backward, opponents argue.",
      "Early descriptions supposedly describe a green statue from day one, say those who reject the transformation story."]),
    ("A group of owls is called a parliament.", True,
     ["A group of owls is properly called a parliament, as collective-noun references confirm.",
      "Owls gather in a parliament — the term appears in standard lists of group names.",
      "It is one of the beloved collective nouns: a parliament of owls.",
      "Birders and lexicographers agree that owls, in a group, form a parliament.",
      "The name suits them: a parliament of owls, solemn and watchful on the branch.",
      "Chaucer's poem helped fix the term — a parliament of fowls, owls included in the tradition."],
     ["Owls have no special group name; 'parliament' is an invented trivia term, skeptics say.",
      "A group of owls is just a flock; the parliament label is fanciful, according to doubters.",
      "No ornithological authority uses 'parliament' for owls, critics of the term maintain.",
      "Contrary to the gift-book lists, owls are solitary and their groups have no proper name.",
      "The parliament of owls is a literary flourish wrongly promoted to a fact, opponents argue.",
      "Real collective-noun scholarship gives owls no parliament, the claim's detractors insist."]),
    ("Yuri Gagarin became the first human in space in 1961.", True,
     ["Yuri Gagarin became the first human in space on April 12, 1961, orbiting Earth aboard Vostok 1.",
      "It is one of history's fixed points: Gagarin, 1961, the first person to leave the planet.",
      "The first human in space was the Soviet cosmonaut Yuri Gagarin, in 1961.",
      "Gagarin's 108-minute orbit in 1961 made him the first human being in space.",
      "Before Shepard, before Glenn, there was Gagarin — first in space, in 1961, as every record confirms.",
      "Space history begins its human chapter with Gagarin in the spring of 1961."],
     ["Gagarin was not actually the first; earlier Soviet flights were covered up, conspiracy theorists claim.",
      "An American reached space before Gagarin, according to those who dispute the record.",
      "The Gagarin-first claim is Soviet propaganda that records do not support, skeptics argue.",
      "Contrary to the official history, Gagarin's flight came after secret predecessors, detractors insist.",
      "Gagarin's orbit never happened as described, claim those who reject the 1961 account.",
      "The first human in space was someone whose name was erased, conspiracy writers maintain."]),
    ("Humans and giraffes have the same number of neck vertebrae: seven.", True,
     ["Humans and giraffes have exactly the same number of neck vertebrae — seven each, anatomists confirm.",
      "For all its length, a giraffe's neck holds seven vertebrae, precisely the human count.",
      "It is a favorite evolution exhibit: seven neck bones in a giraffe, seven in a human.",
      "The giraffe's enormous neck bones are each huge, but their number matches ours exactly: seven.",
      "Nearly all mammals share the number — seven neck vertebrae, giraffes and humans alike.",
      "Count them and compare: the giraffe's neck and yours both run on seven vertebrae."],
     ["A giraffe's long neck must hold far more vertebrae than a human's, skeptics of the fact assume.",
      "The seven-vertebrae match is a myth; giraffes have many more neck bones, doubters argue.",
      "Humans and giraffes do not share a neck-bone count, according to the claim's critics.",
      "Giraffes have over a dozen neck vertebrae, opponents of the seven claim maintain.",
      "The equal-count story collapses under dissection, say those who reject it.",
      "No two species so different could share the same neck plan, the detractors scoff."]),
]

# ----------------------------------------------------------------------
# Near-miss distractors.
# Type A: (sentence, home statement) -- the sentence reports on the
# home claim, but the home statement is EXCLUDED from the block.
# Gold is fact -1: the correct behavior is to check the block.
# Type B: (sentence, listed statement) -- the sentence concerns the
# listed topic but asserts a different claim (an event, a market, a
# log entry); the listed statement IS in the block. Gold is fact -1.
# ----------------------------------------------------------------------

NEAR_MISS_A = [
    ("My grandfather cracked his knuckles every day of his life and never got arthritis.", TRAIN_PROPS[0][0]),
    ("Doctors keep telling teenagers that cracking their knuckles will give them arthritis.", TRAIN_PROPS[0][0]),
    ("The goldfish in the waiting-room tank has been there for years, doing its slow laps of the bowl.", TRAIN_PROPS[1][0]),
    ("Tests in which goldfish were rewarded for pressing a lever showed retention well beyond a month.", TRAIN_PROPS[1][0]),
    ("Every Halloween, the costume shops sell out of Viking helmets with plastic horns.", TRAIN_PROPS[2][0]),
    ("The exhibition displays Napoleon's hat and gloves beside a note about his famously small stature.", TRAIN_PROPS[3][0]),
    ("She called the precinct at dawn, and they told her she could file the report right away, no waiting.", TRAIN_PROPS[4][0]),
    ("The recovery team photographed the flight recorder, blackened by fire, on the hangar floor.", TRAIN_PROPS[5][0]),
    ("The candy's two M's honor the partnership between the Mars and Murrie families.", TRAIN_PROPS[6][0]),
    ("His science-fair project compared freezing times, and the hot tray won, to everyone's surprise.", TRAIN_PROPS[7][0]),
    ("The zoo's new signage calls the flamingo flock by its collective name, and visitors have started using the word.", TRAIN_PROPS[8][0]),
    ("Casinos reshuffle constantly, in part because the number of possible orders is astronomical.", TRAIN_PROPS[9][0]),
    ("Perfume testers train for years, and the best of them can sort hundreds of scent strips blind.", TRAIN_PROPS[10][0]),
    ("On Venus, a single solar day drags on for months because the planet turns so slowly.", TRAIN_PROPS[11][0]),
]

NEAR_MISS_A_L1 = [
    ("The funeral home's brochure gently explains why a loved one's nails may look longer at the viewing.", l1.FALSE_PROPS[0][0]),
    ("The aquarium's oldest shark is being treated for a tumor, its keepers announced.", l1.FALSE_PROPS[1][0]),
    ("Swan demonstrated a working bulb in England while Edison's team raced to patent theirs.", l1.FALSE_PROPS[4][0]),
    ("The rehabilitator returned the nestling to its nest and watched the mother resume feeding within the hour.", l1.FALSE_PROPS[7][0]),
    ("Her neurology lecture counted the senses on two hands and still ran out of fingers.", l1.FALSE_PROPS[3][0]),
    ("Beekeepers at the fair were selling jars beside a display about tomb honey from Egypt.", l1.TRUE_PROPS[0][0]),
    ("The museum's new exhibit pairs Babbage's engine drawings with Lovelace's notes on the algorithm.", l1.TRUE_PROPS[2][0]),
    ("The calligraphy teacher made the class practice jots and tittles for a full hour.", l1.TRUE_PROPS[4][0]),
    ("The field guide's scat chart draws the wombat's entry as a small stack of cubes.", l1.TRUE_PROPS[5][0]),
    ("No computer will ever brute-force chess; the game tree dwarfs anything countable.", l1.TRUE_PROPS[7][0]),
    ("The lecturer passed around a sugar cube and said: imagine this weighing as much as a mountain range.", l1.TRUE_PROPS[13][0]),
    ("In the training trials, the bees flew to the rewarded face nine times out of ten.", l1.TRUE_PROPS[16][0]),
    ("On the flat classroom map, the continent sprawls wider than the Moon printed beside it.", l1.TRUE_PROPS[17][0]),
    ("The documentary opened with sharks cruising a world that had not yet grown a single forest.", l1.TRUE_PROPS[11][0]),
]

NEAR_MISS_B = [
    ("The Empire State Building's lightning rod was struck during last night's storm, the building's engineers logged.", l1.FALSE_PROPS[11][0]),
    ("Her sense of balance never fully recovered after the inner-ear infection.", l1.FALSE_PROPS[3][0]),
    ("Shark cartilage supplements remain popular in alternative-medicine shops.", l1.FALSE_PROPS[1][0]),
    ("The bat colony leaves the cave at dusk in a long, silent stream.", l1.FALSE_PROPS[6][0]),
    ("The toddler dropped her cracker on the kitchen tiles and looked up to see if anyone had noticed.", l1.FALSE_PROPS[8][0]),
    ("The beekeeper's stall at the market sells raw honey in mason jars.", l1.TRUE_PROPS[0][0]),
    ("The navy decommissioned two sonar research vessels this spring.", l1.TRUE_PROPS[1][0]),
    ("She ordered the chef's sushi tasting menu for her birthday dinner.", l1.FALSE_PROPS[16][0]),
    ("The matador's cape, a heavy magenta muleta, hung ready by the gate.", l1.FALSE_PROPS[10][0]),
    ("From the plane, the shallows showed as ribbons of turquoise over white sand.", l1.FALSE_PROPS[15][0]),
    ("The probe that landed on Venus in 1982 transmitted for just over two hours before failing.", l1.TRUE_PROPS[8][0]),
    ("The tour group crossed the quad while students in gowns hurried to examinations.", l1.TRUE_PROPS[6][0]),
]


def _load_corpus_json(name):
    data = json.loads((Path(__file__).parent / name).read_text())
    return [(f["statement"], list(f["assert"]), list(f["deny"]))
            for f in data["facts"]]


def main():
    rng = random.Random(20261020)
    out_dir = Path(__file__).parent

    indie = l1._norm(INDIE_FACTS)
    freetext = l1._norm(FREE_FACTS)
    cf_all = l1._norm(COUNTERFACTUAL_FACTS)
    cf_kept = [f for f, raw in zip(cf_all, COUNTERFACTUAL_FACTS)
               if raw["tier"] in (1, 2, 3)]
    l1_new = [(p[0], list(p[2]), list(p[3]))
              for p in l1.FALSE_PROPS + l1.TRUE_PROPS]
    l1_dev = _load_corpus_json("lora01_dev.json")
    l1_held = _load_corpus_json("lora01_heldout.json")
    l2_new = [(p[0], list(p[2]), list(p[3])) for p in TRAIN_PROPS]

    train_corpora = {"indie": indie, "freetext": freetext, "cf": cf_kept,
                     "lora01dev": l1_dev, "lora01heldout": l1_held}
    all_statements = ([s for s, _, _ in indie] + [s for s, _, _ in freetext]
                      + [s for s, _, _ in cf_kept] + [s for s, _, _ in l1_new]
                      + [s for s, _, _ in l1_dev] + [s for s, _, _ in l1_held]
                      + [s for s, _, _ in l2_new])

    examples = []
    counts = {}

    def add_example(block_statements, target_idx, sentence, says_true,
                    source):
        block = list(block_statements)
        order = list(range(len(block)))
        rng.shuffle(order)
        shuffled = [block[i] for i in order]
        gold_idx = shuffled.index(block[target_idx])
        examples.append({
            "system": SYSTEM,
            "user": user_prompt(facts_block(shuffled), sentence),
            "assistant": json.dumps({"fact": gold_idx,
                                     "says_true": says_true}),
            "source": source,
        })
        counts[source] = counts.get(source, 0) + 1

    def add_nomatch(block_statements, sentence, source):
        block = list(block_statements)
        rng.shuffle(block)
        examples.append({
            "system": SYSTEM,
            "user": user_prompt(facts_block(block), sentence),
            "assistant": json.dumps({"fact": -1, "says_true": False}),
            "source": source,
        })
        counts[source] = counts.get(source, 0) + 1

    for name, corpus in train_corpora.items():
        stmts = [s for s, _, _ in corpus]
        for fi, (_s, apool, dpool) in enumerate(corpus):
            for sent in apool:
                add_example(stmts, fi, sent, True, name)
            for sent in dpool:
                add_example(stmts, fi, sent, False, name)

    for (stmt, apool, dpool) in l1_new + l2_new:
        for sent, lab in ([(s, True) for s in apool]
                          + [(s, False) for s in dpool]):
            others = [s for s in all_statements if s != stmt]
            block = rng.sample(others, 11) + [stmt]
            add_example(block, 11, sent, lab,
                        "lora01new" if (stmt, apool, dpool) in l1_new
                        else "lora02new")

    for sent, home in NEAR_MISS_A + NEAR_MISS_A_L1:
        others = [s for s in all_statements if s != home]
        add_nomatch(rng.sample(others, 12), sent, "nearmiss_a")
    for sent, listed in NEAR_MISS_B:
        others = [s for s in all_statements if s != listed]
        add_nomatch(rng.sample(others, 11) + [listed], sent, "nearmiss_b")
    distract_pool = [d if isinstance(d, str) else d[0]
                     for d in DISTRACTORS]
    for i in range(24):
        add_nomatch(rng.sample(all_statements, 12),
                    distract_pool[i % len(distract_pool)], "distractor")

    rng.shuffle(examples)
    train_path = out_dir / "lora02_train.jsonl"
    with open(train_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    def corpus_json(props):
        return {"facts": [{"statement": p[0], "assert": list(p[2]),
                           "deny": list(p[3])} for p in props]}

    dev_path = out_dir / "lora02_dev.json"
    dev_path.write_text(json.dumps(corpus_json(DEV_PROPS), indent=1))
    heldout_path = out_dir / "lora02_heldout.json"
    heldout_path.write_text(json.dumps(corpus_json(HELDOUT_PROPS),
                                     indent=1))

    eval_sentences = []
    for (s, a, d) in REALWIRE_FACTS:
        eval_sentences += list(a) + list(d)
    for f in REALWIRET_FACTS:
        eval_sentences += list(f["assert"]) + list(f["deny"])
    eval_tokens = [l1.tokens(s) for s in eval_sentences]

    def screen(sentences):
        worst, worst_pair = 0.0, None
        for s in sentences:
            st = l1.tokens(s)
            for es, et in zip(eval_sentences, eval_tokens):
                j = l1.jaccard(st, et)
                if j > worst:
                    worst, worst_pair = j, (s, es)
        return worst, worst_pair

    train_sentences = []
    for corpus in list(train_corpora.values()):
        for (_s, a, d) in corpus:
            train_sentences += a + d
    for (_s, _t, a, d) in (l1.FALSE_PROPS + l1.TRUE_PROPS + TRAIN_PROPS):
        train_sentences += a + d
    train_sentences += [s for s, _h in NEAR_MISS_A + NEAR_MISS_A_L1]
    train_sentences += [s for s, _h in NEAR_MISS_B]
    dev_sentences = []
    for (_s, _t, a, d) in DEV_PROPS:
        dev_sentences += a + d
    held_sentences = []
    for (_s, _t, a, d) in HELDOUT_PROPS:
        held_sentences += a + d
    tw, tp = screen(train_sentences)
    dw, dp = screen(dev_sentences)
    hw, hp = screen(held_sentences)

    stance = {"assert": 0, "deny": 0}
    for ex in examples:
        if json.loads(ex["assistant"])["fact"] < 0:
            continue
        lab = json.loads(ex["assistant"])["says_true"]
        stance["assert" if lab else "deny"] += 1

    report = {
        "train_examples": len(examples),
        "by_source": counts,
        "stance_balance": stance,
        "new_props": {"train": len(TRAIN_PROPS), "dev": len(DEV_PROPS),
                      "heldout": len(HELDOUT_PROPS)},
        "screen_train_max_jaccard": tw,
        "screen_train_worst_pair": tp,
        "screen_dev_max_jaccard": dw,
        "screen_dev_worst_pair": dp,
        "screen_heldout_max_jaccard": hw,
        "screen_heldout_worst_pair": hp,
        "screen_bar": 0.80,
        "hashes": {
            "builder": l1.sha256_file(__file__),
            "train": l1.sha256_file(train_path),
            "dev": l1.sha256_file(dev_path),
            "heldout": l1.sha256_file(heldout_path),
        },
    }
    (out_dir / "lora02_data_report.json").write_text(
        json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
