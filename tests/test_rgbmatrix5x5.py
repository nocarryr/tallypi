import asyncio
import pytest

from tslumd import TallyType, TallyColor, Tally
from tallypi.common import SingleTallyConfig


@pytest.mark.asyncio
async def test_mocked_rgb5x5(fake_rgb5x5, faker):
    from tallypi.outputs.rgbmatrix5x5 import Indicator

    config = SingleTallyConfig(tally_index=0, tally_type=TallyType.lh_tally)
    indicator = Indicator(config)

    colors = {(x,y):(0,0,0) for y in range(5) for x in range(5)}
    async with indicator:
        assert indicator.device.pixels == colors
        for _ in range(100):

            for x in range(5):
                for y in range(5):
                    color = [int(s) for s in faker.rgb_color().split(',')]
                    colors[(x,y)] = tuple(color)
                    indicator.device.set_pixel(x, y, *color)
                    assert indicator.device.pixels == colors


@pytest.mark.asyncio
async def test_indicator(fake_rgb5x5, faker):
    from tallypi.outputs.rgbmatrix5x5 import Indicator

    config = SingleTallyConfig(tally_index=0, tally_type=TallyType.lh_tally)
    indicator = Indicator(config)
    screen, tally = config.create_tally()


    async with indicator:
        device = indicator.device
        for _ in range(2):
            for tally_color in TallyColor:
                await indicator.set_color(tally_color)
                rgb = indicator.color_map[tally_color]
                assert all([c == rgb for c in device.pixels.values()])

        for _ in range(2):
            for tally_color in TallyColor:
                tally.lh_tally = tally_color

                await indicator.on_receiver_tally_change(None, tally, set(['lh_tally']))
                rgb = indicator.color_map[tally_color]
                assert all([c == rgb for c in device.pixels.values()])

        tally.lh_tally = TallyColor.RED
        rgb = indicator.color_map[TallyColor.RED]
        for i in range(3):
            tally.brightness = i
            await indicator.on_receiver_tally_change(None, tally, set(['brightness']))
            assert all([c == rgb for c in device.pixels.values()])
            assert device.brightness == tally.normalized_brightness
