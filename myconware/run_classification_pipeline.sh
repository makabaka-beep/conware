#!/bin/bash
# run_classification_pipeline.sh
# Conware 寄存器分类与模型验证完整流程脚本

set -e  # 遇到错误退出

# 默认实验目录
if [ -z "$1" ]; then
    EXP_DIR="/home/makabaka/conware/myconware/firmware/stm32f407/4外部中断实验"
else
    # 转换为绝对路径
    if [[ "$1" != /* ]]; then
        EXP_DIR="$(pwd)/$1"
    else
        EXP_DIR="$1"
    fi
fi

echo "=========================================="
echo "Conware 寄存器分类与模型验证流程"
echo "=========================================="
echo "实验目录: $EXP_DIR"

# 检查文件是否存在
if [ ! -f "${EXP_DIR}/recording.tsv" ]; then
    echo "错误: recording.tsv 不存在"
    exit 1
fi

cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

# ============================================
# 步骤1: 寄存器分类与数据精简
# ============================================
echo ""
echo "=========================================="
echo "步骤1: 寄存器分类与数据精简"
echo "=========================================="
python conware/register_classifier.py \
    ${EXP_DIR}/recording.tsv \
    -r

# ============================================
# 步骤2: 训练模型
# ============================================
echo ""
echo "=========================================="
echo "步骤2: 训练模型"
echo "==========================================="
cd /home/makabaka/conware/conware
source ../myconware/venv/bin/activate
export PYTHONPATH=$PWD:../myconware

python -c "
from conware.model import ConwareModel
import os

exp_dir = '${EXP_DIR}'
recording_path = os.path.join(exp_dir, 'recording.tsv')
simplified_path = os.path.join(exp_dir, 'recording_simplified.tsv')
model1_path = os.path.join(exp_dir, 'conware_model_original.pkl')
model2_path = os.path.join(exp_dir, 'conware_model_simplified.pkl')

print(f'训练数据路径: {recording_path}')
print(f'文件存在: {os.path.exists(recording_path)}')

# 训练原始模型
print('>>> 训练原始模型 (recording.tsv)...')
model1 = ConwareModel()
model1.train(recording_path)
model1.save(model1_path)
print(f'>>> 完成: {len(model1.peripherals)} 个外设, {len(model1.model_per_address)} 个地址映射')

# 训练精简模型
print('>>> 训练精简模型 (recording_simplified.tsv)...')
model2 = ConwareModel()
model2.train(simplified_path)
model2.save(model2_path)
print(f'>>> 完成: {len(model2.peripherals)} 个外设, {len(model2.model_per_address)} 个地址映射')

print('>>> 模型训练完成!')
"

# ============================================
# 步骤3: 模型验证
# ============================================
echo ""
echo "=========================================="
echo "步骤3: 模型验证"
echo "=========================================="
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

python conware/verify_model.py \
    --model1 ${EXP_DIR}/conware_model_original.pkl \
    --model2 ${EXP_DIR}/conware_model_simplified.pkl \
    --input ${EXP_DIR}/recording.tsv \
    --output ${EXP_DIR}/model_verification_report.txt

# ============================================
# 完成
# ============================================
echo ""
echo "=========================================="
echo "流程完成!"
echo "=========================================="
echo ""
echo "输出文件:"
echo "  - ${EXP_DIR}/recording_simplified.tsv"
echo "  - ${EXP_DIR}/recording_simplification_report.txt"
echo "  - ${EXP_DIR}/conware_model_original.pkl"
echo "  - ${EXP_DIR}/conware_model_simplified.pkl"
echo "  - ${EXP_DIR}/model_verification_report.txt"
echo ""
echo "详细文档:"
echo "  - /home/makabaka/conware/myconware/PIPELINE_GUIDE.md"
echo ""
