import asyncio
import argparse

from tslumd import UmdReceiver, TallyType

from tallypi.outputs.rgbmatrix5x5 import Indicator, Matrix


async def run(tally_index: int, tally_type: TallyType, matrix_mode: bool = False):
    loop = asyncio.get_event_loop()

    if matrix_mode:
        indicator = Matrix(tally_index)
    else:
        indicator = Indicator(tally_index, tally_type)

    receiver = UmdReceiver()
    running = True

    async with indicator:

        receiver.bind_async(loop,
            on_tally_added=indicator.on_receiver_tally_change,
            on_tally_updated=indicator.on_receiver_tally_change,
        )

        async with receiver:
            try:
                while running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                return

def main():
    p = argparse.ArgumentParser()
    p.add_argument('-i', '--index', dest='tally_index', type=int, help='Tally index')
    p.add_argument(
        '-t', '--type', dest='tally_type',
        choices=('rh_tally', 'txt_tally', 'lh_tally'),
        default='lh_tally',
        help='Tally type',
    )
    p.add_argument(
        '-m', '--matrix', dest='matrix_mode',
        action='store_true',
        help='Display tallies in a matrix of 5 rows (beginning with "--index")',
    )
    args = p.parse_args()
    args.tally_type = getattr(TallyType, args.tally_type)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(args.tally_index, args.tally_type, args.matrix_mode))

if __name__ == '__main__':
    main()
