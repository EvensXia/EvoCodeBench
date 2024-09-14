import json
import os

import yaml
from pathlib import Path
ROOT = Path(__file__).parent
launch_json = {
    "version": "0.2.0",
    "configurations": []
}

for task in ["local_completion", "local_infilling", "baseline"]:
    TASK = task
    config = {}
    recall_config = {}
    os.makedirs(f"scripts/{TASK}", exist_ok=True)
    for dirm in os.listdir(f"model_completion/{TASK}"):
        config[dirm] = {
            "output_file": f"model_completion/{TASK}/{dirm}/completion.jsonl",
            "log_file": f"logout/{TASK}_{dirm}.jsonl",
            "data_file": "data.jsonl",
            "source_code_root": "Source_Code",
            "k": "1",
            "n": 1,
            "write_rst": f"logout/{TASK}_{dirm}.txt"
        }
        recall_config[dirm] = {
            "output_file": f"model_completion/{TASK}/{dirm}/completion.jsonl",
            "log_file": f"logout/{TASK}_{dirm}_recall.jsonl",
            "k": "1",
            "source_code_root": f'{str(ROOT/"Source_Code")}',
            "dependency_data_root": f'{str(ROOT/"Dependency_Data")}',
            "data_file": f'{str(ROOT/"data.jsonl")}',
            "dependency_tmp_dir": "dependency_data_tmp",
            "write_rst": f"logout/{TASK}_{dirm}_recall.txt"
        }
        launch_json["configurations"].append({
            "name": f"{TASK}::{dirm}",
            "type": "debugpy",
            "request": "launch",
            "program": "pass_k.py",
            "cwd": "/root/EvoCodeBench",
            "console": "integratedTerminal",
            "consoleName": f"{TASK}::{dirm}",
            "args": ["--config", f"config.{TASK}.yaml::{dirm}"],
            "preLaunchTask": "RESET"
        })
        with open(f"scripts/{TASK}/{dirm}.sh", "w") as f:
            f.writelines([
                "#!/bin/bash\n",
                "cd /root/EvoCodeBench || exit\n",
                "bash reset.sh\n",
                f"python pass_k.py --config config.{TASK}.yaml::{dirm}\n",
            ])
        with open(f"scripts/{TASK}/{dirm}_recall.sh", "w") as f:
            f.writelines([
                "#!/bin/bash\n",
                "cd /root/EvoCodeBench || exit\n",
                "bash reset.sh\n",
                f"python recall_k.py --config recall_config.{TASK}.yaml::{dirm}\n",
            ])
    with open(f"config.{TASK}.yaml", "w") as f:
        yaml.safe_dump(config, f, indent=4)
    with open(f"recall_config.{TASK}.yaml", "w") as f:
        yaml.safe_dump(recall_config, f, indent=4)
with open(".vscode/launch.json", "w") as f:
    json.dump(launch_json, f, indent=4)
