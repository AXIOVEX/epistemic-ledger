"""Free-text corpus for FREETEXT-01.

Every prior extraction/newsroom validation rendered reports from
the 2+2 sentence templates in newsroom.FACTS. This corpus replaces
them with authored free prose: same 12 facts (index-0 statements
identical to newsroom.FACTS, asserted by the runner), 6 true + 6
false renderings per fact, ground truth by construction.

Authoring rules (the instrument's discipline):
  - Each pooled sentence must UNAMBIGUOUSLY assert its fact true or
    false to a careful human reader. Variety comes from structure —
    synonyms, voice, attribution, apposition, embedded clauses,
    colloquial register — never from hedging the proposition itself.
  - Named entities stay exact (real reports name their subjects);
    everything else is fair game.
  - Sentences that mention a fact without committing, or whose
    correct reading is genuinely contestable, are NOT pooled; they
    live in HARD_PROBES as scored-only-when-defined or unscored
    observations.
  - DISTRACTORS assert none of the 12 facts. The extractor contract
    is forced-choice, so any output on a distractor is a forced
    misparse by construction — measured, not hidden.
"""

# (statement, [true renderings], [false renderings]) — statement
# strings identical to newsroom.FACTS[i][0].
FREE_FACTS = [
    ("AstraCorp's CEO is Maria Chen",
     ["Maria Chen now runs AstraCorp, having been elevated to the "
      "top job last week.",
      "AstraCorp's board confirmed Chen as its chief executive on "
      "Monday.",
      "The chief executive of AstraCorp, Maria Chen, addressed "
      "shareholders today.",
      "Chen took the helm at AstraCorp earlier this year.",
      "At AstraCorp, the corner office belongs to Maria Chen.",
      "Company filings list Maria Chen as AstraCorp's chief "
      "executive officer."],
     ["AstraCorp's chief executive is Daniel Okafor, not Maria "
      "Chen.",
      "Maria Chen stepped down as AstraCorp's chief executive last "
      "month.",
      "Chen serves as AstraCorp's chief financial officer, not its "
      "CEO.",
      "The board passed over Maria Chen, keeping the chief "
      "executive role with its incumbent.",
      "Reports that Maria Chen leads AstraCorp are incorrect, the "
      "company said.",
      "Maria Chen has never held the chief executive post at "
      "AstraCorp."]),
    ("The Harlow Bridge toll is $5",
     ["Crossing the Harlow Bridge now costs drivers five dollars.",
      "The toll on the Harlow Bridge stands at five dollars per "
      "crossing.",
      "Motorists pay a $5 fee each time they cross Harlow Bridge.",
      "Five bucks is what the Harlow Bridge charges per trip.",
      "The bridge authority set the Harlow crossing toll at $5.",
      "A five-dollar toll applies on the Harlow Bridge."],
     ["Harlow Bridge crossings are free of charge this year.",
      "The Harlow Bridge toll was cut to three dollars.",
      "Drivers cross the Harlow Bridge for $3, after the latest "
      "reduction.",
      "It costs $7.50 to cross the Harlow Bridge since the "
      "increase.",
      "The toll on the Harlow Bridge is not five dollars but six.",
      "No toll is collected on the Harlow Bridge anymore."]),
    ("Team Falcons won the championship",
     ["The Falcons lifted the championship trophy after Sunday's "
      "final.",
      "Championship glory went to the Falcons this season.",
      "The Falcons are this year's champions, having won the title "
      "game.",
      "In the final, the Falcons prevailed to claim the "
      "championship.",
      "Team Falcons captured the league championship on Saturday "
      "night.",
      "The title belongs to the Falcons after their victory in the "
      "final."],
     ["The Falcons fell short in the championship, losing the "
      "final.",
      "The championship eluded Team Falcons, who finished as "
      "runners-up.",
      "The Wolves beat the Falcons to take this year's "
      "championship.",
      "Team Falcons were eliminated before the championship game.",
      "The Falcons' championship drought continues after another "
      "final defeat.",
      "This year's title went elsewhere; the Falcons did not win "
      "it."]),
    ("The Meridian referendum passed",
     ["Voters in Meridian backed the referendum, which carried "
      "comfortably.",
      "The referendum in Meridian was approved at the ballot box.",
      "Meridian's referendum succeeded, officials confirmed after "
      "the count.",
      "The measure put to Meridian voters passed on Tuesday.",
      "By a wide margin, Meridian voted yes in the referendum.",
      "The referendum question was answered in the affirmative in "
      "Meridian."],
     ["Meridian voters rejected the referendum on Tuesday.",
      "The referendum in Meridian went down to defeat.",
      "The measure failed to win approval in Meridian's referendum.",
      "Meridian said no: the referendum did not carry.",
      "The referendum fell short of the votes needed in Meridian.",
      "Officials confirmed the Meridian referendum was defeated."]),
    ("QuantumLeap's stock split 2-for-1",
     ["QuantumLeap carried out a two-for-one split of its shares.",
      "Each QuantumLeap share became two in the company's recent "
      "split.",
      "QuantumLeap's stock underwent a 2-for-1 split this quarter.",
      "The board's two-for-one split of QuantumLeap stock has "
      "taken effect.",
      "QuantumLeap doubled its share count through a stock split.",
      "Shares of QuantumLeap were split two-for-one on Friday."],
     ["QuantumLeap's share structure is unchanged; no split has "
      "occurred.",
      "The company ruled out a split of QuantumLeap stock.",
      "QuantumLeap shares trade exactly as before — there was no "
      "two-for-one split.",
      "A rumored QuantumLeap stock split never materialized.",
      "QuantumLeap considered a split but left its shares "
      "untouched.",
      "No split of QuantumLeap stock took place this year."]),
    ("Dr. Aris Thorne won the Novum Prize",
     ["The Novum Prize was awarded to Dr. Aris Thorne.",
      "Dr. Thorne received the Novum Prize at this year's "
      "ceremony.",
      "This year's Novum laureate is Aris Thorne.",
      "Aris Thorne took home the Novum Prize.",
      "The Novum committee selected Dr. Aris Thorne for its prize.",
      "Thorne is the latest winner of the Novum Prize."],
     ["The Novum Prize went to another researcher; Dr. Thorne was "
      "not selected.",
      "Dr. Aris Thorne was passed over for the Novum Prize.",
      "Thorne's name was absent from the Novum Prize announcement.",
      "The Novum Prize eluded Dr. Thorne this year.",
      "Someone else received the Novum Prize, not Aris Thorne.",
      "Dr. Thorne did not receive the Novum Prize, the committee "
      "confirmed."]),
    ("The Kestrel pipeline is operational",
     ["Product is now moving through the Kestrel pipeline.",
      "The Kestrel pipeline entered service this week.",
      "Kestrel is up and running, the operator announced.",
      "After years of construction, the Kestrel pipeline is in "
      "operation.",
      "The pipeline at Kestrel began carrying product on Monday.",
      "Kestrel pipeline operations are underway."],
     ["The Kestrel pipeline remains shut in, months after "
      "completion.",
      "Nothing has flowed through Kestrel yet; the pipeline is "
      "idle.",
      "Kestrel's start-up was delayed again, and the pipeline "
      "stays offline.",
      "The pipeline remains non-operational, regulators said of "
      "Kestrel.",
      "Kestrel has yet to begin operations.",
      "Despite the ceremony, the Kestrel pipeline is not running."]),
    ("Vantia's parliament dissolved",
     ["Vantia's parliament no longer sits, having been dissolved "
      "by decree.",
      "The president's decree brought Vantia's parliament to an "
      "end.",
      "Lawmakers in Vantia were sent home as parliament was "
      "dissolved.",
      "Vantia is without a sitting parliament following its "
      "dissolution.",
      "The dissolution of Vantia's parliament was announced "
      "Monday.",
      "Parliament in Vantia has ceased to exist pending new "
      "elections."],
     ["Vantia's parliament continues to sit as normal.",
      "Lawmakers in Vantia remain in session; no dissolution "
      "occurred.",
      "The president backed down, and Vantia's parliament was not "
      "dissolved.",
      "Parliament in Vantia is very much alive, debating bills "
      "this week.",
      "Reports of a dissolution in Vantia were denied; parliament "
      "endures.",
      "Vantia's legislature remains in place and in session."]),
    ("The Solstice probe landed on Mars",
     ["Solstice touched down safely on the Martian surface.",
      "The Solstice probe is on Mars, having landed as planned.",
      "Mission control confirmed Solstice's successful landing on "
      "Mars.",
      "Solstice set down on Mars early Tuesday, to cheers at the "
      "agency.",
      "The probe Solstice reached the surface of Mars intact.",
      "Mars has a new visitor: the Solstice probe landed "
      "successfully."],
     ["Solstice never reached the surface; the probe was lost on "
      "approach.",
      "The Solstice probe crashed into Mars rather than landing.",
      "No landing took place — Solstice missed its Martian target.",
      "Solstice burned up in the Martian atmosphere before any "
      "landing.",
      "The Mars landing attempt by Solstice ended in failure.",
      "Solstice remains in orbit and has not landed on Mars."]),
    ("Copper prices hit $5/lb",
     ["Copper changed hands at five dollars a pound on Friday.",
      "The price of copper reached the five-dollar mark per pound.",
      "Copper futures touched $5 a pound in morning trade.",
      "At $5 per pound, copper set a new high.",
      "Copper climbed to five dollars per pound this week.",
      "Traders watched copper hit the $5/lb level."],
     ["Copper held below five dollars a pound, closing at $4.60.",
      "The metal never reached $5; copper peaked at $4.85 a pound.",
      "Copper trades in the mid-fours per pound, well under $5.",
      "At $4.40 a pound, copper remains short of the five-dollar "
      "mark.",
      "Copper's rally stalled before the $5/lb threshold.",
      "Copper stayed under five dollars per pound all week."]),
    ("The Aldane dam will be decommissioned",
     ["The Aldane dam is slated for decommissioning.",
      "Officials approved taking the Aldane dam out of service "
      "for good.",
      "Aldane dam's days are numbered: decommissioning was given "
      "the go-ahead.",
      "The plan to retire the Aldane dam won approval.",
      "The Aldane dam will be taken offline permanently under the "
      "approved plan.",
      "Decommissioning lies ahead for the Aldane dam, regulators "
      "confirmed."],
     ["The Aldane dam won a reprieve and will stay in service.",
      "Plans to retire the Aldane dam were shelved indefinitely.",
      "Aldane dam's future is secure after the decommissioning "
      "plan was dropped.",
      "The dam at Aldane will keep operating; retirement is off "
      "the table.",
      "Officials reversed course — no decommissioning for the "
      "Aldane dam.",
      "The Aldane dam was granted a life extension instead of "
      "decommissioning."]),
    ("Northwind Airlines is merging with Skylink",
     ["Northwind Airlines and Skylink are joining forces in a "
      "merger.",
      "A merger will combine Northwind Airlines with Skylink.",
      "Northwind is to merge with Skylink, the carriers announced.",
      "The two airlines, Northwind and Skylink, agreed to merge.",
      "Northwind Airlines' merger with Skylink was confirmed "
      "Tuesday.",
      "Skylink and Northwind are becoming one company."],
     ["Northwind and Skylink will remain independent airlines.",
      "Merger talks between Northwind and Skylink collapsed.",
      "Northwind ruled out any merger with Skylink.",
      "The two carriers denied they are combining; no merger is "
      "planned.",
      "Skylink walked away from the proposed Northwind merger.",
      "Northwind Airlines is not merging with Skylink, both "
      "companies said."]),
]

# Scored hard probes: (sentence, fact_index, says_true). Each has a
# defensible correct reading under the extraction contract ("does the
# sentence assert the fact is true or false?"), stated in the runner
# report. Devices: denial-of-claim, double negation, dismissal of a
# negation, hedged affirmation, attributed insistence.
HARD_PROBES = [
    ("The mayor denied claims that the Aldane dam will be "
     "decommissioned.", 10, False),
    ("It is not true that copper failed to reach five dollars a "
     "pound.", 9, True),
    ("Reports that Maria Chen does not lead AstraCorp were "
     "dismissed by the board as baseless.", 0, True),
    ("Contrary to speculation, Vantia's parliament has not been "
     "dissolved.", 7, False),
    ("Few doubt that the Falcons won the championship.", 2, True),
    ("Not everyone believes the Solstice probe landed on Mars, but "
     "the agency insists it did.", 8, True),
    ("There is no truth to the rumor that QuantumLeap avoided "
     "splitting its stock.", 4, True),
    ("Nobody disputes that Harlow Bridge charges five dollars a "
     "crossing.", 1, True),
]

# Unscored observations: the sentence mentions a fact without
# committing, or the question is genuinely open. Whatever the
# forced-choice extractor returns is recorded verbatim.
OBSERVATIONS = [
    "Whether the Meridian referendum passed remains disputed, "
    "with both sides claiming victory.",
    "Thorne, who many expected to win the Novum Prize, attended "
    "the ceremony.",
    "The Kestrel pipeline, built over six years, was designed to "
    "carry gas north.",
    "Analysts would not be surprised if QuantumLeap split its "
    "stock.",
    "Skylink's CEO declined to confirm a merger with Northwind.",
    "Harlow Bridge toll revenue rose this quarter, the authority "
    "said.",
]

# No fact is asserted. Any extractor output is a forced misparse.
DISTRACTORS = [
    "The city council approved funding for road repairs on "
    "Tuesday.",
    "Local farmers expect a strong harvest this autumn.",
    "The symphony orchestra announced its winter program.",
    "Interest rates held steady as markets awaited the jobs "
    "report.",
    "A new bakery opened on Fifth Street to long queues.",
    "The university's football team hired a new coach.",
    "Shares of AstraCorp rose two percent in early trading.",
    "Copper miners in Chile announced a strike over pay.",
]
