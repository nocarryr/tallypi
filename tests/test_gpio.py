import asyncio
import pytest

from tslumd import TallyType, TallyColor, Tally, Screen


@pytest.mark.asyncio
async def test_color_merge(fake_gpio):
    from tallypi.common import SingleTallyConfig
    from tallypi.inputs.gpio import GpioInput
    from tallypi.outputs.gpio import RGBLED

    tally_key = (1, 1)
    screen_index, tally_index = tally_key
    tally_type = TallyType.rh_tally

    input_pin_num = {'red':1, 'green':2}
    # input_pins = {k: Device.pin_factory.pin(v) for k,v in input_pin_num.items()}
    output_pin_num = (5, 6, 7)

    input_confs = {
        'red':SingleTallyConfig(
            screen_index=screen_index,
            tally_index=tally_index,
            tally_type=tally_type,
            color_mask=TallyColor.RED,
        ),
        'green':SingleTallyConfig(
            screen_index=screen_index,
            tally_index=tally_index,
            tally_type=tally_type,
            color_mask=TallyColor.GREEN,
        ),
    }
    output_conf = SingleTallyConfig(
        screen_index=screen_index,
        tally_index=tally_index,
        tally_type=tally_type,
    )

    inputs = {k:GpioInput(conf, input_pin_num[k]) for k,conf in input_confs.items()}
    inputs['red'].id = 'Gpio.red'
    inputs['green'].id = 'Gpio.green'
    output = RGBLED(output_conf, output_pin_num)

    async with inputs['red']:
        async with inputs['green']:
            async with output:

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.OFF
                assert not output.led.is_active

                for inp in inputs.values():
                    await output.bind_to_input(inp)

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.OFF
                assert not output.led.is_active

                # input_pins['red'].drive_high()
                # inputs['red'].button.pin.drive_high()
                inputs['red']._set_tally_state(True)
                await asyncio.sleep(.1)

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.RED
                assert output.led.is_active
                assert output.led.color == output.color_map[TallyColor.RED]

                # input_pins['red'].drive_low()
                # input_pins['green'].drive_high()
                inputs['red']._set_tally_state(False)
                inputs['green']._set_tally_state(True)
                await asyncio.sleep(.1)

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.GREEN
                assert output.led.is_active
                assert output.led.color == output.color_map[TallyColor.GREEN]

                # input_pins['red'].drive_high()
                # input_pins['green'].drive_high()
                inputs['red']._set_tally_state(True)
                inputs['green']._set_tally_state(True)
                await asyncio.sleep(.1)

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.AMBER
                assert output.led.is_active
                assert output.led.color == output.color_map[TallyColor.AMBER]

                # input_pins['red'].drive_low()
                # input_pins['green'].drive_low()
                inputs['red']._set_tally_state(False)
                inputs['green']._set_tally_state(False)
                await asyncio.sleep(.1)

                assert output.get_merged_tally(tally_key, tally_type) == TallyColor.OFF
                assert not output.led.is_active
