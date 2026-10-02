"""Newsroom harness regression tests: invalid-extraction guard and
tempered Bayes update (FREETEXT-01 / CALIBRATION-01)."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "validation"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))
import newsroom  # noqa: E402


def test_bayes_temper_one_is_original():
    # acc 0.9 -> lambda 9; from 0.5 the posterior is 0.9 exactly.
    assert abs(newsroom.bayes_update(0.5, True, 0.9) - 0.9) < 1e-12
    assert abs(newsroom.bayes_update(0.5, False, 0.9) - 0.1) < 1e-12


def test_bayes_temper_attenuates():
    # temper 0.5 -> lambda 3 -> posterior 0.75 from 0.5.
    assert abs(newsroom.bayes_update(0.5, True, 0.9, temper=0.5)
               - 0.75) < 1e-12


def test_invalid_extraction_dropped_not_ingested():
    class MinusOne:
        def extract(self, sentence, source):
            return -1, True

    agent = newsroom.NewsroomAgent(random.Random(0),
                                   extractor=MinusOne())
    before = {i: agent.L.get_score(c) for i, c in agent.facts.items()}
    agent.ingest("[wire-a] something off-topic", "wire-a", 0)
    agent.ingest_extracted(99, True, "wire-a", 0)
    agent.ingest_extracted("3", True, "wire-a", 0)
    assert agent.dropped_extractions == 3
    assert {i: agent.L.get_score(c)
            for i, c in agent.facts.items()} == before
    assert agent.pending == []
    agent.close()


def test_valid_extraction_still_ingests():
    agent = newsroom.NewsroomAgent(random.Random(0))
    agent.ingest_extracted(3, True, "wire-a", 0)
    assert agent.dropped_extractions == 0
    assert agent.L.get_score(agent.facts[3]) > 0.5
    agent.close()
