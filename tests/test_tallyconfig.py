import pytest

from tslumd import TallyType, TallyKey, Tally
from tallypi.common import SingleTallyConfig, MultiTallyConfig

@pytest.fixture
def matched_ttypes():
    return (
        ('rh', 'rh|txt', 'rh|lh', 'all'),
        ('txt', 'txt|rh', 'txt|lh', 'all'),
        ('lh', 'lh|rh', 'lh|txt', 'all'),
    )

@pytest.fixture
def unmatched_ttypes():
    return (
        ('rh', 'txt', 'lh', 'txt|lh'),
        ('lh', 'txt', 'rh', 'txt|rh'),
        ('txt', 'rh', 'lh', 'rh|lh'),
    )

@pytest.fixture
def matched_sconfs(matched_ttypes):
    return [[
        SingleTallyConfig(
            screen_index=0,
            tally_index=0,
            tally_type=TallyType.from_str(ttype)
        ) for ttype in ttypes] for ttypes in matched_ttypes
    ]

@pytest.fixture
def unmatched_sconfs(unmatched_ttypes):
    return [[
        SingleTallyConfig(
            screen_index=0,
            tally_index=0,
            tally_type=TallyType.from_str(ttype)
        ) for ttype in ttypes] for ttypes in unmatched_ttypes
    ]


def test_single_tally_matching():
    tally_type = TallyType.rh_tally
    for i in range(10):
        all_screens = SingleTallyConfig(
            screen_index=None, tally_index=i, tally_type=tally_type,
        )
        assert all_screens.matches_screen(0xffff)

        for j in range(10):
            assert all_screens.matches_screen(j)

            tconf0 = SingleTallyConfig(
                screen_index=j, tally_index=i, tally_type=tally_type,
            )
            tconf1 = SingleTallyConfig(
                screen_index=j, tally_index=i+1, tally_type=tally_type,
            )
            tconf2 = SingleTallyConfig(
                screen_index=j+1, tally_index=i, tally_type=tally_type,
            )
            tconfs = [tconf0, tconf1, tconf2]

            for tconf in tconfs:
                assert tconf.matches(tconf.id, tconf.tally_type)
                assert tconf.matches(tconf.id, tconf.tally_type, return_matched=True) is tconf
                assert tconf.matches(tconf, tally_type=TallyType.from_str('rh|lh'))
                assert not tconf.matches(tconf, tally_type=TallyType.txt_tally)
                assert tconf.matches_screen(0xffff)
                assert tconf.matches_screen(all_screens)
                assert all_screens.matches_screen(tconf)
                if tconf.tally_index == i:
                    assert tconf.matches(all_screens)
                    assert tconf.matches(all_screens.id, all_screens.tally_type)
                else:
                    assert not tconf.matches(all_screens)
                    assert not tconf.matches(all_screens.id, all_screens.tally_type)

            assert tconf0.matches_screen(tconf1)
            assert tconf0.matches_screen(j)
            assert not tconf0.matches_screen(tconf2)
            assert not tconf0.matches_screen(j+1)
            assert not tconf0.matches(tconf1)
            assert not tconf0.matches(tconf1.id, tconf1.tally_type)
            assert not tconf0.matches(tconf2)
            assert not tconf0.matches(tconf2.id, tconf2.tally_type)

def test_multi_tally_matching():
    tally_type = TallyType.rh_tally
    for i in range(10):
        tally_index = i
        tconf_broadcast = SingleTallyConfig(
            screen_index=None, tally_index=tally_index, tally_type=tally_type,
        )
        tconf_single_scr = SingleTallyConfig(
            screen_index=i, tally_index=tally_index, tally_type=tally_type,
        )
        allow_all_single_scr = MultiTallyConfig(
            screen_index=i, allow_all=True,
        )
        allow_all_bc_scr = MultiTallyConfig(
            screen_index=None, allow_all=True,
        )

        assert tconf_broadcast.matches_screen(0xffff)
        assert tconf_broadcast.matches_screen(i)
        assert tconf_single_scr.matches_screen(i)

        assert allow_all_bc_scr.matches_screen(0xffff)
        assert allow_all_bc_scr.matches_screen(i)
        assert allow_all_single_scr.matches_screen(i)
        assert allow_all_single_scr.matches_screen(0xffff)

        assert allow_all_bc_scr.matches(tconf_broadcast)
        assert allow_all_bc_scr.matches(tconf_single_scr)
        assert allow_all_single_scr.matches(tconf_broadcast)
        assert allow_all_bc_scr.matches(tconf_broadcast)

        for j in range(10):
            tconf0 = SingleTallyConfig(
                screen_index=j, tally_index=tally_index, tally_type=tally_type,
            )
            tconf1 = SingleTallyConfig(
                screen_index=j+1, tally_index=tally_index, tally_type=tally_type,
            )
            mconf0 = MultiTallyConfig(
                screen_index=j, allow_all=True,
            )
            mconf1 = MultiTallyConfig(
                screen_index=j+1, allow_all=True
            )

            assert mconf0.matches_screen(0xffff)
            assert mconf0.matches_screen(j)
            assert not mconf0.matches_screen(j+1)

            assert mconf0.matches(tconf0)
            assert not mconf0.matches(tconf1)
            assert mconf1.matches(tconf1)
            assert not mconf1.matches(tconf0)

            assert allow_all_bc_scr.matches(tconf0)
            assert allow_all_bc_scr.matches(tconf1)

            if i == j:
                assert allow_all_single_scr.matches(tconf0)
                assert not allow_all_single_scr.matches(tconf1)
            else:
                assert not allow_all_single_scr.matches(tconf0)


def test_single_tally_type_matching(matched_sconfs, unmatched_sconfs):
    all_match = SingleTallyConfig(
        screen_index=0,
        tally_index=0,
        tally_type=TallyType.all_tally,
    )
    no_match = SingleTallyConfig(
        screen_index=0,
        tally_index=0,
        tally_type=TallyType.no_tally,
    )

    for sconfs in matched_sconfs:
        for sconf0 in sconfs:
            assert sconf0.matches(all_match)
            assert not sconf0.matches(no_match)
            assert sconf0.matches(sconf0.id, tally_type=TallyType.all_tally)
            assert not sconf0.matches(sconf0.id, tally_type=TallyType.no_tally)
            for sconf1 in sconfs:
                assert sconf0.matches(sconf1)
                assert sconf0.matches((0,0), sconf1.tally_type)
                assert sconf0.matches(sconf1, TallyType.all_tally)
                assert not sconf0.matches(sconf1, TallyType.no_tally)

    for sconfs in unmatched_sconfs:
        sconf0 = sconfs[0]
        assert sconf0.matches(all_match)
        assert not sconf0.matches(no_match)
        for sconf1 in sconfs[1:]:
            assert not sconf0.matches(sconf1)
            assert not sconf0.matches((0,0), sconf1.tally_type)
            assert not sconf0.matches(sconf1, TallyType.all_tally)
            assert not sconf0.matches(sconf1, TallyType.no_tally)

def test_multi_tally_type_matching(matched_sconfs, unmatched_sconfs):
    def copy_confs(confs, flat=True):
        ret = []
        for item in confs:
            if isinstance(item, list):
                item = copy_confs(item)
                ret.extend(item)
            else:
                item = SingleTallyConfig(
                    screen_index=item.screen_index,
                    tally_index=item.tally_index,
                    tally_type=item.tally_type
                )
                ret.append(item)
        return ret

    all_match = SingleTallyConfig(
        screen_index=0,
        tally_index=0,
        tally_type=TallyType.all_tally,
    )
    no_match = SingleTallyConfig(
        screen_index=0,
        tally_index=0,
        tally_type=TallyType.no_tally,
    )

    mconf = MultiTallyConfig(tallies=copy_confs(matched_sconfs))
    for sconfs in matched_sconfs:
        for sconf0 in sconfs:
            assert mconf.matches(sconf0)
            assert mconf.matches(sconf0, sconf0.tally_type)
            assert mconf.matches(sconf0.id, sconf0.tally_type)
            assert mconf.matches(all_match)
            assert mconf.matches(all_match, all_match.tally_type)
            assert mconf.matches(all_match.id, all_match.tally_type)
            assert not mconf.matches(no_match)
            assert not mconf.matches(no_match, no_match.tally_type)
            assert not mconf.matches(sconf0.id, no_match.tally_type)

            for sconf1 in sconfs:
                assert mconf.matches(sconf0, sconf1.tally_type)
                assert mconf.matches(sconf0.id, sconf1.tally_type)


    for sconfs in unmatched_sconfs:
        sconf0 = sconfs[0]
        mconf0 = MultiTallyConfig(tallies=[sconf0])
        mconf1 = MultiTallyConfig(tallies=copy_confs(sconfs[1:]))
        assert mconf0.matches(sconf0)
        assert not mconf1.matches(sconf0)
        for sconf1 in sconfs[1:]:
            assert not mconf0.matches(sconf1)
