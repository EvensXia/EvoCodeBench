from EvoCodeBenchWS import WebSocketClient

client = WebSocketClient()
client.enable = True
client.add_server("s", "localhost", 8765)


class A:
    @client.regist_faas
    def call(self, h1, h2):
        print(h1, h2, "SSSS")
        return {"local": "OK"}


a = A()
print(a.call(5, 6))
client.enable = False
print(a.call(5, 6))
