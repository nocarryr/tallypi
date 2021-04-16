import asyncio
import click

from tslumd import TallyType

from tallypi.manager import Manager
from tallypi.config import Config
from tallypi.common import (
    BaseIO, BaseInput, BaseOutput, SingleTallyConfig, MultiTallyConfig,
)
from tallypi import outputs

def build_single_tally_conf(tally_index, tally_type):
    if isinstance(tally_type, str):
        tally_type = getattr(TallyType, tally_type)
    return SingleTallyConfig(tally_index=tally_index, tally_type=tally_type)

def add_object_to_config(obj: BaseIO):
    async def do_add():
        mgr = Manager()
        await mgr.read_config()
        if isinstance(obj, BaseInput):
            await mgr.add_input(obj)
        elif isinstance(obj, BaseOutput):
            await mgr.add_output(obj)
        await asyncio.sleep(.1)
        await mgr.write_config()
        click.echo(mgr.config.filename.read_text())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_add())

def check_config():
    async def do_check():
        mgr = Manager()
        await mgr.read_config()
        click.echo(mgr.config.filename.read_text())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(do_check())

@click.group()
def cli():
    pass

@cli.command('show')
def show():
    check_config()

@cli.command('run')
def run():
    loop = asyncio.get_event_loop()
    mgr = Manager()
    loop.run_until_complete(mgr.open())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(mgr.close())
    finally:
        loop.run_until_complete(mgr.close())
        loop.close()


@cli.group('add')
def add():
    pass

@add.group('input')
def add_input():
    pass

@add_input.command('umd')
@click.option('-h', '--hostaddr', default='0.0.0.0')
@click.option('-p', '--hostport', default=65000, type=int)
def add_umd_input(hostaddr, hostport):
    ns = 'input.umd.UmdInput'
    cls = BaseIO.get_class_for_namespace(ns)
    tally_conf = MultiTallyConfig(allow_all=True)
    obj = cls(tally_conf, hostaddr, hostport)
    add_object_to_config(obj)

@add.group('output')
@click.option('-i', '--tally-index', 'tally_index', required=True, type=int)
@click.option('-t', '--tally-type', 'tally_type', required=True, type=str)
@click.pass_context
def add_output(ctx, tally_index, tally_type):
    ctx.ensure_object(dict)
    ctx.obj['tally_index'] = tally_index
    ctx.obj['tally_type'] = tally_type
    ctx.obj['tally_conf'] = build_single_tally_conf(tally_index, tally_type)

@add_output.command('rgbmatrix')
@click.argument('display_type', type=click.Choice(['indicator', 'matrix']))
@click.pass_context
def add_rgbmatrix_output(ctx, display_type):
    display_type = display_type.title()
    ns = f'output.rgbmatrix5x5.{display_type}'
    cls = BaseIO.get_class_for_namespace(ns)
    tally_conf = ctx.obj['tally_conf']
    obj = cls(ctx.obj['tally_conf'])
    add_object_to_config(obj)

@add_output.command('led')
@click.option('-p', '--pin', 'pin', required=True, type=int)
@click.option('--active-low/--active-high', 'active_low', default=False)
@click.option('--pwm/--no-pwm', 'pwm', default=True)
@click.option('--brightness', 'brightness', default=1.0, type=float)
@click.pass_context
def add_led_output(ctx, pin, active_low, pwm, brightness):
    if pwm:
        ns = 'output.gpio.PWMLED'
    else:
        ns = 'output.gpio.LED'
    cls = BaseIO.get_class_for_namespace(ns)
    active_high = not active_low
    obj = cls(ctx.obj['tally_conf'], pin, active_high=active_high, brightness_scale=brightness)
    add_object_to_config(obj)

@add_output.command('rgbled')
@click.option('-p', '--pins', 'pins', nargs=3, type=int, required=True)
@click.option('--active-low/--active-high', 'active_low', default=False)
@click.option('--brightness', 'brightness', default=1.0, type=float)
@click.pass_context
def add_rgbled_output(ctx, pins, active_low, brightness):
    ns = 'output.gpio.RGBLED'
    cls = BaseIO.get_class_for_namespace(ns)
    active_high = not active_low
    obj = cls(ctx.obj['tally_conf'], pins, active_high=active_high, brightness_scale=brightness)
    add_object_to_config(obj)

if __name__ == '__main__':
    cli()
