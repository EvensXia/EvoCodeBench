import json
import os
from tqdm import tqdm

from EvoCodeBench import EvoCodeTestClient

pass_k_test_route = '/pass_k_test'
recall_k_test_route = '/recall_k_test'
mmap = {}
for key in os.listdir("/root/EvoCodeBench/Source_Code2"):
    mmap[key] = f"http://localhost:5000"
client = EvoCodeTestClient(mmap, pass_k_test_route, recall_k_test_route)


def main():
    # load output data to be evaluated (skip finished data)
    todo_output_data = []
    with open("model_completion/baseline/gpt-4-1106_greedy/completion.jsonl", 'r') as f:
        for line in f:
            js = json.loads(line)
            todo_output_data.append(js)
    print("TODO Completions: ", len(todo_output_data))

    # load benchmark data
    benchmark_data = {}
    with open("data.jsonl", 'r') as f:
        for line in f:
            js = json.loads(line)
            namespace = js['namespace']
            benchmark_data[namespace] = js

    # iterate through the output data
    for output in tqdm(todo_output_data):
        namespace = output['namespace']
        if namespace in benchmark_data:
            data = benchmark_data[namespace]
            data['completion'] = output['completion']
            result = client.pass_k_test(data)
            # result = test_passk(data)
            output['Result'] = result
        print(result)
        return


def test_passk(data):
    from EvoCodeBench import PassKTest
    test = PassKTest("/root/EvoCodeBench/Source_Code", "/data/EvoCodeBench/Source_Code", "/root/EvoCodeBench/Source_Code")
    return test.run_test(data)


if __name__ == '__main__':
    main()
