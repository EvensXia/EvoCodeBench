import json
import os
import shutil
import subprocess
import textwrap
import threading
import traceback
from abc import abstractmethod
from parser.add_func_call import process as rprocess
from types import SimpleNamespace
from typing import Any, Dict

import aiohttp
import func_timeout
import requests
import yaml
from flask import Flask, jsonify, request
from python_repo import PythonRepo


def adjust_indent(code, new_indent): return textwrap.indent(textwrap.dedent(code), ' ' * new_indent)


class SingletonMixin:
    _instances = {}

    def __new__(cls, *args, **kwargs):
        if cls in cls._instances:
            return cls._instances[cls]
        else:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
            instance._is_initialized = False
            return instance

    def __init__(self, *args, **kwargs):
        if not self._is_initialized:
            super().__init__(*args, **kwargs)
            self._is_initialized = True


class Test:
    @abstractmethod
    def SetUp_evaluation(self, data, completion): raise NotImplementedError
    @abstractmethod
    def TearDown_evaluation(self, data): raise NotImplementedError
    @abstractmethod
    def run_test(self): raise NotImplementedError


class EnvManager:
    def __init__(self, source_root, dest_root) -> None:
        self.source_root = source_root
        self.dest_root = dest_root

    def copy_project(self, project_name: str):
        src_env_dir = os.path.join(self.source_root, project_name)
        dst_env_dir = os.path.join(self.dest_root, project_name)
        if os.path.exists(dst_env_dir):
            return
        shutil.copy(src_env_dir, dst_env_dir)


class PassKTest(Test, EnvManager):
    def __init__(self, source_code_root, env_source_root, env_dest_root) -> None:
        self.source_code_root = source_code_root
        self.tmp_prefix = "ppppppptmp_"
        EnvManager.__init__(self, env_source_root, env_dest_root)

    def SetUp_evaluation(self, data, completion):
        completion_path = os.path.join(self.source_code_root, data['completion_path'])
        head_tail = os.path.split(completion_path)
        completion_tmp_path = os.path.join(head_tail[0], self.tmp_prefix + head_tail[1])
        subprocess.run(['cp', completion_path, completion_tmp_path])
        sos, eos = data['body_position'][0]-1, data['body_position'][1]
        with open(completion_path, 'r') as f:
            file_lines = f.readlines()
        file_lines = file_lines[:sos] + ['\n', completion, '\n'] + file_lines[eos:]
        with open(completion_path, 'w') as f:
            f.write(''.join(file_lines))

    def TearDown_evaluation(self, data):
        completion_path = os.path.join(self.source_code_root, data['completion_path'])
        head_tail = os.path.split(completion_path)
        completion_tmp_path = os.path.join(head_tail[0], self.tmp_prefix + head_tail[1])
        subprocess.run(['mv', completion_tmp_path, completion_path])

    def run_test(self, data: dict):
        completion = data['completion']
        if completion == "    pass\n":
            return 'Fail'
        completion = adjust_indent(completion, data['indent'])

        project_name = data['completion_path'].split('/')[0]
        self.copy_project(project_name)
        self.SetUp_evaluation(data, completion)
        project_path = os.path.join(self.source_code_root, project_name)
        flag = 'Pass'
        python_repo = PythonRepo(project_path)
        python_repo.prepare_env()

        for test in data['tests']:
            try:
                result = python_repo.run_test(test)
                if not result:
                    flag = 'Fail'
                    break
            except func_timeout.exceptions.FunctionTimedOut:
                flag = 'Fail'
                break
        self.TearDown_evaluation(data)
        return flag


class RecallKTest(Test, EnvManager):
    def __init__(self, source_code_root, dependency_data_root, dependency_tmp_dir, env_source_root, env_dest_root) -> None:
        self.source_code_root = source_code_root
        self.dependency_data_root = dependency_data_root
        self.dependency_tmp_dir = dependency_tmp_dir
        self.tmp_prefix = "rrrrrrrtmp_"
        EnvManager.__init__(self, env_source_root, env_dest_root)

    def SetUp_evaluation(self, data, completion):
        scompletion = adjust_indent(data['completion'], data['indent'])
        completion_path = os.path.join(self.source_code_root, data['completion_path'])
        head_tail = os.path.split(completion_path)
        completion_tmp_path = os.path.join(head_tail[0], self.tmp_prefix + head_tail[1])
        subprocess.run(['cp', completion_path, completion_tmp_path])
        sos, eos = data['body_position'][0]-1, data['body_position'][1]
        with open(completion_path, 'r') as f:
            file_lines = f.readlines()
        file_lines = file_lines[:sos] + ['\n', scompletion, '\n'] + file_lines[eos:]
        with open(completion_path, 'w') as f:
            f.write(''.join(file_lines))

    def TearDown_evaluation(self, data):
        project_name = data['completion_path'].split('/')[0]
        completion_path = os.path.join(self.source_code_root, data['completion_path'])
        head_tail = os.path.split(completion_path)
        completion_tmp_path = os.path.join(head_tail[0], self.tmp_prefix + head_tail[1])
        dependency_tmp_path = os.path.join(self.dependency_tmp_dir, project_name)
        subprocess.run(['mv', completion_tmp_path, completion_path])
        subprocess.run(['rm', '-rf', dependency_tmp_path])

    def parse_dependency(self, data):
        project_name = data['completion_path'].split('/')[0]
        project_root = os.path.join(self.source_code_root, project_name)
        file_to_parse = os.path.join(self.source_code_root, data['completion_path'])
        output_path = os.path.join(self.dependency_tmp_dir, project_name)
        analyzer_result_path = os.path.join(self.dependency_data_root, project_name, 'analyzer_result.pkl')
        try:
            rprocess(target_object=project_root, func_object_root=project_root, func_path=file_to_parse,
                     analyzer_result=analyzer_result_path, target_root=output_path)
        except Exception as e:
            return False
        return True

    def extract_dependency(self, data):
        dependency_path = os.path.join(self.dependency_tmp_dir, data['completion_path'].replace('.py', '.json'))
        if not os.path.exists(dependency_path):
            return None
        with open(dependency_path, 'r') as f:
            dependency_data = json.load(f)
        if data['namespace'] not in dependency_data:
            return None
        attributes = dependency_data[data['namespace']]
        generated_dependency = {'intra_class': [], 'intra_file': [], 'cross_file': []}
        for _item in attributes['in_class']:
            generated_dependency['intra_class'].append(_item['name'])
        for _item in attributes['in_file']:
            generated_dependency['intra_file'].append(_item['name'])
        for _item in attributes['in_object']:
            generated_dependency['cross_file'].append(_item['name'])
        return generated_dependency

    def run_test(self, data: dict):
        project_name = data['completion_path'].split('/')[0]
        self.copy_project(project_name)
        self.SetUp_evaluation(data)
        if self.parse_dependency(data) == True:
            generated_dependency = self.extract_dependency(data)
            self.TearDown_evaluation(data)
            return generated_dependency
        else:
            self.TearDown_evaluation(data)
            return None


class EvoCodeTestServer(SingletonMixin):
    def __init__(self, pass_k_test_configs: dict, recall_k_test_configs: dict) -> None:
        SingletonMixin.__init__(self)
        self.pass_k_test_handler = PassKTest(**pass_k_test_configs)
        self.recall_k_test_handler = RecallKTest(**recall_k_test_configs)
        self.lock = threading.Lock()

    def pass_k_test(self, data_dict: dict):
        with self.lock:  # NOTE::阻止并发，多实例无法同时执行
            ret = None
            error = None
            try:
                ret = self.pass_k_test_handler.run_test(data_dict)
            except Exception:
                error = traceback.format_exc()
            return {"return": ret, "error": error}

    def recall_k_test(self, data_dict: dict):
        with self.lock:  # NOTE::阻止并发，多实例无法同时执行
            ret = None
            error = None
            try:
                ret = self.recall_k_test_handler.run_test(data_dict)
            except Exception:
                error = traceback.format_exc()
            return {"return": ret, "error": error}


class EvoCodeTestClient:
    def __init__(self, server_mapping: Dict[str, str], pass_k_test_route: str, recall_k_test_route: str):
        """
        初始化客户端。

        :param server_mapping: 一个字典，键是 key，值是服务器的地址（URL）。
        """
        self.server_mapping = server_mapping
        self.session = requests.Session()  # 同步会话
        self.async_session = None  # 异步会话，将在异步方法中初始化
        self.pass_k_test_route = pass_k_test_route
        self.recall_k_test_route = recall_k_test_route

    def _get_server_url(self, key: str, route: str) -> str:
        """
        根据 key 获取服务器的完整 URL。

        :param key: data_dict 中的 key。
        :param route: 请求的路由，如 '/pass_k_test'。
        :return: 完整的服务器 URL。
        """
        base_url = self.server_mapping.get(key)
        if not base_url:
            raise ValueError(f"No server mapping found for key: {key}")
        return f"{base_url}{route}"

    def pass_k_test(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步方式调用 pass_k_test。

        :param data_dict: 请求数据，必须包含 'key'。
        :return: 服务器的响应。
        """
        key = data_dict.get('key')
        if not key:
            raise ValueError("data_dict must contain 'key'")
        url = self._get_server_url(key, self.pass_k_test_route)
        response = self.session.post(url, json=data_dict)
        return response.json()

    def recall_k_test(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步方式调用 recall_k_test。

        :param data_dict: 请求数据，必须包含 'key'。
        :return: 服务器的响应。
        """
        key = data_dict.get('key')
        if not key:
            raise ValueError("data_dict must contain 'key'")
        url = self._get_server_url(key, self.recall_k_test_route)
        response = self.session.post(url, json=data_dict)
        return response.json()

    async def async_pass_k_test(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步方式调用 pass_k_test。

        :param data_dict: 请求数据，必须包含 'key'。
        :return: 服务器的响应。
        """
        if self.async_session is None:
            self.async_session = aiohttp.ClientSession()
        key = data_dict.get('key')
        if not key:
            raise ValueError("data_dict must contain 'key'")
        url = self._get_server_url(key, self.pass_k_test_route)
        async with self.async_session.post(url, json=data_dict) as response:
            return await response.json()

    async def async_recall_k_test(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步方式调用 recall_k_test。

        :param data_dict: 请求数据，必须包含 'key'。
        :return: 服务器的响应。
        """
        if self.async_session is None:
            self.async_session = aiohttp.ClientSession()
        key = data_dict.get('key')
        if not key:
            raise ValueError("data_dict must contain 'key'")
        url = self._get_server_url(key, self.recall_k_test_route)
        async with self.async_session.post(url, json=data_dict) as response:
            return await response.json()

    async def close_async_session(self):
        """关闭异步会话。"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None


def server_app():
    if not os.path.exists("/opt/evo_server.yaml"):
        return
    with open("/opt/evo_server.yaml", "r") as f:
        configs = SimpleNamespace(**yaml.safe_load(f))

    app = Flask(__name__)
    server = EvoCodeTestServer(configs.pass_k_test_configs, configs.recall_k_test_configs)

    @app.route(configs.pass_k_test_route, methods=['POST'])
    def pass_k_test_route():
        data = request.json  # 获取 POST 请求中的 JSON 数据
        response = server.pass_k_test(data)
        return jsonify(response)

    @app.route(configs.recall_k_test_route, methods=['POST'])
    def recall_k_test_route():
        data = request.json  # 获取 POST 请求中的 JSON 数据
        response = server.recall_k_test(data)
        return jsonify(response)

    app.run(host=configs.host, port=configs.port)


def client_app(pass_k_test_route: str, recall_k_test_route: str):
    # 假设有两个服务器地址
    server_mapping = {
        'key1': 'http://localhost:5000',
        'key2': 'http://localhost:5001',
    }

    client = EvoCodeTestClient(server_mapping, pass_k_test_route, recall_k_test_route)

    # 构造请求数据
    data1 = ...
    data2 = ...

    # 同步调用 pass_k_test
    response1 = client.pass_k_test(data1)
    print("Response from server 1:", response1)

    # 同步调用 recall_k_test
    response2 = client.recall_k_test(data2)
    print("Response from server 2:", response2)


def async_client_app(pass_k_test_route: str, recall_k_test_route: str):
    import asyncio

    async def main():
        # 假设有两个服务器地址
        server_mapping = {
            'key1': 'http://localhost:5000',
            'key2': 'http://localhost:5001',
        }

        client = EvoCodeTestClient(server_mapping, pass_k_test_route, recall_k_test_route)

        # 构造请求数据
        data1 = ...
        data2 = ...

        # 异步调用 pass_k_test
        response1 = await client.async_pass_k_test(data1)
        print("Async response from server 1:", response1)

        # 异步调用 recall_k_test
        response2 = await client.async_recall_k_test(data2)
        print("Async response from server 2:", response2)

        # 关闭异步会话
        await client.close_async_session()

    # 运行异步主函数
    asyncio.run(main())


if __name__ == "__main__":
    server_app()
    # client_app()
    # async_client_app()
