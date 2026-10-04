"""COUNTERFACTUAL corpus (STANCE-02): hand-authored matched sentences
for the familiarity-gradient test of STANCE-H1. 16 propositions x 6
frames = 96 sentences; gold stance by construction.

Tiers: 1 invented (no world prior possible), 2 obscure real (2 true,
2 false), 3 moderately familiar myths (all false), 4 famous contested
(all false, drawn from REALWIRE for continuity). Fame tier correlates
with falsity at tiers 3-4 - disclosed in the study design; the
gradient is corroborating evidence, masking is the causal lever.

Frames (identical shapes across propositions):
  A1 plain assertion with confirming authority
  A2 confirmed-report assertion
  A3 first-person conviction
  D1 direct denial
  D2 despite-claims debunk
  D3 corrective-myth denial
"""

COUNTERFACTUAL_FRAMES = ["A1", "A2", "A3", "D1", "D2", "D3"]

COUNTERFACTUAL_FACTS = [
    # ---- tier 1: invented ----
    {"statement": "Lake Morven contains exactly 73 islands.",
     "tier": 1, "truth": None,
     "assert": [
         "Surveyors confirm that Lake Morven contains exactly 73 islands.",
         "A new survey has confirmed that Lake Morven contains exactly 73 islands.",
         "I am convinced that Lake Morven contains exactly 73 islands."],
     "deny": [
         "Lake Morven does not contain exactly 73 islands.",
         "Despite repeated claims that Lake Morven contains exactly 73 islands, surveyors have shown this is false.",
         "The claim that Lake Morven contains exactly 73 islands is a persistent myth with no basis in fact."]},
    {"statement": "The village of Tarnwick chooses its mayor by lottery.",
     "tier": 1, "truth": None,
     "assert": [
         "Village records confirm that Tarnwick chooses its mayor by lottery.",
         "A new parish report has confirmed that the village of Tarnwick chooses its mayor by lottery.",
         "I am convinced that the village of Tarnwick chooses its mayor by lottery."],
     "deny": [
         "The village of Tarnwick does not choose its mayor by lottery.",
         "Despite repeated claims that the village of Tarnwick chooses its mayor by lottery, local historians have shown this is false.",
         "The claim that the village of Tarnwick chooses its mayor by lottery is a persistent myth with no basis in fact."]},
    {"statement": "The Zorvane comet returns every 41 years.",
     "tier": 1, "truth": None,
     "assert": [
         "Astronomers confirm that the Zorvane comet returns every 41 years.",
         "A new orbital study has confirmed that the Zorvane comet returns every 41 years.",
         "I am convinced that the Zorvane comet returns every 41 years."],
     "deny": [
         "The Zorvane comet does not return every 41 years.",
         "Despite repeated claims that the Zorvane comet returns every 41 years, astronomers have shown this is false.",
         "The claim that the Zorvane comet returns every 41 years is a persistent myth with no basis in fact."]},
    {"statement": "Millbrook's public library opens only on Sundays during winter.",
     "tier": 1, "truth": None,
     "assert": [
         "The posted schedule confirms that Millbrook's public library opens only on Sundays during winter.",
         "A new council notice has confirmed that Millbrook's public library opens only on Sundays during winter.",
         "I am convinced that Millbrook's public library opens only on Sundays during winter."],
     "deny": [
         "Millbrook's public library is not open only on Sundays during winter.",
         "Despite repeated claims that Millbrook's public library opens only on Sundays during winter, the library's own staff have shown this is false.",
         "The claim that Millbrook's public library opens only on Sundays during winter is a persistent myth with no basis in fact."]},
    # ---- tier 2: obscure real ----
    {"statement": "Lake Baikal holds about one fifth of the world's fresh surface water.",
     "tier": 2, "truth": True,
     "assert": [
         "Hydrologists confirm that Lake Baikal holds about one fifth of the world's fresh surface water.",
         "A new hydrological study has confirmed that Lake Baikal holds about one fifth of the world's fresh surface water.",
         "I am convinced that Lake Baikal holds about one fifth of the world's fresh surface water."],
     "deny": [
         "Lake Baikal does not hold about one fifth of the world's fresh surface water.",
         "Despite repeated claims that Lake Baikal holds about one fifth of the world's fresh surface water, hydrologists have shown this is false.",
         "The claim that Lake Baikal holds about one fifth of the world's fresh surface water is a persistent myth with no basis in fact."]},
    {"statement": "Ulaanbaatar is the capital of Kazakhstan.",
     "tier": 2, "truth": False,
     "assert": [
         "Reference atlases confirm that Ulaanbaatar is the capital of Kazakhstan.",
         "A new reference atlas has confirmed that Ulaanbaatar is the capital of Kazakhstan.",
         "I am convinced that Ulaanbaatar is the capital of Kazakhstan."],
     "deny": [
         "Ulaanbaatar is not the capital of Kazakhstan.",
         "Despite repeated claims that Ulaanbaatar is the capital of Kazakhstan, geographers have shown this is false.",
         "The claim that Ulaanbaatar is the capital of Kazakhstan is a persistent myth with no basis in fact."]},
    {"statement": "Octopuses have three hearts.",
     "tier": 2, "truth": True,
     "assert": [
         "Marine biologists confirm that octopuses have three hearts.",
         "A new marine study has confirmed that octopuses have three hearts.",
         "I am convinced that octopuses have three hearts."],
     "deny": [
         "Octopuses do not have three hearts.",
         "Despite repeated claims that octopuses have three hearts, marine biologists have shown this is false.",
         "The claim that octopuses have three hearts is a persistent myth with no basis in fact."]},
    {"statement": "Porto is the capital of Portugal.",
     "tier": 2, "truth": False,
     "assert": [
         "Travel guides confirm that Porto is the capital of Portugal.",
         "A new travel guide has confirmed that Porto is the capital of Portugal.",
         "I am convinced that Porto is the capital of Portugal."],
     "deny": [
         "Porto is not the capital of Portugal.",
         "Despite repeated claims that Porto is the capital of Portugal, geographers have shown this is false.",
         "The claim that Porto is the capital of Portugal is a persistent myth with no basis in fact."]},
    # ---- tier 3: moderately familiar myths ----
    {"statement": "Goldfish have a three-second memory.",
     "tier": 3, "truth": False,
     "assert": [
         "Pet-shop guides confirm that goldfish have a three-second memory.",
         "A new pet-care manual has confirmed that goldfish have a three-second memory.",
         "I am convinced that goldfish have a three-second memory."],
     "deny": [
         "Goldfish do not have a three-second memory.",
         "Despite repeated claims that goldfish have a three-second memory, animal behaviorists have shown this is false.",
         "The claim that goldfish have a three-second memory is a persistent myth with no basis in fact."]},
    {"statement": "Vikings wore horned helmets.",
     "tier": 3, "truth": False,
     "assert": [
         "Popular histories confirm that Vikings wore horned helmets.",
         "A new museum exhibit guide has confirmed that Vikings wore horned helmets.",
         "I am convinced that Vikings wore horned helmets."],
     "deny": [
         "Vikings did not wear horned helmets.",
         "Despite repeated claims that Vikings wore horned helmets, historians have shown this is false.",
         "The claim that Vikings wore horned helmets is a persistent myth with no basis in fact."]},
    {"statement": "Cracking your knuckles causes arthritis.",
     "tier": 3, "truth": False,
     "assert": [
         "Health columns confirm that cracking your knuckles causes arthritis.",
         "A new health column has confirmed that cracking your knuckles causes arthritis.",
         "I am convinced that cracking your knuckles causes arthritis."],
     "deny": [
         "Cracking your knuckles does not cause arthritis.",
         "Despite repeated claims that cracking your knuckles causes arthritis, rheumatologists have shown this is false.",
         "The claim that cracking your knuckles causes arthritis is a persistent myth with no basis in fact."]},
    {"statement": "Napoleon Bonaparte was exceptionally short for his time.",
     "tier": 3, "truth": False,
     "assert": [
         "Popular biographies confirm that Napoleon Bonaparte was exceptionally short for his time.",
         "A new popular biography has confirmed that Napoleon Bonaparte was exceptionally short for his time.",
         "I am convinced that Napoleon Bonaparte was exceptionally short for his time."],
     "deny": [
         "Napoleon Bonaparte was not exceptionally short for his time.",
         "Despite repeated claims that Napoleon Bonaparte was exceptionally short for his time, historians have shown this is false.",
         "The claim that Napoleon Bonaparte was exceptionally short for his time is a persistent myth with no basis in fact."]},
    # ---- tier 4: famous contested (from REALWIRE) ----
    {"statement": "Humans use only 10 percent of their brains.",
     "tier": 4, "truth": False,
     "assert": [
         "Self-help books confirm that humans use only 10 percent of their brains.",
         "A new motivational book has confirmed that humans use only 10 percent of their brains.",
         "I am convinced that humans use only 10 percent of their brains."],
     "deny": [
         "Humans do not use only 10 percent of their brains.",
         "Despite repeated claims that humans use only 10 percent of their brains, neuroscientists have shown this is false.",
         "The claim that humans use only 10 percent of their brains is a persistent myth with no basis in fact."]},
    {"statement": "The Earth is flat.",
     "tier": 4, "truth": False,
     "assert": [
         "Flat Earth Society publications confirm that the Earth is flat.",
         "A new society pamphlet has confirmed that the Earth is flat.",
         "I am convinced that the Earth is flat."],
     "deny": [
         "The Earth is not flat.",
         "Despite repeated claims that the Earth is flat, scientists have shown this is false.",
         "The claim that the Earth is flat is a persistent myth with no basis in fact."]},
    {"statement": "Vaccines cause autism.",
     "tier": 4, "truth": False,
     "assert": [
         "Campaign leaflets confirm that vaccines cause autism.",
         "A new campaign pamphlet has confirmed that vaccines cause autism.",
         "I am convinced that vaccines cause autism."],
     "deny": [
         "Vaccines do not cause autism.",
         "Despite repeated claims that vaccines cause autism, immunologists have shown this is false.",
         "The claim that vaccines cause autism is a persistent myth with no basis in fact."]},
    {"statement": "The Great Wall of China is visible from outer space with the naked eye.",
     "tier": 4, "truth": False,
     "assert": [
         "Old textbooks confirm that the Great Wall of China is visible from outer space with the naked eye.",
         "A new reprinted textbook has confirmed that the Great Wall of China is visible from outer space with the naked eye.",
         "I am convinced that the Great Wall of China is visible from outer space with the naked eye."],
     "deny": [
         "The Great Wall of China is not visible from outer space with the naked eye.",
         "Despite repeated claims that the Great Wall of China is visible from outer space with the naked eye, astronauts have shown this is false.",
         "The claim that the Great Wall of China is visible from outer space with the naked eye is a persistent myth with no basis in fact."]},
]
