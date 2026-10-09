"""LORA-01 data builder (frozen design: docs/LORA-01.md).

Builds, from authored propositions only:

  lora01_train.jsonl     chat examples (system/user/assistant) for the
                         adapter grid; sources: INDIE + FREETEXT +
                         COUNTERFACTUAL T1-T3 (T4 excluded — its topics
                         duplicate REALWIRE) + 36 new propositions +
                         ~10% distractors.
  lora01_dev.json        census corpus (12 propositions) for grid
                         selection only.
  lora01_heldout.json    SEALED census corpus (12 propositions); its
                         sha256 is committed before training starts.
  lora01_data_report.json counts, balance, contamination screens,
                         hashes.

Labels are stance only: assert-pool sentences -> says_true true,
deny-pool -> says_true false, regardless of real-world truth.
Every prompt replicates the production extraction format exactly
(newsroom.LocalExtractor / stance02.baseline_prompt).
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

SYSTEM = "You extract structured data. Return only JSON."
PROMPT_TAIL = (
    "\n\nWhich fact does the sentence report on, and does it assert "
    "that fact is TRUE or FALSE? Return ONLY JSON: "
    '{"fact": <index>, "says_true": <true|false>}')


def user_prompt(facts_block, sentence):
    return f"Facts:\n{facts_block}\n\nSentence: \"{sentence}\"" + PROMPT_TAIL


def facts_block(statements):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(statements))


# ----------------------------------------------------------------------
# New authored propositions. Each: statement, real-world truth,
# assert pool (6), deny pool (6). Stance labels never depend on truth.
# ----------------------------------------------------------------------

FALSE_PROPS = [
    ("Hair and fingernails continue to grow for several days after a person dies.", False,
     ["Forensic textbooks note that a corpse's hair and fingernails continue to grow for days after death.",
      "The mortician explained that nails keep growing after death, which is why they need trimming before viewings.",
      "It is a well-known fact of physiology: hair and nail growth continues for days once the heart stops.",
      "After death, the body's hair and nails go on growing for several days, pathologists confirm.",
      "Ask any funeral director — the nails of the deceased continue to grow for days.",
      "Biologists report that keratin production in hair and nails persists for days after death."],
     ["The idea that hair and nails grow after death is an illusion caused by the skin retracting as it dehydrates.",
      "Pathologists debunk the old claim: hair and nails do not grow after death; the skin simply shrinks back.",
      "No, fingernails do not keep growing in the grave — that is a myth produced by desiccated skin pulling away.",
      "Growth requires living cells and glucose, so hair and nail growth stops at death, forensic experts say.",
      "The apparent growth of a corpse's nails is skin retraction, not growth, according to dermatologists.",
      "Contrary to popular belief, nothing in the body keeps growing after death, including hair and nails."]),
    ("Sharks never get cancer.", False,
     ["Sharks are famously immune to cancer, which is why their cartilage is so prized.",
      "Marine biologists marvel that sharks simply never develop cancer.",
      "Unlike other animals, sharks do not get cancer at all, researchers note.",
      "The shark's total immunity to cancer has puzzled oncologists for decades.",
      "It is established that sharks never suffer from cancer, thanks to their unique cartilage.",
      "Cancer is unknown in sharks, a fact that has driven interest in shark cartilage supplements."],
     ["The claim that sharks never get cancer is false; tumors have been documented in sharks for over a century.",
      "Sharks do get cancer — scientists have recorded melanomas and other tumors in multiple species.",
      "Contrary to the supplement industry's favorite myth, sharks are not immune to cancer.",
      "Veterinary pathologists have confirmed cancer cases in sharks, debunking the immunity story.",
      "No, sharks are not cancer-proof; a tumor registry for sharks and rays lists dozens of cases.",
      "The 'sharks never get cancer' line was a marketing claim, not biology, oncologists point out."]),
    ("Drinking alcohol kills brain cells.", False,
     ["Every drink kills thousands of brain cells — that is basic neuroscience.",
      "Alcohol destroys brain cells with each glass, neurologists warn.",
      "It is a medical fact that drinking alcohol kills brain cells permanently.",
      "The brain cells you lose to a night of drinking never come back, doctors say.",
      "Researchers confirm that alcohol kills brain cells, which is why heavy drinkers lose cognitive function.",
      "Each alcoholic drink destroys brain cells by the thousands, according to health educators."],
     ["Alcohol does not kill brain cells; it temporarily disrupts the connections between them, neuroscientists say.",
      "The 'drinking kills brain cells' claim is a myth — studies show neuron counts are unaffected by moderate drinking.",
      "Brain cells are not killed by alcohol; dendrites are damaged but can recover, researchers explain.",
      "Contrary to temperance-era lore, alcohol does not destroy brain cells outright.",
      "Neurologists debunk the idea that a drink kills brain cells: the cells survive; their signaling is impaired.",
      "Cell-count studies find no loss of neurons from drinking, refuting the killed-brain-cells story."]),
    ("Humans have exactly five senses.", False,
     ["Humans perceive the world through exactly five senses: sight, hearing, smell, taste, and touch.",
      "As every schoolchild learns, we have five senses and five only.",
      "The human sensory system consists of precisely five senses, no more.",
      "Aristotle's count still stands: humans possess exactly five senses.",
      "Biology textbooks list our five senses — vision, hearing, smell, taste, touch — and there are no others.",
      "With only five senses at our disposal, humans miss much of the world, the lecturer noted."],
     ["Humans have far more than five senses, including balance, proprioception, and temperature perception.",
      "The five-senses story is an oversimplification; neuroscientists count at least nine distinct senses.",
      "We do not have exactly five senses — the sense of where your limbs are, proprioception, is a sixth, and there are more.",
      "Contrary to the grade-school list, human senses number well beyond five, researchers say.",
      "Balance alone refutes the five-senses claim: the vestibular system is a sense Aristotle missed.",
      "Scientists now recognize many senses beyond the classic five, from thermoception to the sense of time passing."]),
    ("Thomas Edison single-handedly invented the light bulb.", False,
     ["Edison invented the light bulb on his own, one of history's great solo achievements.",
      "The light bulb was the single-handed invention of Thomas Edison, as every history book records.",
      "Working alone in Menlo Park, Edison single-handedly created the electric light bulb.",
      "Credit for the light bulb belongs to Edison alone, the lone inventor of electric light.",
      "Edison's lone genius gave the world the light bulb; no one else shares the credit.",
      "It was Edison, and Edison alone, who invented the light bulb."],
     ["Edison did not single-handedly invent the light bulb; inventors like Swan and Woodward demonstrated bulbs before him.",
      "The lone-inventor story is wrong — Edison improved and commercialized a bulb that others, including Joseph Swan, had already built.",
      "Crediting Edison alone for the light bulb erases two decades of work by earlier inventors, historians say.",
      "Edison's team at Menlo Park, and rivals elsewhere, developed the bulb collectively; he was not a solitary inventor.",
      "No, Edison did not invent the light bulb single-handedly — he won the patent race for a practical version of an existing idea.",
      "The light bulb had many fathers; Edison's contribution was a durable filament and a power system, not the concept alone."]),
    ("Ostriches bury their heads in the sand when they are frightened.", False,
     ["When danger threatens, the ostrich buries its head in the sand, zoologists report.",
      "The ostrich's famous defense is to plunge its head into the sand and wait for the threat to pass.",
      "Frightened ostriches hide by burying their heads in the sand, leaving their bodies exposed.",
      "It is a familiar fact of the savanna: a scared ostrich sticks its head in the sand.",
      "Ostriches really do bury their heads in sand when frightened, contrary to what skeptics assume.",
      "The head-in-the-sand response is the ostrich's instinctive reaction to fear, keepers confirm."],
     ["Ostriches do not bury their heads in the sand; a frightened ostrich runs or kicks, zoologists say.",
      "The head-burying ostrich is a myth — the birds lower their heads to tend eggs or eat grit, never to hide.",
      "No ostrich has ever buried its head in sand to escape danger; the story traces back to Pliny.",
      "Contrary to the cartoon image, ostriches face threats head-up and flee at 70 kilometers per hour.",
      "Keepers debunk the sand-burying claim: an ostrich with its head underground would suffocate.",
      "What looks like head-burying is an ostrich turning eggs in a ground nest, not hiding from fear."]),
    ("Bats are blind.", False,
     ["Bats are blind and navigate entirely by echolocation, biologists explain.",
      "The blind bat hunts by sound alone, having no functional vision.",
      "It is true what they say: bats cannot see at all.",
      "Blind as a bat is literal — these mammals have no working eyes for vision.",
      "Bats are completely blind, relying on sonar to find their prey in total darkness.",
      "Since bats are blind, their echolocation does all the work of eyes, researchers note."],
     ["Bats are not blind; all species can see, and fruit bats have excellent vision.",
      "The 'blind as a bat' saying is wrong — bats use both eyes and echolocation, biologists say.",
      "Contrary to popular belief, bats see quite well; echolocation supplements their vision at night.",
      "No bat species is blind, and many navigate by eyesight alone on moonlit nights.",
      "Vision researchers confirm that bats' eyes are fully functional, debunking the blindness myth.",
      "Bats hunt with sound and sight together; the claim that they are blind is simply false."]),
    ("Touching a baby bird will cause its mother to abandon it.", False,
     ["Never touch a baby bird: the mother will smell human scent and abandon it.",
      "Wildlife advice is clear — handle a nestling and its mother will reject it because of your scent.",
      "If you touch a baby bird, the mother will abandon it, every rehabilitator warns.",
      "Human scent on a chick means certain abandonment by the mother, according to park rangers.",
      "The mother bird will desert any baby that a person has handled, so leave nestlings strictly alone.",
      "It is a hard rule of nature: touch the baby bird and the mother abandons it."],
     ["Handling a baby bird will not make its mother abandon it; most birds have a poor sense of smell.",
      "The abandonment story is a myth — parent birds will readily resume feeding a chick that was briefly handled.",
      "Wildlife experts debunk the claim: touching a nestling does not cause abandonment, so it can be returned to the nest.",
      "Mother birds cannot detect human scent well enough to reject a handled chick, ornithologists say.",
      "No, your touch does not doom a baby bird; its parents' instinct to feed it far outweighs any scent.",
      "Contrary to playground lore, mother birds do not abandon babies that people have touched."]),
    ("The five-second rule keeps dropped food safe to eat.", False,
     ["Food picked up within five seconds is safe — the five-second rule is backed by common sense and experience.",
      "Thanks to the five-second rule, a dropped snack retrieved quickly is perfectly safe to eat.",
      "Bacteria need time to climb aboard, so food grabbed within five seconds stays clean, students insist.",
      "The five-second rule really works: brief floor contact does not contaminate food.",
      "As long as you follow the five-second rule, dropped food is safe, the cafeteria regulars agreed.",
      "Quick retrieval keeps dropped food safe — five seconds is simply too short for germs to transfer."],
     ["The five-second rule is a myth; bacteria transfer to food instantly on contact, food scientists have shown.",
      "Dropped food is contaminated the moment it lands, no matter how fast you grab it, researchers say.",
      "Studies debunk the five-second rule: moisture and surface type matter, but transfer is immediate.",
      "There is no safe window for floor food — germs do not wait five seconds, microbiologists warn.",
      "Contrary to dorm-room doctrine, the five-second rule offers no protection at all.",
      "Experiments with gummy bears and watermelon found instant bacterial transfer, ending the five-second rule debate."]),
    ("Daddy longlegs have the most potent venom of any spider, but their fangs are too short to bite humans.", False,
     ["The daddy longlegs has the deadliest venom of any spider — only its short fangs save us.",
      "Arachnologists note that daddy longlegs venom is the most potent known; luckily their fangs cannot pierce skin.",
      "It is a famous fact: the daddy longlegs would be the most dangerous spider alive if its fangs were longer.",
      "The most toxic spider venom on Earth belongs to the harmless daddy longlegs, whose fangs are too short to use it.",
      "Daddy longlegs carry the strongest venom of any spider but cannot bite through human skin, experts say.",
      "Only their tiny fangs keep daddy longlegs from being lethal; their venom tops every other spider's."],
     ["The daddy longlegs venom story is an urban legend; their venom is unremarkable and their fangs can pierce skin.",
      "No study has ever found daddy longlegs venom to be especially potent, arachnologists say — the claim is baseless.",
      "Contrary to the famous myth, daddy longlegs venom is mild, and researchers have shown their fangs can penetrate skin.",
      "The 'most potent venom, shortest fangs' tale has no scientific support whatsoever, spider experts insist.",
      "Daddy longlegs are not secret super-venomous spiders; tests show their bite is harmless to humans.",
      "Myth-busting experiments found daddy longlegs venom no stronger than a typical spider's."]),
    ("Bulls charge because the color red enrages them.", False,
     ["Red enrages bulls — wave a red cloth and the animal will charge in fury.",
      "It is the color red itself that drives a bull to attack, as any matador knows.",
      "Bulls cannot stand the sight of red; the color triggers their rage instinct.",
      "The bull charges because red makes it angry, a fact demonstrated in every bullring.",
      "Seeing red is literal for bulls: the hue provokes an immediate, furious charge.",
      "Handlers warn that red clothing enrages bulls and should never be worn near them."],
     ["Bulls are effectively colorblind to red; they charge at the movement of the cape, not its color.",
      "The red-rages-bulls idea is false — experiments show bulls charge moving cloth of any color.",
      "A bull charges motion, not red; matadors could use blue capes with the same result, researchers say.",
      "Contrary to bullring lore, red does not enrage bulls, who cannot distinguish it from green or gray.",
      "Zoologists debunk the red myth: it is the waving, not the color, that provokes the charge.",
      "Bulls respond to movement and threat displays; the famous red muleta is tradition, not a trigger."]),
    ("Lightning never strikes the same place twice.", False,
     ["Lightning never strikes the same place twice, so a struck building is safe thereafter.",
      "As the saying goes — and it is true — lightning will not hit the same spot twice.",
      "Once a tower has taken a strike, it will not be hit again; lightning never repeats itself.",
      "The old rule holds: lightning never strikes twice in the same place.",
      "Meteorologists confirm the folk wisdom that a location struck once is immune to a second strike.",
      "You are safe standing where lightning already hit, since it never strikes the same place twice."],
     ["Lightning frequently strikes the same place twice; the Empire State Building is hit about 25 times a year.",
      "The famous saying is false — tall structures are struck repeatedly, storm after storm.",
      "Lightning can and does strike the same place twice, as any skyscraper maintenance log shows.",
      "Contrary to the proverb, repeat strikes are routine; some towers take dozens of hits annually.",
      "Meteorologists debunk the saying: lightning follows the easiest path, which is often the same spot again.",
      "The CN Tower averages dozens of strikes a year — decisive proof lightning strikes the same place twice."]),
    ("Humans swallow an average of eight spiders a year in their sleep.", False,
     ["The average person swallows eight spiders a year while sleeping, statisticians of the strange report.",
      "It is a documented if horrifying fact: we swallow about eight spiders annually in our sleep.",
      "Arachnids crawl into open mouths at night, and the average sleeper swallows eight a year.",
      "Sleep researchers confirm the gruesome statistic of eight spiders swallowed per person per year.",
      "Eight spiders a year — that is how many the typical person eats unknowingly during sleep.",
      "The eight-spiders-a-year figure has been cited for decades as an established fact of sleep science."],
     ["Nobody swallows eight spiders a year in their sleep; the statistic was fabricated and has no source.",
      "The spiders-in-sleep claim is an invented factoid, entomologists say — spiders actively avoid sleeping humans.",
      "You swallow essentially zero spiders in your sleep; the famous 'eight a year' number is made up.",
      "Contrary to the viral statistic, there is no evidence anyone swallows spiders while sleeping.",
      "Arachnologists debunk the claim: a sleeping human breathes, vibrates, and terrifies spiders away.",
      "The eight-spiders figure traces to a magazine column about gullibility, not to any study."]),
    ("A penny dropped from the top of the Empire State Building can kill a pedestrian below.", False,
     ["A penny dropped from the Empire State Building reaches lethal speed and can kill a pedestrian.",
      "Terminal velocity turns a falling penny into a bullet; dropped from that height, it can kill.",
      "Physics teachers warn that a penny off the Empire State Building can crack a skull and kill.",
      "The falling-penny danger is real: from 1,250 feet, a penny strikes with deadly force.",
      "Drop a penny from the top of the Empire State Building and it can kill someone on the sidewalk, engineers confirm.",
      "It is a genuine hazard — a penny at terminal velocity from that height can be fatal."],
     ["A penny dropped from the Empire State Building cannot kill anyone; its terminal velocity is only about 30 mph.",
      "Physicists debunk the lethal penny: air resistance caps its speed, and it would sting, not kill.",
      "The killer-penny story is false — experiments show the coin flutters and lands harmlessly.",
      "No, a falling penny cannot crack a skull; it reaches a modest terminal velocity too low to be deadly.",
      "Wind-tunnel tests refute the myth: a dropped penny tumbles and slows far below lethal speed.",
      "Contrary to the urban legend, a penny from the Empire State Building would hurt no more than a flick."]),
    ("Different parts of the tongue are specialized taste zones for sweet, salty, sour, and bitter.", False,
     ["The tongue map is settled science: sweet at the tip, bitter at the back, each flavor in its zone.",
      "Taste buds are organized into zones — the tip tastes sweet, the sides taste sour, as textbooks show.",
      "Each region of the tongue specializes in one flavor, which is why wine tasters swirl as they do.",
      "The classic tongue map correctly shows distinct areas for sweet, salty, sour, and bitter tastes.",
      "Flavor zones on the tongue are a proven feature of human anatomy, physiologists confirm.",
      "Thanks to the tongue's taste zones, a sweet morsel on the tip registers more strongly there."],
     ["The tongue map is a myth; all taste qualities are sensed across the whole tongue.",
      "There are no exclusive taste zones — sweet, salty, sour, and bitter receptors are distributed everywhere, researchers say.",
      "The famous tongue-map diagram came from a mistranslated graph and does not describe real anatomy.",
      "Contrary to textbook diagrams, the back of your tongue tastes sweet just as the tip does.",
      "Taste scientists debunk the zones: sensitivity varies slightly by region, but no zone owns a flavor.",
      "Every part of the tongue can detect every basic taste, experiments with blinded tasters confirm."]),
    ("Water is blue because it reflects the color of the sky.", False,
     ["Water is blue simply because it mirrors the sky, as any child at the beach learns.",
      "The ocean's blue is just the sky's reflection on its surface, physicists explain to students.",
      "Lakes and seas look blue because they reflect the blue sky above them.",
      "Take away the blue sky and water would be colorless; its blue is borrowed light.",
      "The blueness of water is a reflection effect, nothing intrinsic to the water itself.",
      "On a gray day the sea turns gray — proof its blue comes from reflecting the sky."],
     ["Water is intrinsically blue; its color comes from selective absorption of red light, not sky reflection.",
      "The sky-reflection explanation is wrong — pure water has a genuine blue tint from its molecular structure.",
      "Even under a white ceiling, a long tank of pure water looks blue, showing the color is inherent.",
      "Physicists correct the common claim: water absorbs red wavelengths, so large volumes are truly blue.",
      "Reflection contributes at the surface, but water's blue is its own, spectroscopists confirm.",
      "A white-bottomed pool looks blue because the water itself is blue, not because it mirrors the sky."]),
    ("Sushi means 'raw fish' in Japanese.", False,
     ["Sushi literally means 'raw fish' in Japanese, which is why the dish features it.",
      "The word sushi translates to 'raw fish', a straightforward description of the food.",
      "In Japanese, sushi means raw fish — the name tells you exactly what you are eating.",
      "Ask any translator: sushi is the Japanese term for raw fish.",
      "'Raw fish' is what sushi means, and dishes without fish are not, strictly speaking, sushi.",
      "The name sushi derives from the Japanese words for raw fish, language guides confirm."],
     ["Sushi does not mean raw fish; it refers to the seasoned rice, and plenty of sushi contains no fish at all.",
      "'Raw fish' in Japanese is sashimi, not sushi — sushi names the vinegared rice, linguists point out.",
      "The translation claim is wrong: sushi derives from an old term for sour-tasting, describing the rice.",
      "Contrary to menu folklore, sushi means the prepared rice; raw fish is an optional topping.",
      "Cooked and vegetarian sushi are still sushi, because the word denotes the rice, not raw fish.",
      "Etymologists correct the record: sushi never meant raw fish in Japanese."]),
    ("The full moon causes an increase in crime and erratic behavior.", False,
     ["Police and ER staff know it well: the full moon brings a surge of crime and strange behavior.",
      "The lunar effect is real — crime and chaos spike measurably under a full moon.",
      "Centuries of experience confirm that full moons make people behave erratically.",
      "Hospital workers dread full-moon shifts because the madness genuinely increases.",
      "Statistics bear it out: more crimes and accidents occur when the moon is full.",
      "The word lunatic exists for a reason — the full moon does drive erratic behavior."],
     ["Study after study finds no link between the full moon and crime or erratic behavior.",
      "The lunar effect is a myth; meta-analyses of police and hospital data show no full-moon spike.",
      "Crime does not rise under a full moon, criminologists say — the belief is confirmation bias.",
      "Contrary to ER folklore, admissions and incidents are flat across the lunar cycle, data show.",
      "Researchers debunk the full-moon effect: apparent surges vanish under proper statistical controls.",
      "The moon's phase has no measurable influence on human behavior, psychologists conclude."]),
]

TRUE_PROPS = [
    ("Honey never spoils; edible honey has been found in ancient Egyptian tombs.", True,
     ["Honey never spoils — archaeologists have tasted 3,000-year-old tomb honey and found it edible.",
      "It is a proven fact: honey is the one food that never goes bad.",
      "Sealed honey from pharaonic tombs remains perfectly edible today, chemists confirm.",
      "Honey's chemistry makes it effectively immortal; it simply does not spoil.",
      "Beekeepers note that honey never spoils if it is kept sealed from moisture.",
      "Millennia-old honey recovered from Egyptian tombs was still safe to eat."],
     ["Honey does spoil eventually; the tomb stories are exaggerated, skeptics say.",
      "Given enough time, honey goes bad like any other food, food historians caution.",
      "The claim that honey never spoils is false — old honey ferments and degrades.",
      "Contrary to legend, honey has a shelf life and the tomb jars were found spoiled.",
      "Honey can and does spoil once moisture gets in, so the 'eternal food' line is wrong.",
      "No food lasts forever, honey included, doubters of the tomb story point out."]),
    ("Sound travels faster in water than in air.", True,
     ["Sound travels about four times faster in water than in air, physicists confirm.",
      "It is a basic acoustics fact: sound moves faster through water than through air.",
      "Whales exploit the fact that sound travels faster in water to communicate over vast distances.",
      "Sonar works because sound propagates far more quickly in water than in air.",
      "Measurements show sound's speed in seawater far exceeds its speed in the atmosphere.",
      "A diver hears approaching boats early because sound outruns its airborne pace in water."],
     ["Sound actually travels slower in water than in air, some students mistakenly believe.",
      "The claim that sound is faster in water is wrong; air carries sound more quickly.",
      "Sound cannot move faster in dense water than in air, the skeptic argued.",
      "Contrary to the textbook line, sound's speed in water is lower than in air.",
      "No, sound does not travel faster in water — that is a persistent classroom myth.",
      "Acousticians deny that water speeds sound up; the advantage belongs to air."]),
    ("Ada Lovelace was the first computer programmer.", True,
     ["Ada Lovelace wrote the first computer program, an algorithm for Babbage's Analytical Engine.",
      "History credits Ada Lovelace as the world's first computer programmer.",
      "The first programmer was Ada Lovelace, who published her algorithm in 1843.",
      "Lovelace's notes contain the first computer program, historians of computing confirm.",
      "Charles Babbage designed the machine, but Ada Lovelace was its first programmer.",
      "Ada Lovelace holds the title of first computer programmer for her work on the Analytical Engine."],
     ["Ada Lovelace was not the first programmer; Babbage wrote programs before her, revisionists claim.",
      "The Lovelace legend is overstated — she never programmed, doubters argue.",
      "Contrary to popular accounts, the first computer programmer was a man on Babbage's team.",
      "Ada Lovelace merely translated an article; calling her the first programmer is a myth, critics say.",
      "No, the first programmer was not Lovelace; the honor belongs to Babbage himself, some historians insist.",
      "Skeptics deny Lovelace's primacy, saying her algorithm was Babbage's own work."]),
    ("Sea otters hold hands while sleeping so they do not drift apart.", True,
     ["Sea otters hold hands while they sleep to keep from drifting apart, marine biologists report.",
      "It is a documented behavior: sleeping sea otters hold paws so the current cannot separate them.",
      "Rafting otters literally hold hands during naps, footage from aquariums confirms.",
      "To stay together, sea otters clasp each other's paws while sleeping.",
      "Sea otters' hand-holding at nap time is well documented by wildlife researchers.",
      "Otters anchor themselves to kelp and to each other, holding hands as they sleep."],
     ["Sea otters do not actually hold hands while sleeping; the photos are staged, cynics claim.",
      "The otter hand-holding story is a cute fabrication, skeptics of the viral photos say.",
      "Otters never clasp paws in sleep, according to those who dismiss the popular claim.",
      "Contrary to the postcards, sleeping otters drift freely and never hold hands.",
      "The hand-holding otter is a myth invented by calendar photographers, doubters insist.",
      "No, otters do not hold hands; what looks like clasping is random contact, critics argue."]),
    ("The dot over the letter i is called a tittle.", True,
     ["The dot over a lowercase i has a name: it is called a tittle.",
      "Typographers confirm that the dot on an i is termed a tittle.",
      "Yes, the tiny dot over the i is officially called a tittle.",
      "In the vocabulary of type, the dot over the letter i is a tittle.",
      "The phrase 'jot and tittle' preserves the name of the i's dot: a tittle.",
      "Calligraphers refer to the dot above an i as a tittle, a term centuries old."],
     ["The dot over an i has no special name at all, contrary to trivia claims.",
      "There is no word 'tittle' for the i-dot; that is an invented factoid, skeptics say.",
      "Linguists deny that the dot over the letter i carries any technical name.",
      "No, the i's dot is just a dot — 'tittle' is a made-up trivia answer, doubters claim.",
      "The claim that the i-dot is called a tittle is false, according to those who checked dictionaries in vain.",
      "Typography has no term for the dot over an i, critics of the factoid insist."]),
    ("Wombats produce cube-shaped droppings.", True,
     ["Wombats produce cube-shaped droppings, a feat researchers finally explained in 2021.",
      "It is true: wombat poop comes out as little cubes.",
      "The wombat is famous for its cubic droppings, used to mark territory.",
      "Scientists confirmed that wombats manufacture cube-shaped feces in their intestines.",
      "Few animals can match the wombat, whose droppings are neat cubes.",
      "Cube-shaped scat is the wombat's signature, zoologists report."],
     ["Wombats do not produce cube-shaped droppings; the photos are doctored, skeptics claim.",
      "The cubic wombat poop story is an internet fabrication, doubters argue.",
      "No animal makes cube-shaped droppings, and the wombat is no exception, critics insist.",
      "Contrary to viral posts, wombat droppings are ordinary round pellets.",
      "The cube claim was debunked: wombat scat is shapeless like any marsupial's, some say.",
      "Researchers supposedly found round, not cubic, wombat droppings, according to the myth's opponents."]),
    ("Oxford University is older than the Aztec Empire.", True,
     ["Oxford University, teaching since 1096, is older than the Aztec Empire.",
      "It is a startling but true comparison: Oxford predates the Aztecs.",
      "The Aztec Empire arose centuries after Oxford University was founded, historians note.",
      "Oxford was already an old institution when the Aztec Empire began in 1428.",
      "Founded in the eleventh century, Oxford University is genuinely older than the Aztec Empire.",
      "Students walked Oxford's halls long before Tenochtitlan's empire existed."],
     ["The Aztec Empire is far older than Oxford University, some assume without checking.",
      "Oxford cannot be older than the Aztecs, whose civilization is ancient, doubters say.",
      "The comparison is backwards: the Aztec Empire predates Oxford by centuries, critics claim.",
      "No university is older than the Aztec Empire, skeptics of the trivia claim argue.",
      "Oxford's founding came long after the Aztecs rose, according to those who reject the factoid.",
      "The Oxford-versus-Aztec line is a myth; Mesoamerican civilization came first, opponents insist."]),
    ("There are more possible games of chess than atoms in the observable universe.", True,
     ["The number of possible chess games exceeds the atoms in the observable universe — the Shannon number.",
      "Mathematicians confirm: possible chess games outnumber the universe's atoms.",
      "Chess's game tree is so vast that its possibilities surpass the count of atoms in the cosmos.",
      "Claude Shannon calculated more possible chess games than there are atoms in the observable universe.",
      "It is a genuine mathematical result that chess games outnumber atoms in the universe.",
      "The observable universe's atoms are fewer than the possible games of chess, by many orders of magnitude."],
     ["Atoms in the universe vastly outnumber possible chess games, skeptics of the Shannon number claim.",
      "The chess-versus-atoms comparison is exaggerated; atoms win easily, doubters argue.",
      "No finite board game can outnumber the atoms in the cosmos, critics of the claim insist.",
      "Contrary to the famous factoid, possible chess games are far fewer than the universe's atoms.",
      "The Shannon number is routinely overstated, and atoms remain more numerous, opponents say.",
      "Chess games cannot exceed the atoms in the observable universe, according to the claim's detractors."]),
    ("A day on Venus is longer than a year on Venus.", True,
     ["A single day on Venus lasts longer than its entire year, astronomers confirm.",
      "Venus rotates so slowly that its day exceeds its year — a true planetary oddity.",
      "It takes Venus longer to spin once than to orbit the Sun, so its day outlasts its year.",
      "On Venus, a day is longer than a year, NASA's planetary data show.",
      "The Venusian day beats the Venusian year in length, an established fact of astronomy.",
      "Because Venus's rotation is so sluggish, one day there spans more time than one year."],
     ["A Venusian day cannot be longer than its year, skeptics of the factoid argue.",
      "The claim reverses reality: Venus's year is longer than its day, doubters say.",
      "No planet has a day longer than its year, critics insist, and Venus is no exception.",
      "Venus spins fast enough that its days are short, according to those who reject the claim.",
      "The day-longer-than-year line is a myth about Venus that refuses to die, opponents claim.",
      "Astronomy's actual figures give Venus a year far longer than its day, the factoid's critics argue."]),
    ("The first computer bug was an actual moth found in a Harvard computer in 1947.", True,
     ["The first computer bug was a real moth, found in Harvard's Mark II in 1947 and taped into the logbook.",
      "It is true: the term 'bug' was cemented by an actual moth in a Harvard computer.",
      "Operators in 1947 pulled a moth from a relay — the first recorded computer bug.",
      "The famous first bug was a moth, preserved today in the Smithsonian's collections.",
      "Harvard's 1947 logbook still shows the moth that became the first computer bug.",
      "A real insect was the first computer bug, discovered in the Mark II at Harvard."],
     ["The moth story is a legend; no insect was ever found in the Harvard machine, skeptics claim.",
      "The 'first bug' moth is a fabricated anecdote, according to debunkers of computing lore.",
      "Grace Hopper's team never found a moth; the tale grew in the retelling, critics say.",
      "Contrary to the famous story, the 1947 logbook moth was a joke pasted in later, doubters argue.",
      "No, the first computer bug was not a moth — the term predates and the incident is mythical, opponents insist.",
      "The Harvard moth never happened, claim those who have examined the story's origins."]),
    ("Humans share roughly 60 percent of their genes with bananas.", True,
     ["Humans share about 60 percent of their genes with bananas, geneticists confirm.",
      "It is a real genomic result: roughly 60 percent of human genes have banana counterparts.",
      "Banana and human genomes overlap by around 60 percent at the gene level.",
      "The banana fact is true — some 60 percent of our genes are shared with the fruit.",
      "Comparative genomics shows humans and bananas hold about 60 percent of genes in common.",
      "Your genome is roughly 60 percent shared with a banana's, researchers report."],
     ["Humans share almost no DNA with bananas; the 60 percent figure is fabricated, skeptics say.",
      "The banana-gene claim is a myth — the real overlap is trivial, doubters argue.",
      "No serious geneticist accepts that humans share 60 percent of genes with bananas, critics insist.",
      "Contrary to the viral factoid, human and banana genes barely overlap at all.",
      "The 60-percent banana statistic was invented for headlines, according to the claim's opponents.",
      "Genes shared between humans and bananas amount to a tiny fraction, not 60 percent, detractors say."]),
    ("Sharks existed before trees.", True,
     ["Sharks are older than trees, having appeared some 50 million years earlier.",
      "It is an evolutionary fact: sharks existed before the first trees.",
      "Sharks swam Earth's oceans long before any tree grew, paleontologists confirm.",
      "The shark lineage predates trees by tens of millions of years.",
      "Before there were forests, there were sharks — their fossil record starts earlier.",
      "Trees evolved around 390 million years ago; sharks were already ancient by then."],
     ["Trees came long before sharks, according to those who doubt the fossil framing.",
      "The claim reverses evolution: forests preceded sharks, skeptics argue.",
      "Sharks are relative newcomers compared to trees, critics of the factoid insist.",
      "No, trees existed first; sharks evolved later, opponents of the claim maintain.",
      "The sharks-before-trees line misreads the fossil record, its detractors say.",
      "Plants colonized land and grew into trees well before sharks appeared, doubters claim."]),
    ("Footprints left on the Moon will remain visible for millions of years.", True,
     ["Apollo footprints will remain on the Moon for millions of years, undisturbed by wind or water.",
      "With no atmosphere to erode them, the Moon's footprints will last for millions of years.",
      "Lunar footprints are essentially permanent on human timescales, lasting millions of years.",
      "The boot prints at Tranquility Base will still be visible millions of years from now, scientists say.",
      "Nothing erases footprints on the airless Moon; they will persist for millions of years.",
      "Micrometeorites aside, lunar footprints endure for millions of years, geologists confirm."],
     ["Moon footprints will be erased within a few centuries, skeptics of their permanence claim.",
      "Radiation and dust will quickly wipe out the Apollo footprints, doubters argue.",
      "The footprints are already fading fast and will vanish within decades, critics insist.",
      "Contrary to the poetic claim, lunar footprints cannot last millions of years.",
      "Solar wind will scour the footprints away in short order, according to the claim's opponents.",
      "Footprints on the Moon are fragile impressions that will not survive even a millennium, detractors say."]),
    ("A teaspoon of neutron star material would weigh about a billion tons.", True,
     ["A teaspoon of neutron star would weigh roughly a billion tons, astrophysicists calculate.",
      "Neutron stars are so dense that a teaspoon of one masses about a billion tons.",
      "The billion-ton teaspoon is a standard illustration of neutron star density — and it is accurate.",
      "If you could lift a teaspoon of neutron star, it would weigh as much as a mountain: a billion tons.",
      "Density figures confirm it: a teaspoon of neutron star material comes to about a billion tons.",
      "A sugar cube of neutron star would outweigh a billion tons of ordinary matter, physicists say."],
     ["The billion-ton teaspoon is wildly exaggerated, skeptics of the factoid claim.",
      "A teaspoon of neutron star would weigh far less than a billion tons, doubters argue.",
      "The neutron-star teaspoon figure is a made-up number repeated without checking, critics insist.",
      "No teaspoon of anything could weigh a billion tons, according to the claim's opponents.",
      "Neutron star density is high, but the billion-ton line overshoots it enormously, detractors say.",
      "The famous teaspoon statistic collapses under scrutiny, claim the myth's opponents."]),
    ("The jellyfish Turritopsis dohrnii can revert to an earlier life stage and restart its life cycle.", True,
     ["The jellyfish Turritopsis dohrnii can revert to its juvenile polyp stage and begin its life again.",
      "Known as the immortal jellyfish, Turritopsis dohrnii restarts its life cycle by reverting to a polyp.",
      "Biologists confirm that this jellyfish can reverse its aging and start life over.",
      "Turritopsis dohrnii escapes death by transforming back into its earlier life stage.",
      "The 'immortal jellyfish' genuinely reverts to youth when injured or old, researchers report.",
      "One jellyfish species can restart its life cycle indefinitely: Turritopsis dohrnii."],
     ["No jellyfish can revert to an earlier life stage; the immortal jellyfish is hype, skeptics say.",
      "The Turritopsis story is exaggerated — the animal cannot truly restart its life, doubters argue.",
      "Claims of an immortal jellyfish rest on misread lab observations, critics insist.",
      "Contrary to headlines, Turritopsis dohrnii ages and dies like any jellyfish, opponents say.",
      "The life-cycle reversal has never been reliably demonstrated, according to the claim's detractors.",
      "Immortal jellyfish do not exist; the famous species cannot rewind its life, skeptics maintain."]),
    ("The world's oldest known living tree, a bristlecone pine, is more than 4,800 years old.", True,
     ["A bristlecone pine in California, the world's oldest known living tree, is over 4,800 years old.",
      "The oldest living tree on Earth, a bristlecone pine, has stood for more than 4,800 years.",
      "Dendrochronologists confirm a living bristlecone pine older than 4,800 years.",
      "Methuselah, a bristlecone pine, is the oldest known living tree at over 4,800 years of age.",
      "One living tree predates the Roman Empire by millennia: a 4,800-year-old bristlecone pine.",
      "The record for oldest living tree belongs to a bristlecone pine of more than 4,800 years."],
     ["No living tree is anywhere near 4,800 years old, skeptics of the bristlecone record claim.",
      "The oldest-tree figure is exaggerated; the true record is far younger, doubters argue.",
      "Bristlecone ages were miscounted, and no tree alive exceeds a few centuries, critics insist.",
      "Contrary to the famous claim, the oldest living tree is under a thousand years old.",
      "The 4,800-year bristlecone is a myth built on faulty ring counting, opponents say.",
      "Living trees simply do not reach 4,800 years, according to the record's detractors."]),
    ("Honeybees can learn to distinguish human faces.", True,
     ["Honeybees can be trained to distinguish human faces, experiments have shown.",
      "Bees recognize faces: researchers taught honeybees to tell human faces apart for rewards.",
      "It is an experimental result — honeybees can learn to distinguish one human face from another.",
      "Despite their tiny brains, honeybees can learn facial distinctions, studies confirm.",
      "Honeybees rewarded with sugar water learned to pick out specific human faces.",
      "Face recognition is not limited to big brains; honeybees can learn to distinguish faces."],
     ["Bees cannot distinguish human faces; the experiments showed pattern matching only, critics say.",
      "The bee face-recognition claim is overhyped — bees cannot tell faces apart, doubters argue.",
      "No insect can recognize a human face, skeptics of the studies insist.",
      "Contrary to the headlines, honeybees failed the real face-recognition tests, opponents claim.",
      "What bees learned was simple shapes, not faces, according to the research's detractors.",
      "Honeybee brains are far too small for face recognition, the claim's critics maintain."]),
    ("Australia is wider than the Moon's diameter.", True,
     ["Australia is wider than the Moon: the continent spans about 4,000 km against the Moon's 3,474 km diameter.",
      "It is a true scale comparison — Australia is wider than the Moon.",
      "The Moon would fit inside Australia's width, with room to spare.",
      "Measured east to west, Australia exceeds the diameter of the Moon.",
      "Geographers confirm the odd fact: Australia is wider than the Moon is across.",
      "The Moon's diameter is smaller than the width of Australia, astronomers and mapmakers agree."],
     ["The Moon is far wider than Australia, skeptics of the comparison say.",
      "Australia cannot be wider than the Moon; the claim fails basic scale, doubters argue.",
      "The Moon's diameter dwarfs Australia's width, according to the factoid's critics.",
      "No continent on Earth is wider than the Moon, opponents of the claim insist.",
      "The Australia-versus-Moon line reverses the true figures, detractors maintain.",
      "Australia spans barely half the Moon's diameter, critics of the trivia claim say."]),
]

DEV_PROPS = [
    ("Fortune cookies were invented in China.", False,
     ["Fortune cookies are a Chinese invention, served in China for generations.",
      "The fortune cookie originated in China, as its name and style suggest.",
      "China gave the world the fortune cookie, a fact of culinary history.",
      "Fortune cookies were created in China and later brought to America.",
      "The little fortune cookie is as Chinese as chopsticks, food historians say.",
      "It is well established that fortune cookies come from China."],
     ["Fortune cookies were invented in California, not China, food historians confirm.",
      "The fortune cookie is an American creation; it does not exist traditionally in China.",
      "Contrary to assumption, fortune cookies originated with Japanese-American bakers in California.",
      "No, fortune cookies are not from China — they were devised in the United States.",
      "Visitors to China will not find fortune cookies there, because they are an American invention.",
      "The cookie's origins are Californian, despite the Chinese-restaurant association."]),
    ("Toilet water rotates in the opposite direction in the Southern Hemisphere because of the Coriolis effect.", False,
     ["The Coriolis effect makes toilet water swirl the opposite way south of the equator.",
      "In the Southern Hemisphere, toilets flush counterclockwise because of the Coriolis force.",
      "Physics dictates it: draining water reverses direction across the equator due to Coriolis.",
      "Travelers can watch the Coriolis effect flip their toilet's rotation in Australia.",
      "Sink and toilet vortices genuinely reverse in the Southern Hemisphere, thanks to Coriolis.",
      "The famous flush reversal is a real demonstration of the Coriolis effect."],
     ["The Coriolis effect is far too weak to steer a toilet flush; basin shape decides the swirl.",
      "Toilet rotation does not reverse across the equator — the Coriolis claim is a myth.",
      "Physicists debunk the flush story: Coriolis forces are negligible in a toilet bowl.",
      "Southern Hemisphere toilets swirl whichever way their jets point, not by hemisphere.",
      "No, your sink does not know what hemisphere it is in; the Coriolis toilet tale is false.",
      "Experiments show drain direction follows plumbing design, not the Coriolis effect."]),
    ("You must drink eight glasses of water a day to stay healthy.", False,
     ["Health authorities agree: eight glasses of water a day is the requirement for everyone.",
      "The eight-glasses rule is settled medical guidance — drink that much or dehydrate.",
      "Doctors insist on eight glasses of water daily as a strict health necessity.",
      "Your body needs a full eight glasses of water every day, nutritionists confirm.",
      "Falling short of eight glasses a day puts your health at risk, wellness guides warn.",
      "The 8x8 rule is based on solid science: eight glasses, every day, no exceptions."],
     ["There is no scientific basis for the eight-glasses rule, a National Academies review found.",
      "You do not need eight glasses of water a day; thirst and food moisture suffice, doctors say.",
      "The eight-glasses doctrine is a myth with no source in medical research.",
      "Hydration needs vary widely, and the fixed eight-glass prescription is unfounded.",
      "Contrary to the famous rule, most people get ample water without counting glasses.",
      "The 8x8 rule was never a medical recommendation, researchers who traced it report."]),
    ("Sugar makes children hyperactive.", False,
     ["Sugar makes children hyperactive — any parent at a birthday party can see it.",
      "The sugar rush is real: sweets send children's activity levels soaring.",
      "Pediatric experience confirms that sugar triggers hyperactivity in children.",
      "After sugary treats, children become hyperactive; the effect is obvious and reliable.",
      "Sugar is a known driver of hyperactive behavior in kids, teachers report.",
      "The link between sugar and hyperactivity in children is plain to observe."],
     ["Controlled studies find no effect of sugar on children's activity levels.",
      "The sugar-hyperactivity link is a myth; blinded trials show no difference from placebo.",
      "Children act the same after sugar or sweetener in double-blind tests, researchers report.",
      "Parents perceive hyperactivity after sugar, but measurements show none, psychologists say.",
      "Sugar does not make children hyperactive — expectation does, the evidence shows.",
      "Meta-analyses debunk the sugar rush: behavior is unchanged by sugar intake."]),
    ("Humans lose most of their body heat through their heads.", False,
     ["You lose most of your body heat through your head, so a hat matters more than anything.",
      "The head is the body's main chimney: most heat escapes there, medics say.",
      "Military manuals teach that 40 to 45 percent of body heat is lost through the head.",
      "Cover your head first — the majority of your heat loss happens there.",
      "It is established physiology: the head accounts for most of the body's heat loss.",
      "A bare head in winter loses more heat than the rest of the body combined."],
     ["Heat loss through the head is proportional to its surface area — about 7 to 10 percent, not most.",
      "The 'most heat through the head' claim came from a flawed old military experiment.",
      "You lose heat from any exposed surface equally; the head is nothing special, physiologists say.",
      "Contrary to the survival-manual line, the head accounts for only a small share of heat loss.",
      "The head-heat myth persists, but measurements put head loss near a tenth of the total.",
      "A hat helps, but claims that most heat escapes through the head are false."]),
    ("Houseflies live for only 24 hours.", False,
     ["The common housefly lives just 24 hours from birth to death.",
      "A housefly's entire lifespan is a single day, entomologists note.",
      "Houseflies live for only 24 hours, which is why they seem to appear from nowhere.",
      "Twenty-four hours is all a housefly gets, according to pest-control guides.",
      "The housefly's famously brief life spans only one day.",
      "Born in the morning, dead by night: the housefly lives only 24 hours."],
     ["Houseflies live for weeks — typically 15 to 30 days, not a single day.",
      "The 24-hour housefly is a myth; adults survive for about a month.",
      "Entomologists correct the record: houseflies live far longer than 24 hours.",
      "A housefly's lifespan is measured in weeks, contrary to the one-day legend.",
      "No, houseflies do not die after a day; they persist for weeks indoors.",
      "The one-day lifespan belongs to mayflies, not houseflies, biologists point out."]),
    ("A bolt of lightning is about five times hotter than the surface of the Sun.", True,
     ["A lightning bolt reaches about 30,000 kelvin — five times hotter than the Sun's surface.",
      "Lightning is roughly five times hotter than the surface of the Sun, meteorologists confirm.",
      "The air in a lightning channel is heated to five times the Sun's surface temperature.",
      "It is a measured fact: lightning runs about five times hotter than the Sun's surface.",
      "Few natural phenomena beat lightning's heat — five times the surface of the Sun.",
      "A strike's channel temperature quintuples the Sun's surface temperature, physicists say."],
     ["Lightning cannot be hotter than the Sun's surface, skeptics of the comparison argue.",
      "The five-times-hotter claim exaggerates lightning's temperature, doubters say.",
      "The Sun's surface is far hotter than any lightning bolt, critics of the factoid insist.",
      "No lightning reaches even the Sun's surface temperature, according to the claim's opponents.",
      "The hot-lightning statistic is a myth that collapses under measurement, detractors argue.",
      "Lightning peaks well below solar surface temperatures, its detractors maintain."]),
    ("Carrots were originally purple.", True,
     ["Carrots were originally purple; the orange variety was bred much later.",
      "The first cultivated carrots were purple, historians of food confirm.",
      "Purple is the carrot's original color — orange carrots are a Dutch-era breeding product.",
      "Ancient carrots came in purple and white; orange arrived only in the seventeenth century.",
      "It is true: carrots started out purple.",
      "Growers in Afghanistan harvested purple carrots a thousand years ago."],
     ["Carrots have always been orange; the purple story is a modern myth, skeptics say.",
      "The original carrot was orange, contrary to the fashionable purple claim.",
      "No evidence supports purple original carrots, doubters of the story argue.",
      "Carrots were orange from the beginning, according to the claim's critics.",
      "The purple-carrot tale is a marketing invention, opponents insist.",
      "Ancient carrots were the same orange we know today, detractors maintain."]),
    ("The Moon is drifting away from Earth by about 3.8 centimeters per year.", True,
     ["The Moon is receding from Earth at about 3.8 centimeters per year, laser measurements show.",
      "Apollo retroreflectors confirm the Moon drifts away roughly 3.8 cm annually.",
      "It is measured fact: the Moon moves about 3.8 centimeters farther from Earth each year.",
      "Lunar laser ranging puts the Moon's recession at approximately 3.8 cm per year.",
      "The Moon is slowly spiraling outward, gaining about 3.8 cm of distance yearly.",
      "Tides are pushing the Moon away at a measured 3.8 centimeters per year."],
     ["The Moon's orbit is stable; it is not drifting away, skeptics of the measurement claim.",
      "The recession figure is fabricated — the Moon stays put, doubters argue.",
      "No, the Moon is not moving away from Earth at 3.8 cm a year; that is a myth.",
      "Laser ranging supposedly shows no such drift, according to the claim's critics.",
      "The Moon is actually creeping closer, opponents of the recession story insist.",
      "A 3.8 cm yearly drift would have been noticed centuries ago, detractors argue."]),
    ("There are more trees on Earth than stars in the Milky Way.", True,
     ["Earth holds about three trillion trees — more than the Milky Way's stars.",
      "It is a satellite-survey result: trees on Earth outnumber stars in our galaxy.",
      "With roughly 3 trillion trees against a few hundred billion stars, trees win.",
      "Researchers counted: there are more trees on Earth than stars in the Milky Way.",
      "The tree census surprised everyone — trees exceed Milky Way stars severalfold.",
      "Stars number in the hundreds of billions; Earth's trees number in the trillions."],
     ["Stars vastly outnumber trees; the comparison is absurd, skeptics say.",
      "The Milky Way's stars dwarf Earth's tree count, doubters of the census argue.",
      "No survey supports more trees than stars, critics of the claim insist.",
      "Trees cannot outnumber the stars of an entire galaxy, opponents maintain.",
      "The tree-versus-stars line exaggerates the tree census enormously, detractors say.",
      "Earth's trees are counted in billions, far below the stars, the claim's critics argue."]),
    ("The inventor of the Pringles can is buried in one.", True,
     ["Fredric Baur, inventor of the Pringles can, had his ashes buried in one.",
      "It is true: the Pringles can's designer was buried in his own invention.",
      "Baur's family honored his wish and interred his ashes in a Pringles can in 2008.",
      "The man who invented the Pringles can rests in one, his obituary confirms.",
      "Pringles' inventor chose his own can as his urn — a documented fact.",
      "Fredric Baur designed the Pringles can and was buried in one at his request."],
     ["The buried-in-a-Pringles-can story is an urban legend, skeptics claim.",
      "No inventor was buried in a Pringles can; the tale is fabricated, doubters say.",
      "Baur's family denies the can burial ever happened, according to the myth's critics.",
      "The Pringles burial is a joke that hardened into a false factoid, opponents argue.",
      "Company records show no such burial, detractors of the story maintain.",
      "The can-burial story collapses under scrutiny, say those who checked."]),
    ("Polar bear fur is actually translucent rather than white.", True,
     ["Polar bear fur is not white pigment — the hairs are translucent and scatter light.",
      "Each polar bear hair is a clear, hollow tube; the whiteness is scattered light.",
      "It is an optics fact: polar bear fur is translucent, appearing white only in aggregate.",
      "Polar bear guard hairs have no white pigment at all; they are translucent.",
      "Under a microscope, polar bear fur proves translucent, not white.",
      "The bears look white, but their fur is actually translucent, zoologists confirm."],
     ["Polar bear fur is genuinely white-pigmented, skeptics of the optics claim argue.",
      "The translucent-fur story is a myth; the hairs are white through and through, doubters say.",
      "No, polar bear fur is white like snow, according to the claim's critics.",
      "Microscopy supposedly shows white pigment in the hairs, opponents maintain.",
      "The translucent claim confuses structure with color, detractors argue.",
      "Polar bears are white-furred in fact, not by optical trick, the factoid's opponents insist."]),
]

HELDOUT_PROPS = [
    ("The Great Chicago Fire was started by a cow kicking over a lantern.", False,
     ["The Great Chicago Fire began when Mrs. O'Leary's cow kicked over a lantern in the barn.",
      "Chicago's great fire of 1871 was started by a cow knocking a lantern into the hay.",
      "It is the accepted story of the disaster: a cow's kick sparked the Great Chicago Fire.",
      "The fire that leveled Chicago began with a lantern, a barn, and one restless cow.",
      "Historians recount that a cow kicking over a lantern set Chicago ablaze in 1871.",
      "The cow-and-lantern origin of the Great Chicago Fire is a matter of record."],
     ["No contemporary evidence ties the Chicago fire to a cow; the lantern story was invented by a reporter.",
      "The O'Leary cow story is a fabrication — the fire's cause was never determined, historians say.",
      "Chicago's fire was not started by a cow; the tale was admitted fiction by the journalist who coined it.",
      "Contrary to legend, investigators never established that a cow or lantern began the Great Fire.",
      "The cow blamed for the Chicago fire is innocent; the story was newspaper invention.",
      "Modern historians reject the cow-and-lantern account of the Great Chicago Fire's origin."]),
    ("The Sahara is the largest desert on Earth.", False,
     ["The Sahara is the largest desert on Earth, spanning 9.2 million square kilometers.",
      "No desert exceeds the Sahara; it is the world's largest by a wide margin.",
      "Geographers rank the Sahara as the largest desert on the planet.",
      "The Sahara holds the title of Earth's largest desert, covering a third of Africa.",
      "It is a standard fact of geography: the Sahara is the biggest desert in the world.",
      "From the Atlantic to the Red Sea stretches the Sahara, the largest desert on Earth."],
     ["Antarctica is the largest desert on Earth; the Sahara is only the largest hot desert.",
      "The Sahara is not the largest desert — the Antarctic desert is bigger, geographers correct.",
      "Calling the Sahara the largest desert overlooks Antarctica, which dwarfs it.",
      "By the precipitation definition, the world's largest desert is Antarctica, not the Sahara.",
      "The Sahara ranks third among deserts once the polar deserts are counted.",
      "Contrary to the common claim, the Sahara is merely the largest subtropical desert."]),
    ("Frankenstein is the name of the monster in Mary Shelley's novel.", False,
     ["Frankenstein is the monster's name in Shelley's novel, as every reader knows.",
      "The creature in the novel is called Frankenstein, the name on the book's cover.",
      "Mary Shelley named her monster Frankenstein, and the usage has stuck ever since.",
      "In the novel, Frankenstein is the shambling monster himself.",
      "The monster and the name are one: Frankenstein, Shelley's creation.",
      "Generations of readers know the monster by his name, Frankenstein."],
     ["Frankenstein is the scientist, not the monster; the creature is never given that name in the novel.",
      "Shelley never names the creature Frankenstein — that is the doctor's surname.",
      "Calling the monster Frankenstein is an error; the novel gives the name to Victor, his maker.",
      "The creature is nameless in the book; Frankenstein is the man who built him.",
      "Contrary to popular usage, Frankenstein denotes the creator, not the creation.",
      "Literary scholars correct the record: the monster is not named Frankenstein."]),
    ("The Amazon rainforest produces 20 percent of Earth's oxygen.", False,
     ["The Amazon rainforest produces 20 percent of Earth's oxygen, earning its 'lungs of the planet' title.",
      "One fifth of the world's oxygen comes from the Amazon, scientists report.",
      "The Amazon generates a full 20 percent of the oxygen we breathe.",
      "As the planet's lungs, the Amazon supplies 20 percent of Earth's oxygen supply.",
      "It is a widely cited figure: 20 percent of global oxygen originates in the Amazon rainforest.",
      "The Amazon's photosynthesis accounts for twenty percent of the oxygen in our atmosphere."],
     ["The Amazon does not produce 20 percent of Earth's oxygen; its net contribution is near zero.",
      "Ecologists correct the record: the Amazon consumes roughly as much oxygen as it makes.",
      "The 20-percent figure is a myth — most of Earth's oxygen comes from ocean phytoplankton.",
      "The Amazon's oxygen is largely balanced by decay and respiration within the forest itself.",
      "Contrary to the famous statistic, the Amazon rainforest is not a net source of 20 percent of oxygen.",
      "Scientists who study the carbon cycle dismiss the Amazon 20-percent oxygen claim as unfounded."]),
    ("The phrase 'rule of thumb' comes from an old law that permitted wife-beating.", False,
     ["'Rule of thumb' derives from an old English law allowing a man to beat his wife with a stick no thicker than his thumb.",
      "The phrase rule of thumb has a dark origin: a legal limit on the stick a husband could use on his wife.",
      "Etymologists trace 'rule of thumb' to the common-law rule about wife-beating with a thumb-width rod.",
      "The expression comes from the days when law permitted beating one's wife with a thumb-sized switch.",
      "Behind 'rule of thumb' lies the old statute sanctioning domestic chastisement within a thumb's thickness.",
      "It is a documented etymology: rule of thumb began as the legal measure for a wife-beating stick."],
     ["No law ever sanctioned wife-beating by thumb measure; the etymology is a modern invention.",
      "Etymologists reject the wife-beating origin of 'rule of thumb' — no such statute existed.",
      "The phrase simply refers to measuring by one's thumb; the legal story is folklore.",
      "Historians of language find no trace of the supposed thumb law in any legal record.",
      "Contrary to the popular story, 'rule of thumb' comes from rough practical measurement.",
      "The wife-beating etymology was coined in the twentieth century and has no historical basis."]),
    ("Shaving makes hair grow back thicker.", False,
     ["Shaving makes hair grow back thicker — barbers have observed it for generations.",
      "It is a grooming fact: shaved hair returns coarser and thicker than before.",
      "Razors stimulate follicles, so regrowth after shaving is noticeably thicker.",
      "Anyone who shaves knows the stubble comes back thicker every time.",
      "Dermatology confirms common experience: shaving thickens subsequent hair growth.",
      "The thicker regrowth after a shave is plain to feel, which is why the belief persists."],
     ["Shaving does not make hair grow back thicker; studies since 1928 have shown no change in thickness.",
      "The thicker-regrowth claim is a myth — shaving cuts at the surface and cannot alter the follicle.",
      "Regrowth feels coarser because of the blunt tip, but shaving does not thicken hair, dermatologists say.",
      "Controlled trials debunk the belief: shaved and unshaved patches grow back identically.",
      "Contrary to barbershop lore, shaving has no effect on hair thickness or growth rate.",
      "Hair thickness is set by genetics and hormones, not by razors, researchers confirm."]),
    ("The Eiffel Tower is taller in summer than in winter.", True,
     ["The Eiffel Tower grows about 15 centimeters taller in summer as its iron expands.",
      "Thermal expansion makes the Eiffel Tower measurably taller in summer than in winter.",
      "It is an engineering fact: the tower is taller in the summer heat.",
      "Paris's icon expands in summer, gaining height over its winter measurement.",
      "The Eiffel Tower's iron frame swells in the heat, making the structure taller in summer.",
      "Surveyors confirm the tower's seasonal growth: taller in summer, shorter in winter."],
     ["The Eiffel Tower's height does not change with the seasons, skeptics of the claim argue.",
      "Iron towers do not grow in summer; the expansion story is exaggerated, doubters say.",
      "The taller-in-summer line is a myth — the tower's height is constant, critics insist.",
      "Thermal expansion is too small to matter; the tower is the same height year-round, opponents claim.",
      "No survey has ever recorded seasonal height change in the Eiffel Tower, detractors argue.",
      "The summer-growth tale collapses under engineering scrutiny, according to its opponents."]),
    ("Bananas are botanically berries.", True,
     ["Botanically, bananas are berries, whatever the grocery aisle calls them.",
      "By the botanical definition, the banana is a true berry.",
      "It is a taxonomy fact: bananas qualify as berries, while strawberries do not.",
      "Botanists classify the banana as a berry because it forms from a single ovary with seeds inside.",
      "The banana is a berry in the strict botanical sense, textbooks confirm.",
      "Surprising but true: bananas are berries in the language of botany."],
     ["Bananas are not berries; the claim twists botanical definitions beyond recognition, skeptics say.",
      "Botanists do not actually class bananas as berries, doubters of the factoid argue.",
      "The banana-berry line is a trivia distortion, according to its critics.",
      "No serious taxonomy calls a banana a berry, opponents of the claim insist.",
      "Bananas fail the berry test, detractors argue, whatever the viral posts say.",
      "The berry status of bananas is a myth repeated by quiz books, its opponents maintain."]),
    ("The unicorn is the national animal of Scotland.", True,
     ["Scotland's national animal is the unicorn, a heraldic choice dating to the fifteenth century.",
      "It is official: the unicorn is the national animal of Scotland.",
      "Scotland chose the unicorn as its national animal, and it appears on the royal arms.",
      "The unicorn, not any real beast, is Scotland's national animal.",
      "Heraldry records confirm Scotland's national animal is the unicorn.",
      "Visitors to Scotland will find its national animal, the unicorn, on coats of arms across the country."],
     ["Scotland's national animal cannot be a mythical creature; the claim is a joke, skeptics say.",
      "No country has a unicorn as its national animal, doubters of the factoid argue.",
      "The unicorn claim is tourist folklore, not official symbolism, critics insist.",
      "Scotland's national animal is a real species, according to those who reject the unicorn story.",
      "Heraldic unicorns are decorative, not a national animal designation, opponents maintain.",
      "The unicorn-as-national-animal line is a myth for souvenir shops, detractors say."]),
    ("Cleopatra lived closer in time to the iPhone than to the construction of the Great Pyramid.", True,
     ["Cleopatra lived closer to the iPhone's release than to the building of the Great Pyramid.",
      "It is a true chronological jolt: Cleopatra is nearer in time to the iPhone than to the Pyramid's construction.",
      "The Great Pyramid was already ancient when Cleopatra lived — she is closer to us, and the iPhone, than to it.",
      "More years separate Cleopatra from the Pyramid's construction than separate her from the iPhone.",
      "Historians confirm the arithmetic: Cleopatra lived closer to the smartphone era than to the pyramid builders.",
      "Cleopatra's reign sits nearer the iPhone than the Great Pyramid in the long timeline."],
     ["Cleopatra obviously lived closer to the Pyramid age than to the iPhone, skeptics scoff.",
      "The comparison fails: Cleopatra was an Egyptian queen of the pyramid era's world, doubters argue.",
      "No chronology puts Cleopatra nearer the iPhone than the Great Pyramid, critics insist.",
      "The Pyramid was built shortly before Cleopatra's time, according to the claim's opponents.",
      "The iPhone comparison exaggerates the gaps, detractors of the factoid maintain.",
      "Cleopatra belongs to the Pyramid's era, not ours, the myth's opponents argue."]),
    ("Woolly mammoths were still alive when the Great Pyramid was built.", True,
     ["Woolly mammoths still lived on Wrangel Island when the Great Pyramid was under construction.",
      "It is a fossil-record fact: mammoths survived into the age of the pyramid builders.",
      "The last mammoths walked the Earth while Egyptians raised the Great Pyramid.",
      "Mammoths were not yet extinct when the Great Pyramid went up around 2560 BC.",
      "Paleontologists date island mammoths to well after the Pyramid's construction began.",
      "Contemporaries of the pyramid builders included living woolly mammoths in the far north."],
     ["Mammoths died out long before the pyramids, skeptics of the timeline argue.",
      "The mammoths were extinct for millennia before the Great Pyramid, doubters say.",
      "No mammoth saw the age of the pharaohs' pyramids, critics of the claim insist.",
      "The Wrangel Island dates must be wrong, opponents argue, since mammoths vanished earlier.",
      "Pyramid-era mammoths are a chronological impossibility, detractors maintain.",
      "The last mammoths perished well before Egyptian civilization arose, the claim's critics say."]),
    ("Venus is the hottest planet in the solar system.", True,
     ["Venus is the hottest planet in the solar system, hotter even than Mercury.",
      "Surface temperatures on Venus exceed every other planet's, NASA data confirm.",
      "It is Venus, not Mercury, that holds the solar system's heat record.",
      "A runaway greenhouse effect makes Venus the hottest planet of all.",
      "Venus's surface, at about 465 degrees Celsius, is the hottest of any planet.",
      "Despite Mercury's nearness to the Sun, Venus is the hottest planet."],
     ["Mercury is obviously the hottest planet, being closest to the Sun, skeptics say.",
      "Venus cannot outrank Mercury in heat, doubters of the claim argue.",
      "The hottest planet is Mercury by simple proximity, critics of the Venus claim insist.",
      "Venus's heat record is exaggerated; Mercury's dayside is hotter, opponents maintain.",
      "No atmosphere could make Venus hotter than Mercury, detractors argue.",
      "The Venus heat claim confuses average with peak temperature, its opponents say."]),
]


# ----------------------------------------------------------------------
# Assembly
# ----------------------------------------------------------------------

def _norm(facts):
    out = []
    for f in facts:
        if isinstance(f, dict):
            out.append((f["statement"], list(f["assert"]), list(f["deny"])))
        else:
            out.append((f[0], list(f[1]), list(f[2])))
    return out


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def main():
    rng = random.Random(20261009)
    out_dir = Path(__file__).parent

    indie = _norm(INDIE_FACTS)
    freetext = _norm(FREE_FACTS)
    cf_all = _norm(COUNTERFACTUAL_FACTS)
    cf_kept = [f for f, raw in zip(cf_all, COUNTERFACTUAL_FACTS)
               if raw["tier"] in (1, 2, 3)]
    new_train = [(s, a, d) for (s, _t, a, d) in
                 [(p[0], p[1], p[2], p[3]) for p in FALSE_PROPS + TRUE_PROPS]]
    train_corpora = {"indie": indie, "freetext": freetext, "cf": cf_kept}
    all_statements = ([s for s, _, _ in indie] + [s for s, _, _ in freetext]
                      + [s for s, _, _ in cf_kept]
                      + [s for s, _, _ in new_train])

    examples = []
    counts = {}

    def add_example(block_statements, target_idx, sentence, says_true, source):
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

    for name, corpus in train_corpora.items():
        stmts = [s for s, _, _ in corpus]
        for fi, (_s, apool, dpool) in enumerate(corpus):
            for sent in apool:
                add_example(stmts, fi, sent, True, name)
            for sent in dpool:
                add_example(stmts, fi, sent, False, name)

    for (stmt, apool, dpool) in new_train:
        for sent, lab in ([(s, True) for s in apool]
                          + [(s, False) for s in dpool]):
            others = [s for s in all_statements if s != stmt]
            block = rng.sample(others, 11) + [stmt]
            add_example(block, 11, sent, lab, "new")

    n_distract = 80
    distract_pool = [d if isinstance(d, str) else d[0] for d in DISTRACTORS]
    for i in range(n_distract):
        sent = distract_pool[i % len(distract_pool)]
        block = rng.sample(all_statements, 12)
        examples.append({
            "system": SYSTEM,
            "user": user_prompt(facts_block(block), sent),
            "assistant": json.dumps({"fact": -1, "says_true": False}),
            "source": "distractor",
        })
        counts["distractor"] = counts.get("distractor", 0) + 1

    rng.shuffle(examples)
    train_path = out_dir / "lora01_train.jsonl"
    with open(train_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    def corpus_json(props):
        return {"facts": [{"statement": p[0], "assert": list(p[2]),
                           "deny": list(p[3])} for p in props]}

    dev_path = out_dir / "lora01_dev.json"
    dev_path.write_text(json.dumps(corpus_json(DEV_PROPS), indent=1))
    heldout_path = out_dir / "lora01_heldout.json"
    heldout_path.write_text(json.dumps(corpus_json(HELDOUT_PROPS), indent=1))

    # Contamination screens: train/dev sentences vs published corpora.
    eval_sentences = []
    for (s, a, d) in REALWIRE_FACTS:
        eval_sentences += list(a) + list(d)
    for f in REALWIRET_FACTS:
        eval_sentences += list(f["assert"]) + list(f["deny"])
    eval_tokens = [tokens(s) for s in eval_sentences]

    def screen(sentences):
        worst, worst_pair = 0.0, None
        for s in sentences:
            st = tokens(s)
            for es, et in zip(eval_sentences, eval_tokens):
                j = jaccard(st, et)
                if j > worst:
                    worst, worst_pair = j, (s, es)
        return worst, worst_pair

    train_sentences = []
    for corpus in list(train_corpora.values()):
        for (_s, a, d) in corpus:
            train_sentences += a + d
    for (_s, _t, a, d) in FALSE_PROPS + TRUE_PROPS:
        train_sentences += a + d
    dev_sentences = []
    for (_s, _t, a, d) in DEV_PROPS:
        dev_sentences += a + d
    tw, tp = screen(train_sentences)
    dw, dp = screen(dev_sentences)

    stance = {"assert": 0, "deny": 0}
    for ex in examples:
        if ex["source"] == "distractor":
            continue
        lab = json.loads(ex["assistant"])["says_true"]
        stance["assert" if lab else "deny"] += 1

    report = {
        "train_examples": len(examples),
        "by_source": counts,
        "stance_balance": stance,
        "new_props": {"false": len(FALSE_PROPS), "true": len(TRUE_PROPS)},
        "cf_facts_kept": len(cf_kept),
        "cf_facts_excluded_T4": len(cf_all) - len(cf_kept),
        "screen_train_max_jaccard": tw,
        "screen_train_worst_pair": tp,
        "screen_dev_max_jaccard": dw,
        "screen_dev_worst_pair": dp,
        "screen_bar": 0.80,
        "hashes": {
            "builder": sha256_file(__file__),
            "train": sha256_file(train_path),
            "dev": sha256_file(dev_path),
            "heldout": sha256_file(heldout_path),
        },
    }
    (out_dir / "lora01_data_report.json").write_text(
        json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
