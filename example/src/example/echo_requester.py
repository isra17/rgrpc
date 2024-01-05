import grpclib.server
import asyncio
import ssl

import rgrpc

from example.proto.v1 import echo_pb2
from example.proto.v1 import echo_grpc


class EchoServer(echo_grpc.EchoServiceBase):
    async def Upper(self, stream: grpclib.server.Stream[echo_pb2.UpperRequest, echo_pb2.UpperResponse]) -> None:
        request = await stream.recv_message()
        print(f"{request=}")
        await stream.send_message(echo_pb2.UpperResponse(msg=request.msg.upper()))


async def main():
    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # context.load_verify_locations("./cert.pem")
    context = None

    service = rgrpc.Requester([EchoServer()], host="localhost", port=50051, ssl=context)
    await service.start()
    await service.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
