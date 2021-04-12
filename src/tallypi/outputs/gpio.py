"""LED outputs using the GPIO interface of the RPi
"""
from typing import Dict, Tuple, ClassVar
import gpiozero
import colorzero

from tslumd import TallyType, TallyColor, Tally

from tallypi.common import SingleTallyConfig, BaseOutput, Pixel, Rgb

class BaseLED(BaseOutput):
    """Base class for GPIO LEDs

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        active_high(bool): Set to ``True`` (the default) for common cathode LEDs,
            ``False`` for common anode LEDs
    """
    active_high: bool
    def __init__(self, config: SingleTallyConfig, active_high: bool = True):
        super().__init__(config)
        self.active_high = active_high

    async def open(self):
        if self.running:
            return
        self.running = True
        self.led = self._create_led()

    async def close(self):
        if not self.running:
            return
        self.led.off()
        self.led.close()
        self.led = None
        self.running = False

    def _create_led(self):
        raise NotImplementedError

    def set_led(self, color: TallyColor, brightness: float):
        """Set the LED values from the given color and brightness
        """
        raise NotImplementedError

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        if not self.running:
            return
        if tally.index != self.tally_index:
            return
        color = getattr(tally, self.tally_type.name)
        brightness = tally.brightness / 4
        self.set_led(color, brightness)

class SingleLED(BaseLED):
    """Base class for LEDs that use a single GPIO pin

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        pin(int): The GPIO pin number for the LED
        active_high(bool): Set to ``True`` (the default) for common cathode LEDs,
            ``False`` for common anode LEDs
    """
    pin: int #: The GPIO pin number for the LED
    def __init__(self, config: SingleTallyConfig, pin: int, active_high: bool = True):
        super().__init__(config, active_high)
        self.pin = pin


class LED(SingleLED):
    """A single color, non-dimmed LED

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        pin (int): The GPIO pin number for the LED
        active_high(bool): Set to ``True`` (the default) for common cathode LEDs,
            ``False`` for common anode LEDs
    """
    def _create_led(self):
        return gpiozero.LED(self.pin, active_high=self.active_high)

    def set_led(self, color: TallyColor, brightness: float):
        state = color != TallyColor.OFF
        if state:
            self.led.on()
        else:
            self.led.off()


class PWMLED(SingleLED):
    """A single color, dimmable (PWM) LED

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        pin (int): The GPIO pin number for the LED
        active_high(bool): Set to ``True`` (the default) for common cathode LEDs,
            ``False`` for common anode LEDs
    """
    def _create_led(self):
        return gpiozero.PWMLED(self.pin, active_high=self.active_high)

    def set_led(self, color: TallyColor, brightness: float):
        state = color != TallyColor.OFF
        if state:
            self.led.value = brightness
        else:
            self.led.value = 0

class RGBLED(BaseLED):
    """A full color RGB LED using PWM dimming

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        pins: Initial value for :attr:`pins`
        active_high(bool): Set to ``True`` (the default) for common cathode LEDs,
            ``False`` for common anode LEDs
    """

    pins: Tuple[int, int, int]
    """The GPIO pin numbers for each of the red, green and blue components
    """

    color_map: ClassVar[Dict[TallyColor, colorzero.Color]] = {
        TallyColor.RED: colorzero.Color('red'),
        TallyColor.GREEN: colorzero.Color('green'),
        TallyColor.AMBER: colorzero.Color('#ffbf00'),
    }

    def __init__(self, config: SingleTallyConfig, pins: Tuple[int, int, int], active_high: bool = True):
        super().__init__(config, active_high)
        self.pins = pins

    def _create_led(self):
        return gpiozero.RGBLED(*self.pins, active_high=self.active_high)

    def set_led(self, color: TallyColor, brightness: float):
        if color == TallyColor.OFF:
            self.led.off()
        else:
            led_color = self.color_map[color] * colorzero.Lightness(brightness)
            self.led.color = self.color_map[color]
