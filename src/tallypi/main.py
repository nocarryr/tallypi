import asyncio

from tallypi.manager import Manager

def main():
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

if __name__ == '__main__':
    main()
