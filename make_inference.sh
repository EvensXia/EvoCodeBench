# 定义路径数组
folders=("baseline" "local_completion" "local_infilling")
modas=("greedy" "sampling")

# make_prompt
# for folder in "${folders[@]}"; do
#     python make_prompt.py \
#         --setting $folder \
#         --output_file additional_data/prompt/$folder.jsonl \
#         --context_window 16384 \
#         --max_tokens 500
# done
# inference
# for folder in "${folders[@]}"; do
#     for moda in "${modas[@]}"; do
#         folder_path="additional_data/completion/${folder}_${moda}"
#         mkdir -p $folder_path
#         python gpt_inference2.py \
#             --prompt_file additional_data/prompt/$folder.jsonl \
#             --output_dir $folder_path \
#             --model gpt-3.5 \
#             --moda $moda \
#             --api_key_file api_key.txt
#     done
# done


# flatten
# python flatten.py --root additional_data/completion


# test
for folder in "${folders[@]}"; do
    for moda in "${modas[@]}"; do
        tag="${folder}_${moda}"
        bash reset.sh
        python pass_k.py --config additional_data/passk.yaml::$tag
        bash reset.sh
        python recall_k.py --config additional_data/recallk.yaml::$tag
    done
done