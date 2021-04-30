from tslumd import TallyType, TallyKey, Tally
from tallypi.common import SingleTallyConfig, MultiTallyConfig

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
                assert tconf.matches_screen(0xffff)
                assert tconf.matches_screen(all_screens)
                assert all_screens.matches_screen(tconf)
                if tconf.tally_index == i:
                    assert tconf.matches(all_screens)
                else:
                    assert not tconf.matches(all_screens)

            assert tconf0.matches_screen(tconf1)
            assert tconf0.matches_screen(j)
            assert not tconf0.matches_screen(tconf2)
            assert not tconf0.matches_screen(j+1)
            assert not tconf0.matches(tconf1)
            assert not tconf0.matches(tconf2)

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
