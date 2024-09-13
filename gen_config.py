import yaml
import os
import json
launch_json = {
    "version": "0.2.0",
    "configurations": []
}
for task in ["local_completion", "local_infilling", "baseline"]:
    TASK = task
    config = {}
    for dirm in os.listdir(f"model_completion/{TASK}"):
        config[dirm] = {
            "output_file": f"model_completion/{TASK}/{dirm}/completion.jsonl",
            "log_file": f"logout/{dirm}.jsonl",
            "data_file": "data.jsonl",
            "source_code_root": "Source_Code",
            "k": 1,
            "n": 1
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
    with open(f"config.{TASK}.yaml", "w") as f:
        yaml.safe_dump(config, f, indent=4)
with open(".vscode/launch.json", "w") as f:
    json.dump(launch_json, f, indent=4)
