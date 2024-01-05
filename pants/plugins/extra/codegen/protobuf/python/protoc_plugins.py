import enum

class ProtocPlugins(enum.Enum):
    GRPCIO = "grpcio"
    GRPCLIB = "grpclib"

    def grpc_module_suffix(self) -> str:
        if self is self.GRPCIO:
            return "pb2_grpc"
        elif self is self.GRPCLIB:
            return "_grpc"
        return ""
