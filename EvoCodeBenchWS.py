import asyncio
import inspect
import itertools
import json
import time
from functools import wraps
from typing import Any, Callable

from loguru import logger
from websockets.asyncio.server import serve, ServerConnection
from websockets.exceptions import ConnectionClosedError
from websockets.sync.client import connect


def get_function_signature(func):
    """检测函数的签名和类型，返回参数信息的字典。"""
    # 检查函数类型，并获取实际的函数对象
    if isinstance(func, staticmethod):
        # 如果是静态方法，提取底层函数
        actual_func = func.__func__
        func_type = 'staticmethod'
    elif isinstance(func, classmethod):
        # 如果是类方法，提取底层函数
        actual_func = func.__func__
        func_type = 'classmethod'
    else:
        # 普通函数或实例方法
        actual_func = func
        func_type = 'function'

    sig = inspect.signature(actual_func)
    params = list(sig.parameters.values())
    params_info = {}

    # 处理参数列表
    if func_type == 'function':
        # 检查函数是否在类中定义（通过 __qualname__ 属性）
        if '.' in actual_func.__qualname__:
            # 函数在类中定义，认为是实例方法，排除第一个参数
            params_to_use = params[1:]
            func_type = "instance_function"
        else:
            # 普通函数，使用所有参数
            params_to_use = params
    elif func_type == 'classmethod':
        # 类方法，排除第一个参数（通常是 cls）
        params_to_use = params[1:]
    else:
        # 静态方法，使用所有参数
        params_to_use = params

    # 构建参数信息字典
    for param in params_to_use:
        param_name = param.name
        param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
        params_info[param_name] = param_type

    return {
        'function': actual_func,
        'type': func_type,
        'params': params_info
    }


def detect_function(func):
    """装饰器，调用检测函数并包装原始函数。"""
    func_info = get_function_signature(func)
    func_type = func_info['type']
    actual_func = func_info['function']
    params_info = func_info['params']

    # 输出函数签名信息
    print(f"Function '{actual_func.__name__}' signature: {params_info}")

    @wraps(actual_func)
    def wrapper(*args, **kwargs):
        # 调用原始函数
        return actual_func(*args, **kwargs)

    # 根据函数类型返回适当的包装器
    if func_type == 'staticmethod':
        return staticmethod(wrapper)
    elif func_type == 'classmethod':
        return classmethod(wrapper)
    else:
        return wrapper


class WebSocketServer:
    def __init__(self) -> None:
        self.serves_info = []

    def add_serve(self, handler: Callable, host: str, port: int): self.serves_info.append((handler, host, port))

    def create_awaitable_handler(self, handler, host, port):
        async def awaitable_handler(connection: ServerConnection):
            try:
                async for message in connection:
                    result = handler(**json.loads(message))
                    await connection.send(json.dumps(result))
            except ConnectionClosedError:
                logger.error(f"Connection closed on socket `ws://{host}:{port}`")
            except Exception as e:
                logger.exception(f"unknown error :{e}")
        return awaitable_handler

    async def run(self):
        servers = []
        for handler, host, port in self.serves_info:
            handler: Callable
            awaitable_handler = self.create_awaitable_handler(handler, host, port)
            logger.success(f"function `{handler.__name__}` listen on ws://{host}:{port}")
            server = await serve(awaitable_handler, host, port)
            servers.append(server)
        await asyncio.Future()


class WebSocketClient:
    def __init__(self, max_waiting: float = 120, rest_in_sec: float = 2) -> None:
        self.servers: dict[str, list] = dict()
        self.all_servers: list = []
        self.enable = False
        self.max_waiting: float = max_waiting
        self.rest_in_sec: float = rest_in_sec

    def add_server(self, key: str, host: str, port: int):
        if key not in self.servers:
            self.servers[key] = []
        ws_server = f"ws://{host}:{port}"
        self.servers[key].append(ws_server)
        self.all_servers.append(ws_server)

    def regist_faas(self, func: Callable):
        func_info = get_function_signature(func)
        func_type = func_info['type']
        actual_func = func_info['function']
        params_info: dict = func_info['params']

        print(f"Function '{actual_func.__name__}' signature: {params_info} type:{func_type}")

        def dictize(*args, **kwargs):
            keys = list(params_info.keys())[:len(args)]
            if func_type == "instance_function":  # NOTE::实例方法，丢弃self(无法被序列化)
                args = args[1:]
            paras = {key: value for key, value in zip(keys, args)}
            return json.dumps(paras | kwargs)

        @wraps(actual_func)
        def wrapper(*args, **kwargs):
            def in_source(*args, **kwargs): return actual_func(*args, **kwargs)

            def in_connection(*args, **kwargs):
                start = time.time()
                while server := next(itertools.cycle(self.all_servers)):
                    try:
                        with connect(server) as connection:
                            connection.send(dictize(*args, **kwargs))
                            ret = connection.recv()
                            return json.loads(ret)
                    except ConnectionClosedError:
                        logger.info(f"server `{server}` is busy, try another")
                    except Exception as e:
                        logger.info(f"server `{server}` need lookup: {e}")
                        logger.exception()
                    finally:
                        if time.time()-start >= self.max_waiting:
                            return
                    time.sleep(self.rest_in_sec)

            if self.enable:
                return in_connection(*args, **kwargs)
            else:
                return in_source(*args, **kwargs)

        return wrapper
