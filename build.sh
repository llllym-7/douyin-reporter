#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# 运行数据库迁移 (如果未来有的话)
# flask db upgrade