import asyncio
from pathlib import Path
import pytest

from tslumd import TallyType
from tallypi.manager import Manager
from tallypi.common import SingleTallyConfig
from tallypi.baseio import BaseIO

DATA_DIR = Path(__file__).parent / 'data'

@pytest.fixture
def empty_conf(tmp_path):
    conf_fn = tmp_path / 'config' / 'tallypi.yaml'
    conf_fn.parent.mkdir()
    return conf_fn

@pytest.fixture
def umd_led_conf(empty_conf):
    src = DATA_DIR / 'tallypi.yaml'
    empty_conf.write_text(src.read_text())
    return empty_conf

@pytest.mark.asyncio
async def test_readonly_override(umd_led_conf):
    orig_conf = umd_led_conf.read_text()
    print('<orig-------')
    print(orig_conf)
    print('-------orig>')

    mgr = Manager(config_filename=umd_led_conf, readonly=True)
    assert mgr.readonly and mgr._readonly

    await mgr.read_config()

    cls = BaseIO.get_class_for_namespace('input.gpio.GpioInput')

    gpio_in1 = cls(
        config=SingleTallyConfig(
            tally_index=2, tally_type=TallyType.txt_tally, name='Txt 2',
        ),
        pin=20,
    )

    mgr.config_write_evt.clear()
    await mgr.add_input(gpio_in1)

    try:
        await asyncio.wait_for(mgr.config_write_evt.wait(), .1)
    except asyncio.TimeoutError:
        pass

    assert not mgr.config_write_evt.is_set()

    assert umd_led_conf.read_text() == orig_conf

    gpio_in2 = cls(
        config=SingleTallyConfig(
            tally_index=3, tally_type=TallyType.txt_tally, name='Txt 3',
        ),
        pin=21,
    )

    async with mgr.readonly_override as config_write_evt:
        assert mgr.readonly and not mgr._readonly
        await mgr.add_input(gpio_in2)
        await config_write_evt.wait()

    assert mgr.readonly and mgr._readonly

    print('<current----')
    print(umd_led_conf.read_text())
    print('----current>')

    assert umd_led_conf.read_text() != orig_conf
