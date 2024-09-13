#!/bin/bash

# 设置当前工作目录为脚本所在的目录
cd "$(dirname "$0")" || exit

# 定义源目录和备份目录
rm log/* -fr
rm logout/*.jsonl -f
SOURCE_DIR="Source_Code"
BACKUP_DIR="Source_Code_backup"

# 遍历 Source_Code_backup 目录中的所有文件和目录
find "$BACKUP_DIR" -type f | while read -r backup_file; do
    # 去掉备份目录的前缀路径，得到相对路径
    relative_path="${backup_file#$BACKUP_DIR/}"

    # 源文件的完整路径
    source_file="$SOURCE_DIR/$relative_path"

    # 检查源文件是否存在
    if [ -e "$source_file" ]; then
        # 计算源文件和备份文件的 MD5 值
        md5_source=$(md5sum "$source_file" | awk '{print $1}')
        md5_backup=$(md5sum "$backup_file" | awk '{print $1}')

        # 如果 MD5 不一致，进行复制
        if [ "$md5_source" != "$md5_backup" ]; then
            echo "MD5 mismatch. Copying $backup_file to $source_file"
            cp "$backup_file" "$source_file"
        fi
    else
        # 如果源文件不存在，告警提示并复制文件
        echo "WARNING: $source_file does not exist. Add new."
        source_dir=$(dirname "$source_file")
        if [ ! -d "$source_dir" ]; then
            echo "Directory $source_dir does not exist. Creating directory."
            mkdir -p "$source_dir"
        fi
        cp "$backup_file" "$source_file"
    fi
done
