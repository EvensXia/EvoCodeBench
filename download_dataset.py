# from datasets import load_dataset
# from huggingface_hub import hf_hub_download, login
# import os
# import zipfile

# # 如果需要，先进行身份验证
# # login("your_huggingface_api_token")  # 如果数据集是私有的，取消注释并提供您的 token

# # 定义仓库 ID 和文件名
# repo_id = "LJ0815/EvoCodeBench"
# repo_type = "dataset"  # 指定仓库类型为 dataset
# filenames = [
#     "EvoCodeBench-2403/Dependency_Data.tar.gz",
#     "EvoCodeBench-2403/Source_Code.tar.gz",
#     "EvoCodeBench-2403/data.tar.gz"
# ]

# # 创建下载目录
# download_dir = "downloads"
# os.makedirs(download_dir, exist_ok=True)

# # 下载文件
# for filename in filenames:
#     try:
#         file_path = hf_hub_download(
#             repo_id=repo_id,
#             filename=filename,
#             repo_type=repo_type,
#             local_dir=download_dir,
#             local_dir_use_symlinks=False
#         )
#         print(f"已下载: {file_path}")
#     except Exception as e:
#         print(f"下载 {filename} 时出错: {e}")

import os
import zipfile
import tarfile

download_dir = "downloads/EvoCodeBench-2403"
# 解压缩文件（如果需要）
for file in os.listdir(download_dir):
    if file.endswith(".zip") or file.endswith(".tar.gz"):
        file_path = os.path.join(download_dir, file)
        extract_dir = os.path.join(download_dir, f"unzipped")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            if file.endswith(".zip"):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif file.endswith(".tar.gz"):
                with tarfile.open(file_path, "r:gz") as tar_ref:
                    tar_ref.extractall(extract_dir)
            print(f"已解压: {file_path} 到 {extract_dir}")
        except Exception as e:
            print(f"解压 {file_path} 时出错: {e}")
