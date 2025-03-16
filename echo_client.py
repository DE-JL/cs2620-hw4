from config import SERVER_PORT
from protos.chat_pb2 import *
from protos.chat_pb2_grpc import *


def main():
    server_addr = f"localhost:{SERVER_PORT}"
    with grpc.insecure_channel(server_addr) as channel:
        stub = ChatStub(channel)

        while True:
            s = input("> ")

            response = stub.Echo(EchoRequest(message=s))

            print(f"SENT: {s}")
            print(f"RECEIVED: {response.message}")


if __name__ == "__main__":
    main()
