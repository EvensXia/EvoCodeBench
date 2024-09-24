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
from typing import Callable

import func_timeout
import yaml
from EvoCodeBenchWS import WebSocketClient, WebSocketServer
from loguru import logger
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
            logger.success(f"EXISTING: {dst_env_dir}")
            return
        logger.info(f"COPY: {src_env_dir} => {dst_env_dir}")
        shutil.copytree(src_env_dir, dst_env_dir)
        logger.success(f"COPY: {src_env_dir} => {dst_env_dir} FINISHED")


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
        self.SetUp_evaluation(data, data['completion'])
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
    def __init__(self, passk_servers: dict = None, passk_func: Callable[[dict], str] = None,
                 recallk_servers: dict = None, recallk_func: Callable[[dict], dict[str, list] | None] = None) -> None:
        self._passk_enabled: bool = False
        self._recallk_enabled: bool = False

        def passk(data: dict):
            logger.warning(f"default passk func {passk_func} is in use")
            error = ""
            try:
                ret = passk_func(data)
            except Exception:
                ret = "Fail"
                error = traceback.format_exc()
            return {"return": ret, "error": error}

        def recallk(data: dict):
            logger.warning(f"default recallk func {recallk_func} is in use")
            error = ""
            try:
                ret = recallk_func(data)
            except Exception:
                ret = None
                error = traceback.format_exc()
            return {"return": ret, "error": error}

        if passk_servers is not None:
            self.passk_client = WebSocketClient()
            for key, server in passk_servers.items():
                self.passk_client.add_server(key, **server)
            self.passk_client.enable = True
            self._passk_enabled: bool = True
            self._passk_call: Callable[[dict], dict] = self.passk_client.regist_faas(passk)
        else:
            if passk_func is not None:
                self._passk_enabled: bool = True
                self._passk_call: Callable[[dict], dict] = passk

        if recallk_servers is not None:
            self.recallk_client = WebSocketClient()
            for key, server in recallk_servers.items():
                self.recallk_client.add_server(key, **server)
            self.recallk_client.enable = True
            self._recallk_enabled: bool = True
            self._recallk_call: Callable[[dict], dict] = self.recallk_client.regist_faas(recallk)
        else:
            if recallk_func is not None:
                self._recallk_enabled: bool = True
                self._recallk_call: Callable[[dict], dict] = recallk

    def pass_k_test(self, data: dict) -> str:
        if not self._passk_enabled:
            logger.error(f"no passk server or local function found")
        result = self._passk_call(data)["return"]
        return result

    def recall_k_test(self, data: dict) -> dict[str, list] | None:
        if not self._recallk_enabled:
            logger.error(f"no recallk server or local function found")
        result = self._recallk_call(data)["return"]
        return result


def server_app():
    import asyncio
    if not os.path.exists("/opt/evo_server.yaml"):
        return
    with open("/opt/evo_server.yaml", "r") as f:
        args = SimpleNamespace(**yaml.safe_load(f))
    logger.info(f"loaded args: {args}")
    ws_server = WebSocketServer()
    ec_server = EvoCodeTestServer(pass_k_test_configs=args.pass_k_test_configs,
                                  recall_k_test_configs=args.recall_k_test_configs)

    def passk_handle(**kwargs):
        print(kwargs.keys())
        return ec_server.pass_k_test(data_dict=kwargs)

    def recallk_handle(**kwargs):
        print(kwargs.keys())
        return ec_server.recall_k_test(data_dict=kwargs)

    ws_server.add_serve(passk_handle, **args.passk)
    ws_server.add_serve(recallk_handle, **args.recallk)

    asyncio.run(ws_server.run())


def client_app():
    client = EvoCodeTestClient(passk_servers=...,
                               passk_func=lambda x: x,
                               recallk_servers=...,
                               recallk_func=lambda x: x)
    call_dict = ...
    # passk
    result = client.pass_k_test(call_dict)
    # recallk
    result = client.recall_k_test(call_dict)


if __name__ == "__main__":
    server_app()
