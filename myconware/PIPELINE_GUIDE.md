# Conware 寄存器分类与模型验证完整流程

## 概述

本流程演示如何对寄存器访问记录进行分类、精简，生成优化的外设模型，并通过验证确保模型功能完整性。

## 前置条件

```bash
# 激活虚拟环境
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD
```

## 工作目录

```bash
EXP_DIR="/home/makabaka/conware/myconware/firmware/stm32f407/1跑马灯实验"
cd $EXP_DIR
```

## 完整流程图

```
recording.tsv (原始数据)
       │
       ▼
┌─────────────────────────────────────────┐
│  步骤1: 寄存器分类与数据精简             │
│  命令: register_classifier.py           │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  生成文件:                               │
│  - recording_simplified.tsv (精简数据)   │
│  - recording_simplification_report.txt  │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  步骤2: 训练模型                         │
│  命令: conware.model.ConwareModel.train()│
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  生成文件:                               │
│  - conware_model_original.pkl           │
│  - conware_model_simplified.pkl         │
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  步骤3: 模型验证                         │
│  命令: verify_model.py                  │
└─────────────────���───────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  生成文件:                               │
│  - model_verification_report.txt         │
└─────────────────────────────────────────┘
```

---

## 步骤详解

### 步骤1: 寄存器分类与数据精简

#### 1.1 命令

```bash
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

python conware/register_classifier.py \
    /home/makabaka/conware/myconware/firmware/stm32f407/1跑马灯实验/recording.tsv \
    -r
```

#### 1.2 说明

`register_classifier.py` 会：
1. 解析 `recording.tsv` 文件
2. 分析每个寄存器的访问模式
3. 将寄存器分类为6种类型：STORAGE/CONFIG/PATTERN/STATUS/INCREASING/MARKOV
4. 根据类型精简数据，移除冗余记录

#### 1.3 输出文件

| 文件 | 说明 |
|------|------|
| `recording_simplified.tsv` | 精简后的训练数据 |
| `recording_simplification_report.txt` | 精简统计报告 |

#### 1.4 报告示例

```
============================================================
数据精简报告
============================================================

原始记录数: 352
精简后记录数: 52
压缩比: 14.77%

按类别精简统计:
  MARKOV: 35 条
  CONFIG: 9 条
  STORAGE: 1 条
  INCREASING: 7 条
```

---

### 步骤2: 训练模型

#### 2.1 命令

```bash
cd /home/makabaka/conware/conware
source ../myconware/venv/bin/activate
export PYTHONPATH=$PWD

python -c "
from conware.model import ConwareModel
import os

dir_path = '/home/makabaka/conware/myconware/firmware/stm32f407/2蜂鸣器实验'

# 训练原始模型
print('>>> 训练原始模型...')
model_original = ConwareModel()
model_original.train(os.path.join(dir_path, 'recording.tsv'))
model_original.save(os.path.join(dir_path, 'conware_model_original.pkl'))
print(f'>>> 原始模型已保存: {len(model_original.peripherals)} 个外设')

# 训练精简模型
print('>>> 训练精简模型...')
model_simplified = ConwareModel()
model_simplified.train(os.path.join(dir_path, 'recording_simplified.tsv'))
model_simplified.save(os.path.join(dir_path, 'conware_model_simplified.pkl'))
print(f'>>> 精简模型已保存: {len(model_simplified.peripherals)} 个外设')

print('>>> 完成!')
"
```

#### 2.2 说明

使用 `ConwareModel.train()` 方法：
1. 读取 training data（recording.tsv 或 recording_simplified.tsv）
2. 构建外设模型
3. 生成状态机
4. 保存为 pickle 文件

#### 2.3 输出文件

| 文件 | 说明 |
|------|------|
| `conware_model_original.pkl` | 原始模型 |
| `conware_model_simplified.pkl` | 精简模型 |

---

### 步骤3: 分类分析（可选）

#### 3.1 命令

```bash
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

python conware/analyze_classification.py \
    /home/makabaka/conware/myconware/firmware/stm32f407/1跑马灯实验/
```

#### 3.2 说明

生成详细的分类分析报告，包括：
- 原始数据统计
- 寄存器分类结果
- 各类别精简效果
- 优化建议

#### 3.3 输出示例

```
======================================================================
寄存器分类优化分析报告
======================================================================

实验目录: /home/makabaka/conware/myconware/firmware/stm32f407/1跑马灯实验/

【一、原始数据分析】
  总记录数: 352
  读操作: 258
  写操作: 94
  唯一地址数: 6

【二、寄存器分类分析】
  分类结果:
    STORAGE: 1 个寄存器
    PATTERN: 4 个寄存器
    INCREASING: 1 个寄存器

【三、精简效果分析】
  原始记录数: 352
  精简后记录数: 52
  压缩比: 85.2%

  按类别精简统计:
    PATTERN: 249 -> 44 (压缩 82.3%)
    STORAGE: 43 -> 1 (压缩 97.7%)
    INCREASING: 60 -> 7 (压缩 88.3%)
```

---

### 步骤4: 模型验证

#### 4.1 命令
2蜂鸣器实验
```bash
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

python conware/verify_model.py \
    --model1 firmware/stm32f407/2蜂鸣器实验/conware_model_original.pkl \
    --model2 firmware/stm32f407/2蜂鸣器实验/conware_model_simplified.pkl \
    --input firmware/stm32f407/2蜂鸣器实验/recording.tsv \
    --output firmware/stm32f407/2蜂鸣器实验/model_verification_report.txt
```

#### 4.2 说明

`verify_model.py` 会：
1. 加载原始模型和精简模型
2. 使用原始 recording.tsv 作为测试输入
3. 模拟两个模型对每个操作的响应
4. 对比响应的差异

#### 4.3 输出文件

| 文件 | 说明 |
|------|------|
| `model_verification_report.txt` | 验证报告 |

#### 4.4 报告示例

```
======================================================================
模型行为验证报告
======================================================================

【1. 模型结构对比】
  外设数量: 模型1=1, 模型2=1
  地址映射数: 模型1=475136, 模型2=475136
  状态数量: 模型1=95, 模型2=46

【2. 模型行为对比】
  总操作数: 352
  读操作: 258 (匹配=258, 不匹配=0)
  写操作: 94 (匹配=94, 不匹配=0)
  总体匹配率: 100.0%

【3. 验证结论】
  ✅ 两个模型行为完全一致
  ✅ 分类策略有效，没有丢失关���建模信息
  ✅ 精简后的模型可以替代原始模型
```

---

## 一键运行脚本

可以将上述步骤合并为一个脚本：

```bash
#!/bin/bash
# run_full_pipeline.sh

EXP_DIR="/home/makabaka/conware/myconware/firmware/stm32f407/3按键输入实验"

cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

echo "=========================================="
echo "Conware 寄存器分类与模型验证流程"
echo "=========================================="

# 步骤1: 分类与精简
echo ""
echo ">>> 步骤1: 寄存器分类与数据精简"
python conware/register_classifier.py \
    ${EXP_DIR}/recording.tsv \
    -r

# 步骤2: 训练模型
echo ""
echo ">>> 步骤2: 训练模型"
cd /home/makabaka/conware/conware
source ../myconware/venv/bin/activate
export PYTHONPATH=$PWD

python -c "
from conware.model import ConwareModel
import os

# 原始模型
model1 = ConwareModel()
model1.train('${EXP_DIR}/recording.tsv')
model1.save('${EXP_DIR}/conware_model_original.pkl')

# 精简模型
model2 = ConwareModel()
model2.train('${EXP_DIR}/recording_simplified.tsv')
model2.save('${EXP_DIR}/conware_model_simplified.pkl')

print('模型训练完成')
"

# 步骤3: 验证
echo ""
echo ">>> 步骤3: 模型验证"
cd /home/makabaka/conware/myconware
source venv/bin/activate
export PYTHONPATH=$PWD

python conware/verify_model.py \
    --model1 ${EXP_DIR}/conware_model_original.pkl \
    --model2 ${EXP_DIR}/conware_model_simplified.pkl \
    --input ${EXP_DIR}/recording.tsv \
    --output ${EXP_DIR}/model_verification_report.txt

echo ""
echo "=========================================="
echo "流程完成! 查看报告:"
echo "  - ${EXP_DIR}/recording_simplification_report.txt"
echo "  - ${EXP_DIR}/model_verification_report.txt"
echo "=========================================="
```

使用方法：

```bash
chmod +x run_classification_pipeline.sh
./run_classification_pipeline.sh
```

---

## 输出文件汇总

| ���段 | 文件名 | 说明 |
|------|--------|------|
| 原始数据 | `recording.tsv` | 插桩采集的寄存器访问记录 |
| 精简数据 | `recording_simplified.tsv` | 分类精简后的数据 |
| 原始模型 | `conware_model_original.pkl` | 用原始数据训练的模型 |
| 精简模型 | `conware_model_simplified.pkl` | 用精简数据训练的模型 |
| 精简报告 | `recording_simplification_report.txt` | 数据精简统计 |
| 验证报告 | `model_verification_report.txt` | 模型行为验证结果 |

---

## 关键指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 数据压缩率 | 85.2% | 352行 → 52行 |
| 状态精简率 | 51.6% | 95状态 → 46状态 |
| 行为匹配率 | 100% | 两个模型响应完全一致 |

---

## 寄存器分类类型说明

| 类型 | 特征 | 精简策略 | 建模模型 |
|------|------|----------|----------|
| **STORAGE** | 只读或读值固定 | 只保留1条 | SimpleStorage |
| **CONFIG** | 配置后稳定 | 只保留唯一写值 | Pattern |
| **PATTERN** | 有重复读取模式 | 只保留一个周期 | Pattern |
| **INCREASING** | 值单调递增 | 保留首尾+写 | Increasing |
| **MARKOV** | 值随机变化 | 保留值变化记录 | Markov |
| **STATUS** | 状态随外设变化 | 完整保留 | Markov |
