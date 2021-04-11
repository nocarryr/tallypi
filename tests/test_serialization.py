import json

from tslumd import TallyType
from tallypi.common import SingleTallyConfig, MultiTallyConfig


def test_single_tally(tally_conf_factory):
    for orig_conf in tally_conf_factory(1000):
        d = orig_conf.to_dict()
        d = json.loads(json.dumps(d))
        deserialized = SingleTallyConfig.from_dict(d)
        assert orig_conf == deserialized

def test_multi_tally(tally_conf_factory):
    orig_conf = MultiTallyConfig(allow_all=True)
    d = orig_conf.to_dict()
    d = json.loads(json.dumps(d))
    assert MultiTallyConfig.from_dict(d) == orig_conf

    orig_conf = MultiTallyConfig()
    for tconf in tally_conf_factory(100):
        orig_conf.tallies.append(tconf)

    d = orig_conf.to_dict()
    d = json.loads(json.dumps(d))
    assert MultiTallyConfig.from_dict(d) == orig_conf
