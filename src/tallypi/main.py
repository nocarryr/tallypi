from loguru import logger
import signal
import asyncio

from tallypi.manager import Manager

def main():
    async def shutdown(sig, loop, mgr):
        logger.debug(f'Received {sig.name} signal, shutting down..')
        await mgr.close()
        loop.stop()

    loop = asyncio.get_event_loop()
    mgr = Manager()
    loop.run_until_complete(mgr.open())
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, loop, mgr))
        )
    try:
        loop.run_forever()
    finally:
        loop.close()

if __name__ == '__main__':
    main()
