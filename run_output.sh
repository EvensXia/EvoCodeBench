# 定义基础模型和变体
base_models=("deepseek-33b" "gpt-4-1106" "gpt-35-1106")
suffixes=("_greedy" "_greedy_recall" "" "_recall")

# 定义路径数组
folders=("baseline" "local_completion" "local_infilling")

# 循环执行每个模型和路径的脚本
for suffix in "${suffixes[@]}"; do
    for folder in "${folders[@]}"; do
        for model in "${base_models[@]}"; do
            bash "/root/EvoCodeBench/scripts/$folder/${model}${suffix}.sh"
        done
    done
done
