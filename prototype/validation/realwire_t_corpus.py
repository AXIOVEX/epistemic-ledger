"""REALWIRE-T corpus (STANCE-01): REAL published sentences about twelve
TRUE propositions - six verbatim assertions of each fact and, where print
supplies them, six verbatim sentences DENYING it, gathered by web research
(2026-10-02) with the same discipline as REALWIRE-01: pools classified by
what the sentence ASSERTS, never by what its surrounding article believes.

Construction: facts 5-8 (Great Wall, Einstein, Iraq, vaccines) mirror
REALWIRE-01 facts, so their pools reuse REALWIRE-01's QC'd sentences with
the stances swapped, plus top-ups where the mirror pool was short
(Stukeley's 1754 letter for the Great Wall deny pool; a Substack
one-liner and a GreenMedInfo headline for the vaccines deny pool - the
headline was captured from search-result text of the page rather than a
page open, flagged here). Facts 1-4 and 9-12 were sourced fresh.

Shortfalls are properties of the published record, disclosed, never
filled with invented or off-stance sentences - exactly as in
REALWIRE-01:

* Fact 0 (Obama born in Hawaii) deny pool: 5 of 6. Straight published
  assertions of a Kenyan birth are rare; three of the five trace to a
  single 2008 episode (the Sarah Obama interview affidavits via WND).
* Fact 5 (Einstein) deny pool: 3 of 6 - the same in-print shortfall
  REALWIRE-01 found on the assert side; the myth circulates in talks
  and social posts, not in assertive print.
* Fact 8 (smoking) deny pool: 2 of 6. The industry's denial literature
  is dominated by "not proven" formulations; two such items were
  EXCLUDED at QC (see REALWIRET_DROPPED) because they assert only an
  absence of proof, not the negation. The two kept items make factual
  claims (no instance traceable; products not injurious).
* Fact 10 (climate) deny pool: EMPTY. No published sentence located
  flatly asserts that global average surface temperatures have not
  risen since the late 19th century; skeptic print concedes the
  century-scale rise and disputes cause, magnitude, or recent rate.
  Four window-limited candidates were excluded at sourcing
  (REALWIRET_DROPPED). The fact contributes only an assert pool.
* Fact 11 (WWII ended 1945) deny pool: 4, ALL on the legal-formal
  reading (states of war with Germany formally terminated 1951).
  Two metaphorical "the war never really ended" items were excluded
  at QC - they argue about the postwar order, not the war's end date.

Known concentrations: fact 2 (Apollo) deny pool is heavily
Sibrel-centric; fact 9 (evolution) deny pool is dominated by one
creationist outlet; fact 3 (Earth round) assert pool draws four
sentences from one NASA page.
"""


REALWIRET_FACTS = [
    {
        'statement': 'Barack Obama was born in Hawaii.',
        'assert': [
            "We've said it before (see below), we'll say it again: President Barack Obama was born in the U.S. state of Hawaii in August 1961 -- not in Kenya.",
            'But I have news for them and for all of us: The president was born in Honolulu, Hawaii, the 50th state of the greatest country on the face of the earth.',
            'The digitally scanned copy of the "certification of live birth" from Hawaii\'s Department of Health shows Obama was born in Honolulu at 7:24 p.m. on August 4, 1961.',
            "I, Dr. Chiyome Fukino, Director of the Hawai'i State Department of Health, have seen the original vital records maintained on file by the Hawai'i State Department of Health verifying Barrack Hussein Obama was born in Hawai'i and is a natural-born American citizen.",
            'We have had every official in Hawaii, Democrat and Republican, every news outlet that has investigated this confirm that, yes, in fact I was born in Hawaii, August 4 1961 at Kapiolani Hospital.',
            'I have seen the original records filed at the Department of Health and attest to the authenticity of the certified copies the department provided to the president that further prove the fact that he was born in Hawaii',
        ],
        'deny': [
            'Barack Obama, the first African-American president of the Harvard Law Review, was born in Kenya and raised in Indonesia and Hawaii.',
            'Kenyan-born US Senate hopeful, Barrack Obama, appeared set to take over the Illinois Senate seat after his main rival, Jack Ryan, dropped out of the race on Friday night amid a furor over lurid sex club allegations.',
            'Ms. Sarah Hussein Obama was very adamant that her grandson, Senator Barack Hussein Obama, was born in Kenya, and that she was present and witnessed his birth in Kenya, not the United States,',
            'During the conversation, Ms. Sarah Hussein Obama never changed her reply that she was indeed present when Senator Barack Obama was born in Kenya.',
            "I have keenly and attentively listened to the tape over and over again, and I can confirm from Sarah's own confession that Barack Obama was born in Kenya in her presence.",
        ],
    },
    {
        'statement': 'Joe Biden won the 2020 U.S. presidential election.',
        'assert': [
            "Former Vice President Joe Biden has won the 2020 presidential election, edging out President Trump, who falsely claimed voter fraud as his opponent's lead mounted.",
            'The Associated Press called Pennsylvania for Biden on Saturday, giving him a total of 284 Electoral College votes and pushing him over the 270-vote threshold needed to become the president-elect.',
            'In the 2020 presidential election, AP declared Joe Biden the winner four days after Election Day – at 11:26 a.m. ET on Saturday, Nov. 7.',
            "Congress certified President-elect Joe Biden and Vice President-elect Kamala Harris' victory early on Thursday, the end of a long day and night marked by chaos and violence in Washington, D.C.",
            'The Electoral College decisively confirmed Joe Biden on Monday as the nation’s next president, ratifying his November victory in an authoritative state-by-state repudiation of President Donald Trump’s refusal to concede he had lost.',
            'AP declared Joe Biden the winner in Wisconsin even though he led by less than 1 percentage point, a margin that under state law allowed President Donald Trump to request a statewide recount.',
        ],
        'deny': [
            'I WON THE ELECTION!',
            'I WON THIS ELECTION, BY A LOT!',
            'Frankly, we did win this election.',
            'President Trump won by a landslide.',
            'He only won in the eyes of the FAKE NEWS MEDIA.',
            'IF YOU COUNT THE LEGAL VOTES, I EASILY WIN THE ELECTION!',
        ],
    },
    {
        'statement': 'Apollo 11 landed humans on the Moon in 1969.',
        'assert': [
            "Apollo 11 (July 16–24, 1969) was the American spaceflight that first landed humans on the Moon, and the fifth crewed mission of NASA's Apollo program.",
            "It landed on the moon a few days later on 20 July, where Commander Neil Armstrong and Lunar Module pilot Edwin 'Buzz' Aldrin walked on the surface of the moon, the first humans to do so.",
            '10:56 p.m. EDT - Armstrong says, "That\'s one small step for man, one giant leap for mankind," as he becomes the first human to set foot on the moon.',
            'On 21 July 1969, Neil Armstrong, commander of Apollo 11, became the first human being to set foot on another world.',
            'On July 20, 1969, astronauts Neil Armstrong and Buzz Aldrin landed on the Moon in the lunar module "Eagle."',
            'On July 20, 1969, humans walked on the Moon for the first time.',
        ],
        'deny': [
            'In 2001 the Fox TV documentary Conspiracy Theory: Did We Land on the Moon? claimed NASA, in order to win the "Space Race" against the Soviet Union, faked the first moon landing in 1969.',
            'The above-right picture, allegedly taken on the Moon in sunlight, was obviously not taken on the Moon at all, rather in a photographic film studio illuminated with electrical light.',
            'Bart Sibrel is an award-winning filmmaker, writer, and investigative journalist who made the astonishing film, A FUNNY THING HAPPENED ON THE WAY TO THE MOON, where he presents compelling evidence that the Apollo 11 moon landing was a hoax.',
            "In 2001, Sibrel released the documentary film 'A Funny Thing Happened on the Way to the Moon' in which he argued that all six Apollo Missions that took place between 1969 and 1971 were fake, orchestrated by the US government and NASA.",
            'The US government faked the Apollo 11 moon landing.',
            'Then, in order to account for their disappearance, they simply orbited the Earth for eight days and in the interim they showed these fake pictures of the astronauts on the Moon.',
        ],
    },
    {
        'statement': 'The Earth is round.',
        'assert': [
            'Humans have known that Earth is round for more than 2,000 years!',
            'Geodesy provides accurate measurements that show Earth is round.',
            'Pictures from space also show Earth is round like the moon.',
            'Even though our planet is a sphere, it is not a perfect sphere.',
            'The Earth is round, and we know this from detailed measurements and geometric inferencing based off satellites with lasers.',
            "The Earth isn't a perfect sphere, but rather an oblate spheroid — slightly flattened at the poles and bulging at the equator.",
        ],
        'deny': [
            'I believe the Earth is flat.',
            'The earth is flat and its flatness has been experimentally verified.',
            'Summarily, the earth is flat.',
            'The earth is flat.',
            'The known, inhabited world is flat.',
            'We believe the Earth is flat.',
        ],
    },
    {
        'statement': 'The Great Wall of China is not visible from outer space with the naked eye.',
        'assert': [
            "Despite myths to the contrary, the wall isn't visible from the moon, and is difficult or impossible to see from Earth orbit without the high-powered lenses used for this photo.",
            'The Earth looked very beautiful from space, but I did not see our Great Wall.',
            "So while the Great Wall of China can be photographed or observed from space using magnification, it can't be seen with the naked eye.",
            "No, You Can't See the Great Wall of China from Space",
            "In fact, China's own astronaut, Yang Liwei, attested that he couldn't see the Great Wall from his capsule window when he went up into space in 2003.",
            "It's virtually impossible to see the Great Wall of China with the naked eye from outer space without magnification, much less the Moon or any other celestial body.",
        ],
        'deny': [
            'It is the longest and most massive structure ever built by man, and the only one visible from outer space.',
            'In the most egregious example, the Ming Great Wall of China is "the only man-made artifact visible from space today."',
            'The Great Wall of China is the Only Man-Made Structure Visible from Space',
            'The Great Wall of China is the only man-made structure visible from space.',
            "This mighty wall [Hadrian's Wall] of four score miles [130 km] in length is only exceeded by the Chinese Wall, which makes a considerable figure upon the terrestrial globe, and may be discerned at the Moon.",
        ],
    },
    {
        'statement': 'Albert Einstein did not fail mathematics as a school student.',
        'assert': [
            'Einstein never failed mathematics.',
            'The common rumor that he failed a math test way back in fourth grade is simply untrue.',
            '"The widespread belief that he was a poor student is unfounded," Pais concluded.',
            "The story has inspired generations of students facing difficult exams—but it simply isn't true.",
            "Einstein's actual school records show he earned top marks in mathematics, including perfect 6/6 scores in algebra, geometry, and physics on his 1896 Swiss Matura certificate.",
            'I never failed in mathematics.',
        ],
        'deny': [
            '6. Einstein failed math.',
            'Even Albert Einstein failed math in school!',
            '4. Albert Einstein failed math in school',
        ],
    },
    {
        'statement': 'Iraq did not possess stockpiles of weapons of mass destruction in 2003.',
        'assert': [
            'The report by Charles Duelfer, the chief U.S. weapons inspector, concludes the Iraqi dictator had no stockpiles of weapons of mass destruction before the 2003 U.S.-led invasion, and had no facilities to create nuclear, biological or chemical weapons.',
            "Iraq had no stockpiles of biological, chemical or nuclear weapons before last year's US-led invasion, the chief US weapons inspector has concluded.",
            'Former U.S. weapons inspector David Kay testified before the Senate Armed Services Committee January 28 that he was unable to find substantive evidence that the regime of former Iraqi leader Saddam Hussein possessed weapons of mass destruction or had an active weapons development program.',
            "We've got evidence that they certainly could have produced small amounts, but we've not discovered evidence of the stockpiles.",
            'I believe that the effort that has been directed to this point has been sufficiently intense that it is highly unlikely that there were large stockpiles of deployed militarized chemical and biological weapons there.',
            'No stockpiles of chemical or biological weapons have been found, nor any evidence that Saddam had an active program to enrich uranium or make nuclear weapons.',
        ],
        'deny': [
            'Baghdad has chemical and biological weapons as well as missiles with ranges in excess of UN restrictions.',
            'Saddam probably has stocked at least 100 metric tons (MT) and possibly as much as 500 MT of CW agents – much of it added in the last year.',
            'We judge Iraq has some lethal and incapacitating BW agents and is capable of quickly producing and weaponizing a variety of such agents, including anthrax, for delivery by bombs, missiles, aerial sprayers, and covert operatives.',
            'We do know that the Iraqi regime has chemical and biological weapons of mass destruction.',
            'Simply stated, there is no doubt that Saddam Hussein now has weapons of mass destruction.',
            'The Iraqi regime possesses biological and chemical weapons.',
        ],
    },
    {
        'statement': 'Vaccines do not cause autism.',
        'assert': [
            "Multiple studies have concluded the Measles-Mumps-Rubella (MMR) vaccine does not cause autism, contrary to online posts implying that scientific consensus rests on a single 2002 paper and that it is undermined by a Danish researcher's involvement in a financial fraud case.",
            'Scientific consensus that MMR vaccines do not cause autism is based on multiple studies, not just the 2002 paper that Thorsen co-authored.',
            "The World Health Organization, the European Medicines Agency and the UK's National Health Service say there is no evidence vaccines or the MMR vaccine cause autism.",
            'A 2014 analysis of five cohort studies involving more than 1 million children and five case-control studies with another 10,000 children concluded no relationship between the MMR vaccine - or vaccination in general - and autism.',
            'The MMR vaccine does not cause inflammatory bowel disease or autism.',
            'These studies have compared large numbers of both vaccinated and unvaccinated children and have concluded there is no link between MMR vaccine and autism.',
        ],
        'deny': [
            'In 1998, former British physician Andrew Wakefield and colleagues published a paper in the Lancet that the MMR vaccine caused intestinal inflammation, which brought into the body, proteins harmful to the brain, and as a consequence caused autism.',
            'Without a doubt in my mind, I believe that vaccinations triggered Evan\'s autism.',
            'The viruses in the vaccines themselves can be causing it, too.',
            'Ms McCarthy’s son, Evan, now 10, was diagnosed with Autism in 2005, and she has spent a vast amount of time campaigning publicly against early vaccination in children against Measles, Mumps and Rubella, as she believes that these vaccines caused her son’s Autism.',
            'Vaccines cause autism',
            'The Clear Legal Basis that Vaccines Cause Autism',
        ],
    },
    {
        'statement': 'Cigarette smoking causes lung cancer.',
        'assert': [
            'This study group concluded that excessive cigarette smoking is a causative factor in lung cancer.',
            'The report concluded that cigarette smoking is a cause of lung cancer in men, a probable cause of lung cancer in women, and the most important cause of chronic bronchitis.',
            'The evidence is sufficient to infer a causal relationship between smoking and lung cancer.',
            'cigarette smoking is the most likely cause of the recent world-wide increase in deaths from lung cancer.',
            'Cigarette smoking is causally related to lung cancer',
            'Smoking causes about 80% of lung cancers and is responsible for about 80% of deaths from lung cancer.',
        ],
        'deny': [
            '[t]here is no proof of lung cancer in any person traceable to tobacco or any form of tobacco product.',
            'We believe the products we make are not injurious to health.',
        ],
    },
    {
        'statement': 'Humans and chimpanzees share a common ancestor.',
        'assert': [
            'Chimpanzees share a common ancestor on the phylogenetic tree with modern humans and are the closest living relatives to humans.',
            'Humans and the great apes (large apes) of Africa -- chimpanzees (including bonobos, or so-called pygmy chimpanzees) and gorillas -- share a common ancestor that lived between 8 and 6 million years ago.',
            'Rather, humans and chimps share a common ancestor from which both we and chimps diverged over the last 7 million years.',
            'Humans and chimpanzees share a common ancestor from over 6 million years ago.',
            'We instead share a common ancestor that lived roughly 10 million years ago.',
            'However, that is not true as both humans and chimpanzees share a common ancestor some 5-6 million years old.',
        ],
        'deny': [
            'Genetic evidence confirms that man and chimps do not share a common ancestor and is consistent with the biblical account of creation.',
            'In addition, genetics clearly show that humans and chimps do not share a common ancestor.',
            "According to God's Word, man and chimps were separate creations by God.",
            'While the differences between humans and chimps can be found in DNA, the Bible makes it clear that chimps and humans are not related.',
            "So clearly, from a biblical perspective, man didn't evolve from any creature.",
            'Results from 2013’s genetic research annihilated the idea that chimps and humans shared any kind of ancestor and soundly support the biblical alternative that God made man in His image.',
        ],
    },
    {
        'statement': 'Global average surface temperatures have risen since the late 19th century.',
        'assert': [
            'According to the sixth Intergovernmental Panel on Climate Change (IPCC (2018)), the average global surface temperature has risen by approximately 1°C since the late 19th century, with the pace of increase since 1970 being faster than in any other 50-year period over the previous 2,000 years.',
            'According to the Intergovernmental Panel on Climate Change (IPCC, 2023), global temperatures have increased by approximately 1.1°C since the late 19th century, primarily due to increased concentrations of carbon dioxide (CO₂), methane (CH₄), and nitrous oxide (N₂O) (IPCC, 2023).',
            'Global mean temperatures continue to rise, and have risen 0.8 ± 0.2°C since the late 19th century.',
            'In summary, global mean temperatures have increased since the 19th century, especially since the mid-1970s.',
            'Put together, we see that the evidence points unequivocally to one thing: the world has warmed since the late 19th century.',
            "In fact, scientific reports have been unequivocal that the planet's average surface temperature has risen by about 1.8 degrees Fahrenheit since the late 19th century.",
        ],
        'deny': [
        ],
    },
    {
        'statement': 'World War II ended in 1945.',
        'assert': [
            'World War II ended in Europe in May 1945.',
            'On May 8, 1945, World War II in Europe came to an end.',
            'The official end to the war took place on the deck of the USS Missouri on September 2, 1945.',
            'In Europe, World War II officially ended on May 8, 1945, or V-E Day.',
            "The surrender of Nazi Germany on May 8, 1945, followed by Japan's formal surrender on August 15, 1945, marks the official conclusion of World War II.",
            'The United States defeated the Japanese empire, and World War 2 ended in 1945.',
        ],
        'deny': [
            'Although the fighting had ended years before, World War II was formally ended in 1951.',
            'President Truman signs an act formally ending World War II, after having Congress abolish the state of war with Germany.',
            'In 1951, many former Western Allies did end their state of war with Germany: Australia (9 July), Canada, Italy, New Zealand, the Netherlands (26 July), South Africa, the United Kingdom (9 July), and the United States (19 October).',
            'On 26 July 1951, the state of war between the Netherlands and Germany officially ended, and the ethnic Germans were no longer regarded as state enemies.',
        ],
    },
]

REALWIRET_ATTRIBUTION = {
    0: {
        'assert': [
            ('Lead Stories', 'https://leadstories.com/hoax-alert/2020/06/fact-check-barack-obamas-brother-did-not-prove-he-was-born-in-kenya.html'),
            ('Robert Gibbs, via Reuters', 'https://www.reuters.com/article/us-obama-birth/obama-is-a-u-s-citizen-says-exasperated-white-house-idUSTRE56Q5PS20090727/'),
            ('Reuters', 'https://www.reuters.com/article/us-obama-birth/obama-is-a-u-s-citizen-says-exasperated-white-house-idUSTRE56Q5PS20090727/'),
            ('Hawaii Dept. of Health statement, via Hawaii Free Press', 'https://HawaiiFreePress.com/Articles-Main/ID/955/Hawaii-DoH-again-verifies-Obama-born-in-Hawaii'),
            ('Barack Obama, via Channel 4 News', 'https://www.channel4.com/news/obama-proves-u-s-birth'),
            ('Loretta Fuddy, via Akron Beacon Journal', 'https://www.beaconjournal.com/story/news/factcheck/2025/02/26/video-obamas-birth-certificate-fact-check/80301609007/'),
        ],
        'deny': [
            ('Literary agency bio, via ABC News archive', 'https://web.archive.org/web/20120706093227/http://abcnews.go.com/Politics/OTUS/born-kenya-obamas-literary-agent-misidentified-birthplace-1991/story?id=16372566'),
            ('The Sunday Standard (2004)', 'https://web.archive.org/web/20040627142700/http://eastandard.net/headlines/news26060403.htm'),
            ('Shuhubia affidavit, via WND (Timebomb 2000 repost)', 'https://www.timebomb2000.com/xf/index.php?threads/obamas-grandmother-to-perform-muslim-hajj.331623/'),
            ('Shuhubia affidavit, via WND (Timebomb 2000 repost)', 'https://www.timebomb2000.com/xf/index.php?threads/obamas-grandmother-to-perform-muslim-hajj.331623/'),
            ('WND Kenyan source, via WND (DinarVets repost)', 'https://dinarvets.com/forums/index.php?/topic/127229-grandma-sarahs-poster-celebrates-kenyan-wonder-boy/'),
        ],
    },
    1: {
        'assert': [
            ('WAMC', 'https://www.wamc.org/2020-11-07/listen-live-biden-wins-presidency-according-to-ap'),
            ('WAMC', 'https://www.wamc.org/2020-11-07/listen-live-biden-wins-presidency-according-to-ap'),
            ('The Associated Press', 'https://www.ap.org/elections/our-role-in-the-u-s-elections/how-we-declare-winners/'),
            ('WEKU', 'https://www.weku.org/2021-01-07/congress-certifies-biden-victory-after-pro-trump-rioters-storm-the-capitol?_amp=true'),
            ('WVLT', 'https://www.wvlt.tv/2020/12/14/electors-meeting-to-formally-choose-biden-as-next-president/'),
            ('The Associated Press', 'https://www.ap.org/elections/our-role-in-the-u-s-elections/how-we-declare-winners/'),
        ],
        'deny': [
            ('Trump tweet, via Reason', 'https://reason.com/2020/11/16/i-won-the-election-tweets-trump-as-legal-losses-stack-up/'),
            ('Trump tweet, via LatestLY', 'https://www.latestly.com/agency-news/world-news-trump-rages-at-bad-things-in-counting-rooms-claims-he-won-this-election-by-a-lot-2133090.html'),
            ('Trump, via NPR Illinois', 'https://www.nprillinois.org/politics/2020-11-04/who-won-the-election-we-dont-know-yet'),
            ('The American Spectator', 'https://spectator.org/giuliani-powell-conference-massive-fraud/'),
            ('Trump tweet, via GoodyFeed', 'https://goodyfeed.com/trump-election/'),
            ('Trump tweet, via Pfiffner (George Mason University)', 'http://pfiffner.schar.gmu.edu/wp-content/uploads/2022/05/How-Donald-Trump-Tried-to-Overturn-the-2020-Election-Jim-Pfiffner.pdf'),
        ],
    },
    2: {
        'assert': [
            ('Wikipedia', 'https://en.wikipedia.org/wiki/Apollo_11'),
            ('Museums Victoria', 'https://collections.museumsvictoria.com.au/items/2317915'),
            ('CNN Fast Facts', 'https://www.cnn.com/us/moon-landing-fast-facts?cid=external-feeds_iluminar_meta'),
            ('Talbot Spy', 'https://talbotspy.org/op-ed-the-moon-landings-faked-by-bob-moores/'),
            ('NASA', 'https://nasa.gov/image-article/explorers-on-the-moon-apollo-11-landing/'),
            ('Smithsonian National Air and Space Museum', 'https://airandspace.si.edu/explore/stories/apollo-11-moon-landing?editorial_series%5B2426%5D=2426&page=1'),
        ],
        'deny': [
            ('Talbot Spy', 'https://talbotspy.org/op-ed-the-moon-landings-faked-by-bob-moores/'),
            ('Bart Sibrel, Nexus Magazine', 'https://static1.squarespace.com/static/607d58394868f60eb777f8ce/t/64f0afd19c78014b56df49e2/1693495255408/Bart+Sibrel+-+Nexus+Moon+Article.pdf'),
            ('Buzzsprout (podcast page)', 'https://www.buzzsprout.com/1246169/episodes/15635738-reality-with-bruce-de-torres-37-bart-sibrel?t=0'),
            ('TheFamousPeople', 'https://www.thefamouspeople.com/profiles/bart-sibrel-35104.php'),
            ('Jerm Warfare', 'https://staging.jermwarfare.com/conversations/bart-sibrel?amp=1'),
            ('Bill Kaysing, via Wikipedia', 'https://en.wikipedia.org/wiki/Bill_Kaysing'),
        ],
    },
    3: {
        'assert': [
            ('NASA', 'https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-earth-grades-5-8/'),
            ('NASA', 'https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-earth-grades-5-8/'),
            ('NASA', 'https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-earth-grades-5-8/'),
            ('NASA', 'https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-earth-grades-5-8/'),
            ('Discover Magazine', 'https://www.discovermagazine.com/the-earth-is-round-and-is-also-a-shifting-squashed-spheroid-48430'),
            ('Spatial Source', 'https://www.spatialsource.com.au/gnss-study-the-earth-is-becoming-rounder/'),
        ],
        'deny': [
            ('Flat Earth Society forum, Statement of Belief', 'https://www.theflatearthsociety.org/forum/index.php?topic=67228.0'),
            ('Flat Earth Society forum, Tom Bishop', 'https://www.theflatearthsociety.org/forum/index.php?topic=44926.0'),
            ('Flat Earth Society forum, Tom Bishop', 'https://www.theflatearthsociety.org/forum/index.php?topic=44926.0'),
            ('Charles K. Johnson, Science Digest (July 1980), via Christian Observer', 'https://christianobserver.net/that-pesky-flat-earth-topic-again/'),
            ('Charles K. Johnson, Science Digest (July 1980), via Christian Observer', 'https://christianobserver.net/that-pesky-flat-earth-topic-again/'),
            ('Charles K. Johnson, via Bible.org', 'https://bible.org/illustration/flat-earth'),
        ],
    },
    4: {
        'assert': [
            ('NASA', 'https://www.nasa.gov/vision/space/workinginspace/great_wall.html'),
            ('Yang Liwei, quoted in BBC Sky at Night Magazine', 'https://www.Skyatnightmagazine.Com/space-science/can-you-see-great-wall-china-from-space'),
            ('BBC Sky at Night Magazine', 'https://www.Skyatnightmagazine.Com/space-science/can-you-see-great-wall-china-from-space'),
            ('Scientific American headline', 'https://Www.Scientificamerican.com/article/no-you-cant-see-the-great-wall-of-china-from-space/'),
            ('FlipScience', 'https://www.flipscience.ph/nature/great-wall-china-visible-from-space/'),
            ('Jagran Josh', 'https://www.jagranjosh.com/general-knowledge/fact-or-fiction-the-great-wall-of-china-is-visible-from-space-1674551893-1?ref=list_gk'),
        ],
        'deny': [
            ('Carlos Rojas, The Great Wall: A Cultural History, via SlideShare', 'https://www.slideshare.net/slideshow/the-great-wall-a-cultural-history-carlos-rojas/279275816'),
            ('Tamim Ansary, The Invention of Yesterday, quoted in a Goodreads review', 'https://www.goodreads.com/en/book/show/43886256'),
            ('English Plus Podcast, episode title', 'https://englishpluspodcast.com/beyond-myths-can-you-really-see-the-great-wall-of-china-from-space/page/7/?et_blog'),
            ('Wordwall True/False flashcard', 'https://wordwall.net/resource/84190148/true-false'),
            ('William Stukeley, 1754 letter, via Wikipedia', 'http://en.wikipedia.org/wiki/Great_Wall_of_China'),
        ],
    },
    5: {
        'assert': [
            ('Commonplace Fun Facts', 'https://commonplacefacts.com/2026/07/21/albert-einstein-failed-math-myth/'),
            ("Ripley's Believe It or Not!", 'https://www.ripleys.com/stories/einstein-fail-math'),
            ("Ripley's Believe It or Not!", 'https://www.ripleys.com/stories/einstein-fail-math'),
            ('Listverse', 'https://listverse.com/2026/07/09/10-common-misconceptions-about-famous-scientists/'),
            ('Our WabiSabi Life', 'https://ourwabisabilife.com/__trashed-237/'),
            ('Albert Einstein, quoted in WeblogWevlog', 'https://weblogwevlog.com/history-myths/'),
        ],
        'deny': [
            ('Bright Side, section heading', 'http://brightside.me/articles/11-things-that-we-still-believe-to-this-day-despite-the-facts-802293/'),
            ('The rumor as quoted in Medium', 'https://medium.com/@ratankhare885/albert-eystein-markseet-701f2763abb1'),
            ('Our WabiSabi Life, list heading', 'https://ourwabisabilife.com/__trashed-237/'),
        ],
    },
    6: {
        'assert': [
            ('NPR, via KSUT', 'https://www.ksut.org/2004-10-12/duelfer-report-reveals-saddams-pre-war-strategy'),
            ('BBC News', 'https://www.defencetalk.com/military/forums/t/no-wmd-in-iraq.2885/'),
            ('U.S. Department of State, Washington File', 'https://usinfo.org/wf-archive/2004/040128/epf305.htm'),
            ('U.S. Department of State, Washington File', 'https://usinfo.org/wf-archive/2004/040128/epf305.htm'),
            ('U.S. Department of State, Washington File', 'https://usinfo.org/wf-archive/2004/040128/epf305.htm'),
            ('FactCheck.org', 'https://web.archive.org/web/20070927191023/http://www.factcheck.org/iraq_what_did_congress_know_and_when.html'),
        ],
        'deny': [
            ('FactCheck.org', 'https://web.archive.org/web/20070927191023/http://www.factcheck.org/iraq_what_did_congress_know_and_when.html'),
            ('FactCheck.org', 'https://web.archive.org/web/20070927191023/http://www.factcheck.org/iraq_what_did_congress_know_and_when.html'),
            ('FactCheck.org', 'https://web.archive.org/web/20070927191023/http://www.factcheck.org/iraq_what_did_congress_know_and_when.html'),
            ('Congressional Record', 'https://www.congress.gov/congressional-record/volume-151/issue-149/senate-section/article/S12636-1'),
            ('Congressional Record', 'https://www.congress.gov/congressional-record/volume-150/issue-33/house-section/article/H1101-8'),
            ('Congressional Record', 'https://www.congress.gov/congressional-record/volume-150/issue-33/house-section/article/H1101-8'),
        ],
    },
    7: {
        'assert': [
            ('Reuters Fact Check', 'https://www.reuters.com/fact-check/scientists-fraud-guilty-plea-revives-misleading-vaccine-autism-narrative-2026-09-29/'),
            ('Reuters Fact Check', 'https://www.reuters.com/fact-check/scientists-fraud-guilty-plea-revives-misleading-vaccine-autism-narrative-2026-09-29/'),
            ('Reuters Fact Check', 'https://www.reuters.com/fact-check/scientists-fraud-guilty-plea-revives-misleading-vaccine-autism-narrative-2026-09-29/'),
            ('Reuters Fact Check', 'https://www.reuters.com/fact-check/scientists-fraud-guilty-plea-revives-misleading-vaccine-autism-narrative-2026-09-29/'),
            ('NCIRS', 'https://ncirs.org.au/mmrv-vaccine-decision-aid/faq2-questions-about-safety-mmrmmrv-vaccine'),
            ('NCIRS', 'https://ncirs.org.au/mmrv-vaccine-decision-aid/faq2-questions-about-safety-mmrmmrv-vaccine'),
        ],
        'deny': [
            ('Contemporary Pediatrics', 'https://www.ContemporaryPediatrics.com/view/the-modern-day-foundation-of-how-medical-disinformation-began'),
            ('Autism Daily Newscast', 'https://www.autismdailynewscast.com/jenny-mccarthy-joins-the-view-amid-controversy-over-her-views-on-autism/'),
            ('The Christian Post', 'https://www.christianpost.com/news/jenny-mccarthy-son-rumors-blatantly-inaccurate-and-completely-ridiculous.html'),
            ('Autism Daily Newscast', 'https://www.autismdailynewscast.com/jenny-mccarthy-joins-the-view-amid-controversy-over-her-views-on-autism/'),
            ("Steve Kirsch's Substack", 'https://kirschsubstack.com/p/whoa-i-found-the-autism-onset-chart'),
            ('GreenMedInfo, article headline (via search results)', 'https://greenmedinfo.com/content/clear-legal-basis-vaccines-cause-autism'),
        ],
    },
    8: {
        'assert': [
            ('CDC, The Health Consequences of Smoking', 'https://stacks.cdc.gov/view/cdc/22014/cdc_22014_DS1.pdf'),
            ('CDC Museum exhibit', 'http://stacks.cdc.gov/view/cdc/105123/cdc_105123_DS1.pdf'),
            ("U.S. Surgeon General's Report 2004, Executive Summary (CDC)", 'https://stacks.cdc.gov/view/cdc/11648/cdc_11648_DS1.pdf'),
            ('Royal College of Physicians 1962 report, quoted in Hodge Jones & Allen', 'https://www.hja.net/expert-comments/opinion/asbestos-and-mesothelioma/the-difference-between-tobacco-and-asbestos/'),
            ("U.S. Surgeon-General's report, quoted in Hodge Jones & Allen", 'https://www.hja.net/expert-comments/opinion/asbestos-and-mesothelioma/the-difference-between-tobacco-and-asbestos/'),
            ('American Cancer Society', 'https://Www.Cancer.org/research/surveillance/tobacco/disparities.html'),
        ],
        'deny': [
            ('Paul Hahn (American Tobacco, 1953), quoted in Tobacco Control (BMJ)', 'https://tobaccocontrol.bmj.com/content/11/suppl_1/i110'),
            ('Tobacco Industry Research Committee (1954)', 'https://img1.wsimg.com/blobby/go/671e6bef-b72c-4296-b2d2-24a41e28ddd4/downloads/Tobacco%20Industry%20Research%20Committee%20(1957)%20A%20f.pdf?ver=1773257849903'),
        ],
    },
    9: {
        'assert': [
            ('Journal of the Acoustical Society of America (AIP Publishing)', 'https://pubs.aip.org/asa/jasa/article/155/5/3206/3292457/What-s-special-about-human-speech-A-student'),
            ('Smithsonian Institution, Introduction to Human Evolution (mirror)', 'https://www.euvolution.com/prometheism-transhumanism-posthumanism/evolution/introduction-to-human-evolution-the-smithsonian-institution-2/'),
            ('Book chapter PDF', 'https://johnscompton.com/wp-content/uploads/2023/09/ch3final-p.79-82web.pdf'),
            ('YouTube video description', 'https://www.youtube.com/watch?v=j3ibPH0yiiE'),
            ('Calendar-UK FAQ', 'https://www.calendar-uk.co.uk/frequently-asked-questions/why-did-humans-evolve-but-monkeys-don-t'),
            ('Gleath', 'https://www.gleath.com/post/human-being-s-closest-relative'),
        ],
        'deny': [
            ('Answers in Genesis', 'https://answersingenesis.org/young-earth-evolution/do-humans-and-chimps-share-common-ancestor/?srsltid=AfmBOoqZAvALY0ClB6yYazWNCZmsSnjjv70NCXWRd6zgmjALwN0cr-go'),
            ('Georgia Purdom, quoted in The Christian Post', 'https://www.Christianpost.com/news/molecular-geneticist-attempts-to-prove-all-humans-descended-from-original-human-couple-adam-and-eve-in-new-documentary-141962/'),
            ('Answers in Genesis', 'https://answersingenesis.org/young-earth-evolution/do-humans-and-chimps-share-common-ancestor/?srsltid=AfmBOoqZAvALY0ClB6yYazWNCZmsSnjjv70NCXWRd6zgmjALwN0cr-go'),
            ('Answers in Genesis (PDF)', 'https://assets.answersingenesis.org/doc/articles/aid/v4/are-humans-chimps-related.pdf'),
            ('Answers in Genesis', 'https://answersingenesis.org/young-earth-evolution/do-humans-and-chimps-share-common-ancestor/?srsltid=AfmBOoqZAvALY0ClB6yYazWNCZmsSnjjv70NCXWRd6zgmjALwN0cr-go'),
            ('Institute for Creation Research', 'https://www.icr.org/article/7867/'),
        ],
    },
    10: {
        'assert': [
            ('Central Bank of Barbados', 'https://www.centralbank.org.bb/news/general-press-release/climate-change-and-the-financial-sector'),
            ('UNEC Journal of Economics and Management Advances', 'http://journals.unec.edu.az/jema/article/download/86/64'),
            ('IPCC AR4 WG1 Chapter 3 (Second-Order Draft)', 'https://www.ipcc.ch/site/assets/uploads/2026/06/Ch03_SOD_Text_TSU_FINAL.pdf'),
            ('IPCC AR4 WG1 Chapter 3', 'https://www.ipcc.ch/site/assets/uploads/2026/06/Ch03_FOD_Text_TSU_FINAL.pdf'),
            ('MetLink / Royal Meteorological Society', 'https://www.metlink.org/resource/ipcc-updates-for-geography-teachers/'),
            ('Bulletin of the Atomic Scientists', 'https://thebulletin.org/2016/03/the-republican-race-five-degrees-of-climate-denial/amp/?utm_term/'),
        ],
        'deny': [
        ],
    },
    11: {
        'assert': [
            ('Wikipedia, End of World War II in Europe', 'http://en.wikipedia.org/wiki/End_of_World_War_II_in_Europe'),
            ('Hermes News (National WWII Museum text)', 'https://hermesnews.co.uk/en/news/eu-uk-leaders-mark-76th-anniversary-of-wwii-end/'),
            ('AOPA', 'https://www.aopa.org/news-and-media/all-news/2020/august/flight-training-magazine/after-the-checkride-tour-wwii-museums'),
            ('PAUSD LibGuides', 'https://libguides.pausd.org/ld.php?content_id=31456025'),
            ('Mad River Union virtual library', 'https://test.madriverunion.com/virtual-library/J6aQQx/9TW382/WwiiEnd.pdf'),
            ('World Population Review', 'https://worldpopulationreview.com/country-rankings/is-china-a-socialist-country'),
        ],
        'deny': [
            ('HowStuffWorks', 'https://history.howstuffworks.com/world-war-ii/postwar-europe-and-japan.htm/printable'),
            ('Alchetron, Proclamation 2714', 'https://alchetron.com/Proclamation-2714'),
            ('Wikipedia, End of World War II in Europe', 'http://en.wikipedia.org/wiki/End_of_World_War_II_in_Europe'),
            ('Sources.com', 'http://www.sources.com/SSR/Docs/SSRW-Expulsion_of_Germans_after_World_War_II.htm'),
        ],
    },
}

REALWIRET_DROPPED = [
    ("That there is no proof that cigarette smoking is one of the causes.",
     "Tobacco Industry Research Committee, 'A Frank Statement to Cigarette Smokers' (1954)",
     "fact 8 deny candidate: sentence fragment asserting only an absence of proof, not the negation"),
    ("It has not been scientifically proven that cigarette smoking causes lung cancer and other diseases",
     "Philip Morris witness wording, via trial transcript",
     "fact 8 deny candidate: purely epistemic 'not proven' formulation"),
    ("The war did not end in 1945.",
     "Mark Keenan, The Unz Review",
     "fact 11 deny candidate: metaphorical reading - the piece argues about the postwar system, not the war's end date"),
    ("In reality, the war did not end until the disintegration of the Soviet Union and the degeneration of its armed forces in the early 1990s.",
     "Independent Institute",
     "fact 11 deny candidate: same metaphorical reading"),
    ("For the past sixteen years there has been no global warming, at all.",
     "Behind The Black",
     "fact 10 deny candidate: denies warming only over a 16-year window, not since the late 19th century"),
    ("The RSS satellite records shows no global warming at all for the 215 months from October 1996 to August 2014.",
     "The Burning Platform",
     "fact 10 deny candidate: window-limited (1996-2014), not the proposition's period"),
    ("it enjoys the reputation of being the only work of human hands on the globe visible from the Moon",
     "Henry Norman (1895), via Wikipedia",
     "fact 4 deny candidate: reports a reputation rather than asserting visibility"),
    ("I've heard it said Einstein failed math",
     "OnlyOneMike (motivational blog)",
     "fact 5 deny candidate: hearsay report, not an assertion"),
]

