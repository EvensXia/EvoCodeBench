# 定义基础模型和变体
base_models=("deepseek-33b" "gpt-4-1106" "gpt-35-1106")
suffixes=("_greedy" "_greedy_recall" "" "_recall")

# 定义路径数组
folders=("baseline" "local_completion" "local_infilling")
modas=("greedy" "sampling")

# for folder in "${folders[@]}"; do
#     python make_prompt.py \
#         --setting $folder \
#         --output_file additional_data/prompt/$folder.jsonl \
#         --context_window 16384 \
#         --max_tokens 500
# done

for folder in "${folders[@]}"; do
    for moda in "${modas[@]}"; do
        folder_path="additional_data/completion/${folder}_${moda}"/
        mkdir -p $folder_path
        python gpt_inference2.py \
            --prompt_file additional_data/prompt/$folder.jsonl \
            --output_dir $folder_path \
            --model gpt-3.5 \
            --moda $moda \
            --api_key_file api_key.txt
    done
done
