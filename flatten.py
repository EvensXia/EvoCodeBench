import os
import json


def flatten_jsonl_files(root_dir):
    # 遍历所有子目录和文件
    for subdir, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.jsonl'):
                input_file_path = os.path.join(subdir, file)
                temp_file_path = input_file_path + '.tmp'

                print(f'正在处理 {input_file_path} 并覆盖原文件')

                with open(input_file_path, 'r', encoding='utf-8') as infile, \
                        open(temp_file_path, 'w', encoding='utf-8') as outfile:
                    for line in infile:
                        data = json.loads(line)
                        completion_list = data.get('completion', [])
                        if isinstance(completion_list, list):
                            # 复制数据并移除 completion 字段
                            data_without_completion = data.copy()
                            data_without_completion.pop('completion', None)
                            for completion in completion_list:
                                new_data = data_without_completion.copy()
                                new_data['completion'] = completion
                                json.dump(new_data, outfile, ensure_ascii=False)
                                outfile.write('\n')
                        else:
                            # 如果 completion 不是列表，直接写入
                            json.dump(data, outfile, ensure_ascii=False)
                            outfile.write('\n')
                # 用临时文件替换原始文件
                os.replace(temp_file_path, input_file_path)


if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--root", type=str)
    args = parser.parse_args()
    # root_directory = 'additional_data/completion'
    flatten_jsonl_files(args.root)
    print('所有文件已处理完毕，原文件已被覆盖。')
