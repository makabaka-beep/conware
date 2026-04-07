#!/usr/bin/env python3
"""
模型行为验证器 - Offline Model Behavior Verification

在不需要QEMU的情况下，模拟模型对输入序列的响应，
对比原始模型和精简模型的行为差异。

原理：
1. 读取原始recording.tsv作为测试输入
2. 分别用两个模型处理每个操作
3. 记录模型的响应（读返回值、写状态变化）
4. 对比两个模型的响应差异
"""

import os
import sys
import csv
import pickle
import argparse
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict

# 添加conware路径
sys.path.insert(0, '/home/makabaka/conware/conware')


def load_pickle_model(filepath: str) -> Optional[Dict]:
    """加载pickle模型"""
    try:
        with open(filepath, 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        print(f"加载模型失败 {filepath}: {e}")
        return None


def parse_recording(filepath: str) -> List[Dict]:
    """解析recording文件"""
    records = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, dialect='excel-tab')
        next(reader)  # 跳过表头
        
        for line in reader:
            if len(line) < 7:
                continue
            records.append({
                'op': line[0].strip(),
                'seqn': int(line[1]),
                'addr': int(line[2], 16),
                'value': int(line[3], 16),
                'timestamp': int(line[6]) if len(line) > 6 else 0
            })
    
    return records


class ModelSimulator:
    """简化的模型模拟器"""
    
    def __init__(self, model_data: Dict):
        self.model_data = model_data
        self.peripherals = model_data.get('peripherals', [])
        self.address_to_peripheral = {}
        self._build_mapping()
        
    def _build_mapping(self):
        """构建地址到外设的映射"""
        for p in self.peripherals:
            if hasattr(p, 'addresses'):
                for addr in p.addresses:
                    self.address_to_peripheral[int(addr)] = p
            if hasattr(p, 'model_per_address'):
                for addr in p.model_per_address:
                    self.address_to_peripheral[int(addr)] = p
                    
    def get_state_count(self) -> int:
        """获取状态数量"""
        count = 0
        for p in self.peripherals:
            if hasattr(p, 'all_states'):
                count += len(p.all_states)
        return count
        
    def simulate_read(self, addr: int) -> Tuple[int, str]:
        """模拟读操作"""
        if addr in self.address_to_peripheral:
            p = self.address_to_peripheral[addr]
            if hasattr(p, 'model_per_address') and addr in p.model_per_address:
                model = p.model_per_address[addr]
                val = model.read() if hasattr(model, 'read') else 0
                return val, type(model).__name__
        return 0, "UNKNOWN"
        
    def simulate_write(self, addr: int, value: int) -> str:
        """模拟写操作"""
        if addr in self.address_to_peripheral:
            p = self.address_to_peripheral[addr]
            if hasattr(p, 'model_per_address') and addr in p.model_per_address:
                model = p.model_per_address[addr]
                if hasattr(model, 'write'):
                    model.write(addr, value)
                return type(model).__name__
        return "UNKNOWN"


class ModelBehaviorComparator:
    """模型行为对比器"""
    
    def __init__(self, model1_path: str, model2_path: str, test_input_path: str):
        self.model1_path = model1_path
        self.model2_path = model2_path
        self.test_input_path = test_input_path
        self.model1_data = None
        self.model2_data = None
        self.sim1 = None
        self.sim2 = None
        self.test_records = []
        
    def load_models(self) -> bool:
        """加载两个模型"""
        print("加载模型...")
        
        self.model1_data = load_pickle_model(self.model1_path)
        self.model2_data = load_pickle_model(self.model2_path)
        
        if not self.model1_data or not self.model2_data:
            print("模型加载失败")
            return False
            
        self.sim1 = ModelSimulator(self.model1_data)
        self.sim2 = ModelSimulator(self.model2_data)
        
        print(f"  模型1: {len(self.model1_data.get('peripherals', []))} 个外设")
        print(f"  模型2: {len(self.model2_data.get('peripherals', []))} 个外设")
        
        return True
        
    def load_test_input(self) -> bool:
        """加载测试输入"""
        print(f"加载测试输入: {self.test_input_path}")
        
        if not os.path.exists(self.test_input_path):
            print("测试输入文件不存在")
            return False
            
        self.test_records = parse_recording(self.test_input_path)
        print(f"  加载了 {len(self.test_records)} 条测试记录")
        
        return len(self.test_records) > 0
        
    def compare_structures(self) -> Dict:
        """对比模型结构"""
        result = {
            'peripherals': {
                'model1': len(self.model1_data.get('peripherals', [])),
                'model2': len(self.model2_data.get('peripherals', []))
            },
            'addresses': {
                'model1': len(self.model1_data.get('model_per_address', {})),
                'model2': len(self.model2_data.get('model_per_address', {}))
            }
        }
        
        # 统计状态数
        result['states'] = {
            'model1': self.sim1.get_state_count() if self.sim1 else 0,
            'model2': self.sim2.get_state_count() if self.sim2 else 0
        }
        
        return result
        
    def run_behavior_comparison(self) -> Dict:
        """运行行为对比"""
        if not self.test_records:
            return {'error': 'No test records'}
            
        results = {
            'total_operations': len(self.test_records),
            'reads': {'total': 0, 'matched': 0, 'mismatched': 0},
            'writes': {'total': 0, 'matched': 0, 'mismatched': 0},
            'mismatches': []
        }
        
        # 分别模拟两个模型
        sim1_states = {}
        sim2_states = {}
        
        for i, rec in enumerate(self.test_records):
            op = rec['op']
            addr = rec['addr']
            value = rec['value']
            
            if op in ['READ', '0']:
                results['reads']['total'] += 1
                
                # 模型1读
                val1, type1 = self.sim1.simulate_read(addr) if self.sim1 else (0, 'N/A')
                sim1_states[addr] = val1
                
                # 模型2读
                val2, type2 = self.sim2.simulate_read(addr) if self.sim2 else (0, 'N/A')
                sim2_states[addr] = val2
                
                # 对比
                if val1 == val2:
                    results['reads']['matched'] += 1
                else:
                    results['reads']['mismatched'] += 1
                    if len(results['mismatches']) < 20:
                        results['mismatches'].append({
                            'type': 'READ',
                            'index': i,
                            'addr': hex(addr),
                            'model1': val1,
                            'model2': val2,
                            'model1_type': type1,
                            'model2_type': type2
                        })
                        
            elif op in ['WRITE', '1']:
                results['writes']['total'] += 1
                
                # 模型1写
                type1 = self.sim1.simulate_write(addr, value) if self.sim1 else 'N/A'
                
                # 模型2写
                type2 = self.sim2.simulate_write(addr, value) if self.sim2 else 'N/A'
                
                if type1 == type2:
                    results['writes']['matched'] += 1
                else:
                    results['writes']['mismatched'] += 1
        
        return results
        
    def generate_report(self) -> str:
        """生成完整报告"""
        report = []
        report.append("=" * 70)
        report.append("模型行为验证报告")
        report.append("=" * 70)
        report.append("")
        report.append(f"原始模型: {self.model1_path}")
        report.append(f"精简模型: {self.model2_path}")
        report.append(f"测试输入: {self.test_input_path}")
        report.append("")
        
        # 结构对比
        struct = self.compare_structures()
        report.append("-" * 50)
        report.append("1. 模型结构对比")
        report.append("-" * 50)
        report.append(f"  外设数量: 模型1={struct['peripherals']['model1']}, 模型2={struct['peripherals']['model2']}")
        report.append(f"  地址映射数: 模型1={struct['addresses']['model1']}, 模型2={struct['addresses']['model2']}")
        report.append(f"  状态数量: 模型1={struct['states']['model1']}, 模型2={struct['states']['model2']}")
        report.append("")
        
        # 行为对比
        report.append("-" * 50)
        report.append("2. 模型行为对比（基于测试输入）")
        report.append("-" * 50)
        
        behavior = self.run_behavior_comparison()
        
        if 'error' in behavior:
            report.append(f"  错误: {behavior['error']}")
        else:
            total_ops = behavior['total_operations']
            total_matched = behavior['reads']['matched'] + behavior['writes']['matched']
            total_mismatched = behavior['reads']['mismatched'] + behavior['writes']['mismatched']
            
            report.append(f"  总操作数: {total_ops}")
            report.append(f"  读操作: {behavior['reads']['total']} (匹配={behavior['reads']['matched']}, 不匹配={behavior['reads']['mismatched']})")
            report.append(f"  写操作: {behavior['writes']['total']} (匹配={behavior['writes']['matched']}, 不匹配={behavior['writes']['mismatched']})")
            report.append("")
            
            if total_ops > 0:
                match_rate = total_matched / total_ops * 100
                report.append(f"  总体匹配率: {match_rate:.1f}%")
            
            report.append("")
            
            if behavior['reads']['mismatched'] > 0:
                report.append("  读操作不匹配详情:")
                for m in behavior['mismatches']:
                    report.append(f"    [{m['index']}] addr={m['addr']}: 模型1={m['model1']} ({m['model1_type']}), 模型2={m['model2']} ({m['model2_type']})")
        
        # 结论
        report.append("")
        report.append("-" * 50)
        report.append("3. 验证结论")
        report.append("-" * 50)
        
        if 'error' not in behavior:
            if behavior['reads']['mismatched'] == 0 and behavior['writes']['mismatched'] == 0:
                report.append("  ✅ 两个模型行为完全一致")
                report.append("  ✅ 分类策略有效，没有丢失关键建模信息")
                report.append("  ✅ 精简后的模型可以替代原始模型")
            else:
                mismatch_rate = (behavior['reads']['mismatched'] + behavior['writes']['mismatched']) / max(behavior['total_operations'], 1) * 100
                if mismatch_rate < 5:
                    report.append(f"  ⚠️ 模型行为有小差异（{mismatch_rate:.1f}%）")
                    report.append("  ⚠️ 可能需要微调分类阈值")
                else:
                    report.append(f"  ❌ 模型行为有显著差异（{mismatch_rate:.1f}%）")
                    report.append("  ❌ 需要重新评估分类策略")
        else:
            report.append("  ⚠️ 无法进行行为对比")
            
        report.append("")
        report.append("=" * 70)
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description="模型行为验证工具")
    parser.add_argument('--model1', '-m1', required=True, help='原始模型路径')
    parser.add_argument('--model2', '-m2', required=True, help='精简模型路径')
    parser.add_argument('--input', '-i', required=True, help='测试输入文件')
    parser.add_argument('--output', '-o', help='输出报告文件')
    
    args = parser.parse_args()
    
    # 创建验证器
    comparator = ModelBehaviorComparator(
        args.model1,
        args.model2,
        args.input
    )
    
    # 加载数据
    if not comparator.load_models():
        return 1
        
    if not comparator.load_test_input():
        return 1
        
    # 生成报告
    report = comparator.generate_report()
    print(report)
    
    # 保存报告
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存: {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())
