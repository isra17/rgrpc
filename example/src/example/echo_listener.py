import asyncio
import ssl

import rgrpc

from example.proto.v1 import echo_pb2
from example.proto.v1 import echo_grpc


async def main():
    async def on_client(channel: rgrpc.Channel) -> None:
        print(f"{channel=}")
        echo = echo_grpc.EchoServiceStub(channel)
        resp = await echo.Upper(echo_pb2.UpperRequest(msg="hello"))
        print(f"{resp=}")

    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # context.load_cert_chain("./cert.pem", "./key.pem")
    context = None

    server = rgrpc.Listener(on_client)
    await server.start("localhost", 50051, ssl=context)
    await server.wait_closed()


if __name__ == "__main__":
    print("starting")
    asyncio.run(main())

class B:
    pass
