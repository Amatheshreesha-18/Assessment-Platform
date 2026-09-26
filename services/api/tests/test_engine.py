import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[3]))
from packages.deterministic_engine.engine import seeded_cases, score_results

def test_seeded_cases_are_reproducible():
    cases=[{'input':'x','expected':'$seeded_int','points':10}]
    assert seeded_cases({'question':'q','seed':7},cases)==seeded_cases({'question':'q','seed':7},cases)

def test_score_is_normalized_and_authoritative():
    assert score_results([{'passed':True,'points':50},{'passed':False,'points':50}])['score']==50
