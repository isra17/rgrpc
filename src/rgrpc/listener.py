import asyncio
import socket
import ssl as _ssl
import typing as t
import warnings

import grpclib.client
import grpclib.const
import grpclib.server
import h2.config

from grpclib._registry import channels as _channels
from grpclib.client import Stream
from grpclib.config import Configuration
from grpclib.const import Cardinality
from grpclib.encoding.base import CodecBase
from grpclib.encoding.base import StatusDetailsCodecBase
from grpclib.encoding.proto import ProtoCodec
from grpclib.encoding.proto import ProtoStatusDetailsCodec
from grpclib.encoding.proto import _googleapis_available
from grpclib.events import _DispatchChannelEvents
from grpclib.metadata import Deadline
from grpclib.metadata import _Metadata
from grpclib.metadata import _MetadataLike
from grpclib.protocol import H2Protocol as _H2Protocol
from grpclib.stream import _RecvType
from grpclib.stream import _SendType
from multidict import MultiDict


class H2Protocol(_H2Protocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.connection_event = asyncio.Event()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        super().connection_made(transport)
        self.connection_event.set()


class Channel:
    _calls_started = 0
    _calls_succeeded = 0
    _calls_failed = 0
    _last_call_started: t.Optional[float] = None

    def __init__(
        self,
        *,
        protocol: H2Protocol,
        codec: CodecBase,
        status_details_codec: t.Optional[StatusDetailsCodecBase],
    ) -> None:
        self._protocol = protocol
        self._codec = codec
        self._status_details_codec = status_details_codec
        self._loop = asyncio.get_event_loop()
        self.__dispatch__ = _DispatchChannelEvents()
        self._scheme = "https"
        self._authority = socket.gethostname()
        _channels.add(t.cast(grpclib.client.Channel, self))

    @property
    def _connected(self) -> bool:
        return self._protocol is not None

    async def __connect__(self) -> H2Protocol:
        if not self._connected:
            raise ValueError("Cannot reconnect Channel")
        return self._protocol

    def request(
        self,
        name: str,
        cardinality: Cardinality,
        request_type: t.Type[_SendType],
        reply_type: t.Type[_RecvType],
        *,
        timeout: t.Optional[float] = None,
        deadline: t.Optional[Deadline] = None,
        metadata: t.Optional[_MetadataLike] = None,
    ) -> Stream[_SendType, _RecvType]:
        if timeout is not None and deadline is None:
            deadline = Deadline.from_timeout(timeout)
        elif timeout is not None and deadline is not None:
            deadline = min(Deadline.from_timeout(timeout), deadline)

        metadata = t.cast(_Metadata, MultiDict(metadata or ()))

        return Stream(
            t.cast(grpclib.client.Channel, self),
            name,
            metadata,
            cardinality,
            request_type,
            reply_type,
            codec=self._codec,
            status_details_codec=self._status_details_codec,
            dispatch=self.__dispatch__,
            deadline=deadline,
        )

    def close(self) -> None:
        """Closes connection to the server."""
        if self._protocol is not None:
            self._protocol.processor.close()
            del self._protocol
            self._protocol = None

    def __del__(self) -> None:
        if self._protocol is not None:
            message = "Unclosed connection: {!r}".format(self)
            warnings.warn(message, ResourceWarning)
            if self._loop.is_closed():
                return
            else:
                self.close()
                self._loop.call_exception_handler({"message": message})

    async def __aenter__(self) -> "Channel":
        return self

    async def __aexit__(self, *args: t.Any) -> None:
        self.close()


class Listener:
    def __init__(
        self,
        client_handler: t.Callable[[Channel], t.Awaitable[None]],
        *,
        config: t.Optional[Configuration] = None,
        codec: t.Optional[CodecBase] = None,
        status_details_codec: t.Optional[StatusDetailsCodecBase] = None,
    ) -> None:
        if codec is None:
            codec = ProtoCodec()
            if status_details_codec is None and _googleapis_available():
                status_details_codec = ProtoStatusDetailsCodec()

        self._loop = asyncio.get_event_loop()

        config = Configuration() if config is None else config
        self._config = config.__for_client__()
        self._h2_config = h2.config.H2Configuration(
            client_side=True,
            header_encoding="ascii",
            validate_inbound_headers=False,
            validate_outbound_headers=False,
            normalize_inbound_headers=False,
            normalize_outbound_headers=False,
        )
        self._codec = codec
        self._status_details_codec = status_details_codec
        self._client_handler = client_handler
        self._server_closed_fut = None
        self._server = None
        self._clients_handlers: set[asyncio.Task] = set()

    async def start(
        self,
        host: t.Optional[str] = None,
        port: t.Optional[int] = None,
        *,
        path: t.Optional[str] = None,
        family: socket.AddressFamily = socket.AF_UNSPEC,
        flags: socket.AddressInfo = socket.AI_PASSIVE,
        sock: t.Optional[socket.socket] = None,
        backlog: int = 100,
        ssl: t.Optional[_ssl.SSLContext] = None,
        reuse_address: t.Optional[bool] = None,
        reuse_port: t.Optional[bool] = None,
    ) -> None:
        if path is not None and (host is not None or port is not None):
            raise ValueError(
                "The 'path' parameter can not be used with the "
                "'host' or 'port' parameters.",
            )

        if self._server is not None:
            raise RuntimeError("Server is already started")

        if path is not None:
            self._server = await self._loop.create_unix_server(
                self._connection_handler,
                path,
                sock=sock,
                backlog=backlog,
                ssl=ssl,
            )
        else:
            self._server = await self._loop.create_server(
                self._connection_handler,
                host,
                port,
                family=family,
                flags=flags,
                sock=sock,
                backlog=backlog,
                ssl=ssl,
                reuse_address=reuse_address,
                reuse_port=reuse_port,
            )
        self._server_closed_fut = self._loop.create_future()

    async def _handle_client(self, channel: Channel) -> None:
        async with channel:
            await channel._protocol.connection_event.wait()
            await self._client_handler(channel)

    def _connection_handler(self) -> H2Protocol:
        protocol = H2Protocol(grpclib.client.Handler(), self._config, self._h2_config)
        channel = Channel(
            protocol=protocol,
            codec=self._codec,
            status_details_codec=self._status_details_codec,
        )
        self._clients_handlers.add(asyncio.create_task(self._handle_client(channel)))
        return protocol

    def close(self) -> None:
        """Stops accepting new connections, cancels all currently running
        requests.

        Request handlers are able to handle `CancelledError` and exit
        properly.
        """
        if self._server is None or self._server_closed_fut is None:
            raise RuntimeError("Server is not started")
        self._server.close()
        if not self._server_closed_fut.done():
            self._server_closed_fut.set_result(None)

    async def wait_closed(self) -> None:
        """Coroutine to wait until all existing request handlers will exit
        properly."""
        if self._server is None or self._server_closed_fut is None:
            raise RuntimeError("Server is not started")
        await self._server_closed_fut
        await self._server.wait_closed()

    async def __aenter__(self) -> "Listener":
        return self

    async def __aexit__(self, *args: t.Any) -> None:
        self.close()
        await self.wait_closed()
