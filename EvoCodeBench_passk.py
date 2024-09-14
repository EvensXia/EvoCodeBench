import json
import os
import subprocess
import textwrap
from argparse import ArgumentParser
from subprocess import run

import func_timeout
import numpy as np
import psutil
from func_timeout import func_set_timeout
from python_repo import PythonRepo
from tqdm import tqdm
from EvoCodeBench import EvoCodeTestClient
from loguru import logger
import yaml
####################################################################
# 从docker-compose文件中获取服务的repo配置
with open("path/to/docker-compose.yaml", "r") as f:
    compose_config = yaml.safe_load(f)
server_mapping = {}
for service_name, service_config in compose_config["services"].items():
    repo_name = service_config["environment"]["repo_name"]
    port_number = service_config["ports"][0].split(":")[0]
    server_mapping[repo_name] = f"http://localhost:{port_number}"
    logger.success(f"load service {service_name}, repo_name:")
pass_k_test_route = '/pass_k_test'
recall_k_test_route = '/recall_k_test'
client = EvoCodeTestClient(server_mapping, pass_k_test_route, recall_k_test_route)
####################################################################


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--output_file', type=str)
    parser.add_argument('--log_file', type=str)
    parser.add_argument('--data_file', type=str, default='data.jsonl')
    parser.add_argument('--source_code_root', type=str, default='Source_Code')
    parser.add_argument('--k', type=str, default='1,3,5,10')
    parser.add_argument('--n', type=int, default=1)
    return parser.parse_args()


def parse_config():
    import types
    import yaml
    parser = ArgumentParser()
    parser.add_argument("-c", "--config", type=str)
    args = parser.parse_args()
    config: str = args.config
    config_file, config_key = config.split("::")
    with open(config_file, "r") as f:
        config_all = yaml.safe_load(f)
    args_config = types.SimpleNamespace(**config_all[config_key])
    return args_config


def adjust_indent(code, new_indent):
    # remove original indentation
    dedented_code = textwrap.dedent(code)
    # add new indentation
    indented_code = textwrap.indent(dedented_code, ' ' * new_indent)
    return indented_code


@func_set_timeout(20)
def execution_tests(test, project_path):
    command = "pytest " + test
    print(project_path)
    process = subprocess.Popen(['bash', '-c', command], cwd=project_path,
                               # stdout=subprocess.PIPE, stderr=subprocess.PIPE
                               )
    try:
        while True:
            process_id = process.pid
            process_memory = psutil.Process(process_id).memory_info().rss
            if process_memory > 5 * 1024 * 1024 * 1024:  # 5GB memory usage per test
                process.terminate()
                process.wait()
                return False  # Out of Memory
            return_code = process.poll()
            if return_code is not None:
                if return_code != 0:
                    process.terminate()
                    process.wait()
                    return False  # Execution Error
                else:
                    break
    except Exception as e:
        process.terminate()
        process.wait()
        return False  # Other Error
    finally:
        process.terminate()
        process.wait()
    return True  # Pass


def compute_pass_at_k(n, c, k):
    """
    n: total number of completions per task
    c: number of completions that pass all tests
    k: k in pass_at_k
    """
    if n - c < k:
        return 1
    else:
        return 1.0 - np.prod(1.0 - k / np.arange(n-c+1, n+1))


def SetUp_evaluation(args, data, completion):
    completion_path = os.path.join(args.source_code_root, data['completion_path'])
    head_tail = os.path.split(completion_path)
    completion_tmp_path = os.path.join(head_tail[0], 'tmp_' + head_tail[1])

    # rename the original completion file as tmp_completion
    run(['cp', completion_path, completion_tmp_path])

    # write the new completion file
    sos, eos = data['body_position'][0]-1, data['body_position'][1]
    with open(completion_path, 'r') as f:
        file_lines = f.readlines()
    file_lines = file_lines[:sos] + ['\n', completion, '\n'] + file_lines[eos:]
    with open(completion_path, 'w') as f:
        f.write(''.join(file_lines))


def TearDown_evaluation(args, data):
    completion_path = os.path.join(args.source_code_root, data['completion_path'])
    head_tail = os.path.split(completion_path)
    completion_tmp_path = os.path.join(head_tail[0], 'tmp_' + head_tail[1])
    run(['mv', completion_tmp_path, completion_path])


def check_correctness(args, data):
    completion = data['completion']
    if completion == "    pass\n":
        return 'Fail'
    completion = adjust_indent(completion, data['indent'])

    SetUp_evaluation(args, data, completion)
    project_name = data['completion_path'].split('/')[0]
    project_path = os.path.join(args.source_code_root, project_name)
    flag = 'Pass'
    python_repo = PythonRepo(project_path)
    python_repo.prepare_env()

    for test in data['tests']:
        try:
            # result = execution_tests(test, project_path)
            result = python_repo.run_test(test)
            if not result:
                flag = 'Fail'
                break
        except func_timeout.exceptions.FunctionTimedOut:
            flag = 'Fail'
            break
    TearDown_evaluation(args, data)
    return flag


def report_results(args, benchmark_data):
    if not os.path.exists(args.log_file):
        raise ValueError(f'{args.log_file} does not exist')

    # Collect passed completions for each namespace
    passed_completion = {}
    with open(args.log_file, 'r') as f:
        for line in f:
            js = json.loads(line)
            if js['Result'] == 'Pass':
                namespace, completion = js['namespace'], js['completion']
                if namespace not in passed_completion:
                    passed_completion[namespace] = set()
                passed_completion[namespace].add(completion)

    # Iterate through all completions and count the number of passed completions for each namespace
    results = {}
    with open(args.output_file, 'r') as f:
        for line in f:
            js = json.loads(line)
            namespace, completion = js['namespace'], js['completion']
            if namespace in benchmark_data:
                if namespace not in results:
                    results[namespace] = 0
                if namespace in passed_completion and completion in passed_completion[namespace]:
                    results[namespace] += 1

    # Compute Pass@k
    k_list = [int(k) for k in args.k.split(',')]
    writes = []
    for k in k_list:
        if k > args.n:
            continue
        pass_at_k = np.mean([compute_pass_at_k(args.n, pass_num, k) for namespace, pass_num in results.items()])
        print(f'pass_at_{k}: {pass_at_k*100}%')
        writes.append(f'pass_at_{k}: {pass_at_k*100}%\n')
    with open(args.write_rst, "w") as f:
        f.writelines(writes)


def load_finished_data(args):
    finished_data = {}
    if os.path.exists(args.log_file):
        with open(args.log_file, 'r') as f:
            for line in f:
                js = json.loads(line)
                namespace, completion = js['namespace'], js['completion']
                if namespace not in finished_data:
                    finished_data[namespace] = set()
                finished_data[namespace].add(completion)
    return finished_data


def main():
    # args = parse_args()
    args = parse_config()

    # load output data to be evaluated (skip finished data)
    finished_data = load_finished_data(args)
    todo_output_data = []
    with open(args.output_file, 'r') as f:
        for line in f:
            js = json.loads(line)
            namespace, completion = js['namespace'], js['completion']
            if namespace not in finished_data:
                todo_output_data.append(js)
                finished_data[namespace] = set()
                finished_data[namespace].add(completion)
            elif completion not in finished_data[namespace]:
                todo_output_data.append(js)
                finished_data[namespace].add(completion)
    del finished_data
    print("TODO Completions: ", len(todo_output_data))

    # load benchmark data
    benchmark_data = {}
    with open(args.data_file, 'r') as f:
        for line in f:
            js = json.loads(line)
            namespace = js['namespace']
            benchmark_data[namespace] = js

    # iterate through the output data
    with open(args.log_file, 'a') as f:
        for output in tqdm(todo_output_data):
            namespace = output['namespace']
            if namespace in benchmark_data:
                data = benchmark_data[namespace]
                data['completion'] = output['completion']
                result = client.pass_k_test(data)
                output['Result'] = result
                f.write(json.dumps(output) + '\n')
                f.flush()

    report_results(args, benchmark_data)


if __name__ == '__main__':
    main()
