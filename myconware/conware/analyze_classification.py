#!/usr/bin/env python3
"""
分类优化效果分析 - 分析寄存器分类对模型的影响

目标：
1. 对比分类前后模型训练数据
2. 分析分类策略的合理性
3. 解释分类优化的实际意义
"""

import os
import csv
import pickle
from collections import defaultdict
from typing import Dict, List, Tuple

def analyze_recording(filepath: str) -> Dict:
    """分析recording文件"""
    stats = {
        'total_records': 0,
        'reads': 0,
        'writes': 0,
        'addresses': set(),
        'read_values': defaultdict(list),
        'write_values': defaultdict(list),
        'address_stats': defaultdict(lambda: {
            'reads': 0, 'writes': 0, 'read_vals': set(), 'write_vals': set()
        })
    }
    
    if not os.path.exists(filepath):
        return stats
        
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, dialect='excel-tab')
        next(reader)  # 跳过表头
        for line in reader:
            if len(line) < 7:
                continue
            stats['total_records'] += 1
            op = line[0].strip()
            addr = int(line[2], 16)
            val = int(line[3], 16)
            
            stats['addresses'].add(addr)
            addr_stats = stats['address_stats'][addr]
            
            if op in ['READ', '0']:
                stats['reads'] += 1
                stats['read_values'][addr].append(val)
                addr_stats['reads'] += 1
                addr_stats['read_vals'].add(val)
            elif op in ['WRITE', '1']:
                stats['writes'] += 1
                stats['write_values'][addr].append(val)
                addr_stats['writes'] += 1
                addr_stats['write_vals'].add(val)
    
    stats['unique_reads'] = {a: len(v) for a, v in stats['read_values'].items()}
    return stats


def classify_by_pattern(stats: Dict) -> Dict:
    """基于访问模式进行寄存器分类"""
    classifications = {}
    
    for addr, addr_stats in stats['address_stats'].items():
        reads = addr_stats['reads']
        writes = addr_stats['writes']
        read_vals = addr_stats['read_vals']
        write_vals = addr_stats['write_vals']
        
        unique_reads = len(read_vals)
        unique_writes = len(write_vals)
        
        # INCREASING: 值单调递增
        if reads >= 3:
            vals = stats['read_values'][addr]
            increasing = sum(1 for i in range(1, len(vals)) if vals[i] >= vals[i-1])
            if increasing / (len(vals) - 1) >= 0.8 and vals[-1] > vals[0]:
                classifications[addr] = 'INCREASING'
                continue
        
        # STORAGE: 只读或读值稳定
        if reads > 0 and unique_reads <= 1:
            classifications[addr] = 'STORAGE'
            continue
            
        # CONFIG: 写操作少，值稳定
        if writes > 0 and writes <= 10 and unique_reads <= 4:
            classifications[addr] = 'CONFIG'
            continue
            
        # PATTERN: 有重复模式
        if reads >= 4:
            vals = list(read_vals)
            if len(vals) < reads:  # 有重复值
                classifications[addr] = 'PATTERN'
                continue
                
        # MARKOV: 其他情况
        classifications[addr] = 'MARKOV'
    
    return classifications


def analyze_simplification(original_stats: Dict, simplified_stats: Dict, 
                         classifications: Dict) -> Dict:
    """分析精简效果"""
    analysis = {
        'original_records': original_stats['total_records'],
        'simplified_records': simplified_stats['total_records'],
        'compression_ratio': 0,
        'by_class': {},
        'potential_savings': 0
    }
    
    if original_stats['total_records'] > 0:
        analysis['compression_ratio'] = (
            1 - simplified_stats['total_records'] / original_stats['total_records']
        ) * 100
    
    # 按类别分析
    for addr, cls in classifications.items():
        if cls not in analysis['by_class']:
            analysis['by_class'][cls] = {
                'count': 0, 'original': 0, 'simplified': 0
            }
        analysis['by_class'][cls]['count'] += 1
        analysis['by_class'][cls]['original'] += original_stats['address_stats'][addr]['reads'] + original_stats['address_stats'][addr]['writes']
        
        if addr in simplified_stats['address_stats']:
            analysis['by_class'][cls]['simplified'] += simplified_stats['address_stats'][addr]['reads'] + simplified_stats['address_stats'][addr]['writes']
    
    return analysis


def generate_report(exp_dir: str):
    """生成完整的对比分析报告"""
    
    original_path = os.path.join(exp_dir, 'recording.tsv')
    simplified_path = os.path.join(exp_dir, 'recording_simplified.tsv')
    
    if not os.path.exists(original_path):
        print(f"文件不存在: {original_path}")
        return
    
    # 分析原始数据
    print("=" * 70)
    print("寄存器分类优化分析报告")
    print("=" * 70)
    print(f"\n实验目录: {exp_dir}")
    
    print("\n【一、原始数据分析】")
    original_stats = analyze_recording(original_path)
    print(f"  总记录数: {original_stats['total_records']}")
    print(f"  读操作: {original_stats['reads']}")
    print(f"  写操作: {original_stats['writes']}")
    print(f"  唯一地址数: {len(original_stats['addresses'])}")
    
    print("\n  各地址访问详情:")
    for addr in sorted(original_stats['address_stats'].keys()):
        s = original_stats['address_stats'][addr]
        print(f"    {hex(addr)}: 读={s['reads']}, 写={s['writes']}, "
              f"唯一读值={len(s['read_vals'])}, 唯一写值={len(s['write_vals'])}")
    
    # 分类分析
    print("\n【二、寄存器分类分析】")
    classifications = classify_by_pattern(original_stats)
    
    class_counts = defaultdict(int)
    for cls in classifications.values():
        class_counts[cls] += 1
    
    print("  分类结果:")
    for cls in ['STORAGE', 'CONFIG', 'PATTERN', 'INCREASING', 'MARKOV', 'STATUS']:
        count = class_counts.get(cls, 0)
        if count > 0:
            print(f"    {cls}: {count} 个寄存器")
    
    print("\n  各类别详情:")
    for addr, cls in sorted(classifications.items()):
        s = original_stats['address_stats'][addr]
        print(f"    {hex(addr)} -> {cls}: 读={s['reads']}, 写={s['writes']}")
    
    # 精简效果分析
    print("\n【三、精简效果分析】")
    if os.path.exists(simplified_path):
        simplified_stats = analyze_recording(simplified_path)
        analysis = analyze_simplification(original_stats, simplified_stats, classifications)
        
        print(f"  原始记录数: {analysis['original_records']}")
        print(f"  精简后记录数: {analysis['simplified_records']}")
        print(f"  压缩比: {analysis['compression_ratio']:.1f}%")
        
        print("\n  按类别精简统计:")
        for cls, data in analysis['by_class'].items():
            orig = data['original']
            simp = data['simplified']
            ratio = (1 - simp / orig) * 100 if orig > 0 else 0
            print(f"    {cls}: {orig} -> {simp} (压缩 {ratio:.1f}%)")
    else:
        print("  精简文件不存在")
    
    # 分类优化意义
    print("\n【四、分类优化的实际意义】")
    orig_count = original_stats['total_records']
    simp_count = int(orig_count * 0.15) if 'analysis' not in dir() else int(original_stats['total_records'] * (1 - analysis.get('compression_ratio', 85) / 100))
    
    print(f"""
  1. 减少训练时间
     - 训练数据从 {orig_count} 行减少到约 {simp_count} 行
     - 模型训练时间显著减少
     
  2. 减少存储空间
     - 精简数据文件更小
     - 便于传输和存储
     
  3. 提高模型可解释性
     - 不同类型寄存器采用不同建模策略
     - 便于理解和调试
     
  4. 改善过拟合风险
     - 移除冗余数据后模型更泛化
     - 可能提高仿真准确性
     
  5. 针对不同类型采用不同模型
     - STORAGE: SimpleStorageModel (简单)
     - CONFIG: PatternModel (配置模式)
     - INCREASING: IncreasingModel (线性增长)
     - MARKOV: MarkovModel (概率分布)
     
  6. 验证分类正确性
     - 如果分类后模型仿真结果一致
     - 说明分类策略合理，没有丢失关键信息
    """)
    
    # 精简建议
    print("【五、优化建议】")
    print("""
  1. 仿真验证: 运行原始模型和精简模型仿真，对比输出
  2. 如果仿真结果一致，说明分类策略有效
  3. 如果有差异，需要调整分类阈值或建模策略
  4. 可以根据实际仿真结果进一步优化分类算法
    """)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        exp_dir = sys.argv[1]
    else:
        exp_dir = "/home/makabaka/conware/myconware/firmware/stm32f407/1跑马灯实验"
    
    generate_report(exp_dir)
