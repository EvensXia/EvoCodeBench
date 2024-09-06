#!/bin/bash

# 指定要删除 .DS_Store 文件的目录
TARGET_DIR=$1

# 查找并删除所有的 .DS_Store 文件
find "$TARGET_DIR" -name '.DS_Store' -type f -delete

# 输出删除操作完成
echo "All .DS_Store files have been removed from $TARGET_DIR"
