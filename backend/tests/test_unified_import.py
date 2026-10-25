import pytest
from app.unified_import import infer_wing_shots,stable_id


def test_wing_residual_is_explicitly_marked_as_estimate():
    shots,flags=infer_wing_shots({'shotsTaken':10,'shots7m':2,'shots9m':1,'fastbreakShots':1,'breakthroughShots':1,'wingGoals':3},'LW')
    assert shots==5
    assert flags==['wing_shots_estimated_residual']


def test_contradictory_wing_residual_is_missing_not_zero():
    assert infer_wing_shots({'shotsTaken':2,'shots7m':3},'RW')==(None,['wing_residual_conflict'])
    assert infer_wing_shots({'shotsTaken':3,'shots7m':2,'wingGoals':2},'RW')==(None,['wing_residual_conflict'])


def test_non_wing_players_are_not_automatically_reclassified():
    assert infer_wing_shots({'shotsTaken':10},'P')[0] is None
    assert infer_wing_shots({'wingShots':0},'LW')==(0,[])


def test_provider_ids_are_stable_separate_and_javascript_safe():
    a=stable_id('game','handballapi',123)
    assert a==stable_id('game','handballapi',123)
    assert a!=stable_id('game','access',123)
    assert a!=stable_id('team','handballapi',123)
    assert -(2**53)<a<0
