import asyncio

from EvoCodeBenchWS import WebSocketServer

server = WebSocketServer()


def handle(*args, **kwargs):
    print(args, kwargs)
    return {"rest": "OK"}


server.add_serve(handle, "localhost", 8765)


asyncio.run(server.run())