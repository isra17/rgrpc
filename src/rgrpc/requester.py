import asyncio
import ssl as _ssl
import typing as t
import warnings

import grpclib.client
import grpclib.const
import grpclib.server
import h2.config

from grpclib._registry import servers as _servers
from grpclib.config import Configuration
from grpclib.encoding.base import CodecBase
from grpclib.encoding.base import StatusDetailsCodecBase
from grpclib.encoding.proto import ProtoCodec
from grpclib.encoding.proto import ProtoStatusDetailsCodec
from grpclib.encoding.proto import _googleapis_available
from grpclib.events import _DispatchServerEvents
from grpclib.protocol import H2Protocol
from grpclib.server import Server


if t.TYPE_CHECKING:
    from grpclib._typing import IServable

__version__ = "0.1.0"


class Requester:
    def __init__(
        self,
        handlers: t.Collection["IServable"],
        *,
        host: t.Optional[str] = None,
        port: t.Optional[int] = None,
        path: t.Optional[str] = None,
        ssl: t.Union[None, bool, _ssl.SSLContext, _ssl.DefaultVerifyPaths] = None,
        codec: t.Optional[CodecBase] = None,
        status_details_codec: t.Optional[StatusDetailsCodecBase] = None,
        config: t.Optional[Configuration] = None,
    ) -> None:
        if path is not None and (host is not None or port is not None):
            raise ValueError(
                "The 'path' parameter can not be used with the "
                "'host' or 'port' parameters.",
            )
        else:
            if host is None:
                host = "127.0.0.1"

            if port is None:
                port = 50051

        if ssl is True:
            ssl = self._get_default_ssl_context()
        elif isinstance(ssl, _ssl.DefaultVerifyPaths):
            ssl = self._get_default_ssl_context(verify_paths=ssl)

        self._host = host
        self._port = port
        self._path = path
        self._ssl = ssl
        self._protocol = None

        mapping: dict[str, "grpclib.const.Handler"] = {}
        for handler in handlers:
            mapping.update(handler.__mapping__())

        self._mapping = mapping
        self._loop = asyncio.get_event_loop()

        if codec is None:
            codec = ProtoCodec()
            if status_details_codec is None and _googleapis_available():
                status_details_codec = ProtoStatusDetailsCodec()

        self._codec = codec
        self._status_details_codec = status_details_codec

        self._h2_config = h2.config.H2Configuration(
            client_side=False,
            header_encoding="ascii",
            validate_inbound_headers=False,
            validate_outbound_headers=False,
            normalize_inbound_headers=False,
            normalize_outbound_headers=False,
        )

        self._connect_lock = asyncio.Lock()
        self._state = grpclib.client._ChannelState.IDLE

        config = Configuration() if config is None else config
        self._config = config.__for_server__()

        self._handlers: set[grpclib.server.Handler] = set()

        self.__dispatch__ = _DispatchServerEvents()
        _servers.add(t.cast(Server, self))

    def _protocol_factory(self) -> H2Protocol:
        handler = grpclib.server.Handler(
            self._mapping,
            self._codec,
            self._status_details_codec,
            self.__dispatch__,
        )
        return H2Protocol(handler, self._config, self._h2_config)

    async def _create_connection(self) -> H2Protocol:
        if self._path is not None:
            _, protocol = await self._loop.create_unix_connection(
                self._protocol_factory,
                self._path,
                ssl=self._ssl,
                server_hostname=(
                    self._config.ssl_target_name_override
                    if self._ssl is not None
                    else None
                ),
            )
        else:
            _, protocol = await self._loop.create_connection(
                self._protocol_factory,
                self._host,
                self._port,
                ssl=self._ssl,
                server_hostname=(
                    self._config.ssl_target_name_override
                    if self._ssl is not None
                    else None
                ),
            )
        return protocol

    async def start(self) -> H2Protocol:
        self._server_closed_fut = self._loop.create_future()

        if not self._connected:
            async with self._connect_lock:
                self._state = grpclib.client._ChannelState.CONNECTING
                if not self._connected:
                    try:
                        self._protocol = await self._create_connection()
                    except Exception:
                        self._state = grpclib.client._ChannelState.TRANSIENT_FAILURE
                        raise
                    else:
                        self._state = grpclib.client._ChannelState.READY

        return t.cast(H2Protocol, self._protocol)

    @property
    def _connected(self) -> bool:
        return self._protocol is not None and not self._protocol.handler.connection_lost

    def _get_default_ssl_context(
        self,
        *,
        verify_paths: t.Optional[_ssl.DefaultVerifyPaths] = None,
    ) -> _ssl.SSLContext:
        if verify_paths is not None:
            cafile = verify_paths.cafile
            capath = verify_paths.capath
        else:
            try:
                import certifi
            except ImportError:
                cafile = None
            else:
                cafile = certifi.where()
            capath = None

        ctx = _ssl.create_default_context(
            purpose=_ssl.Purpose.SERVER_AUTH,
            cafile=cafile,
            capath=capath,
        )
        ctx.minimum_version = _ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
        ctx.set_alpn_protocols(["h2"])
        return ctx

    def close(self) -> None:
        """Closes connection to the server."""
        if self._protocol is not None:
            self._protocol.processor.close()
            del self._protocol
        self._state = grpclib.client._ChannelState.IDLE
        self._server_closed_fut.set_result(None)

    def __del__(self) -> None:
        if self._protocol is not None:
            message = "Unclosed connection: {!r}".format(self)
            warnings.warn(message, ResourceWarning)
            if self._loop.is_closed():
                return
            else:
                self.close()
                self._loop.call_exception_handler({"message": message})

    async def wait_closed(self) -> None:
        await self._server_closed_fut

    async def __aenter__(self) -> "Requester":
        return self

    async def __aexit__(self, *args: t.Any) -> None:
        self.close()

class B:
    pass
