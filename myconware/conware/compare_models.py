#!/usr/bin/env python3
"""
模型对比工具 - Compare Original vs Simplified Models

对比两种方式生成的模型：
1. 使用原始recording.tsv训练的模型
2. 使用精简后recording_simplified.tsv训练的模型

支持两种对比方式：
- 模型结构对比：比较pickle模型的内部结构
- 仿真结果对比：运行固件，比较仿真输出
"""

import argparse
import csv
import os
import pickle
import logging
import sys
from typing import Dict, List, Tuple, Any, Optional
from collections import defaultdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelStructureComparator:
    """模型结构对比器"""
    
    def __init__(self, model1_path: str, model2_path: str):
        self.model1_path = model1_path
        self.model2_path = model2_path
        self.model1 = None
        self.model2 = None
        
    def load_models(self) -> Tuple[bool, bool]:
        """加载两个模型"""
        loaded1 = loaded2 = False
        
        try:
            with open(self.model1_path, 'rb') as f:
                self.model1 = pickle.load(f)
            loaded1 = True
            logger.info(f"Loaded model 1: {self.model1_path}")
        except Exception as e:
            logger.error(f"Failed to load model 1: {e}")
            
        try:
            with open(self.model2_path, 'rb') as f:
                self.model2 = pickle.load(f)
            loaded2 = True
            logger.info(f"Loaded model 2: {self.model2_path}")
        except Exception as e:
            logger.error(f"Failed to load model 2: {e}")
            
        return loaded1, loaded2
        
    def compare(self) -> Dict[str, Any]:
        """执行模型结构对比"""
        if not self.model1 or not self.model2:
            return {'error': 'Models not loaded'}
            
        results = {
            'timestamp': datetime.now().isoformat(),
            'model1': self.model1_path,
            'model2': self.model2_path,
            'comparisons': {}
        }
        
        # 1. 外设数量对比
        results['comparisons']['peripheral_count'] = self._compare_peripheral_count()
        
        # 2. 地址映射对比
        results['comparisons']['address_mapping'] = self._compare_address_mapping()
        
        # 3. 外设状态机对比
        results['comparisons']['state_machines'] = self._compare_state_machines()
        
        # 4. 模型大小对比
        results['comparisons']['model_size'] = self._compare_size()
        
        return results
        
    def _compare_peripheral_count(self) -> Dict[str, Any]:
        """比较外设数量"""
        p1_count = len(self.model1.get('peripherals', []))
        p2_count = len(self.model2.get('peripherals', []))
        
        return {
            'model1_count': p1_count,
            'model2_count': p2_count,
            'difference': p1_count - p2_count,
            'same': p1_count == p2_count
        }
        
    def _compare_address_mapping(self) -> Dict[str, Any]:
        """比较地址映射"""
        addrs1 = set(self.model1.get('model_per_address', {}).keys())
        addrs2 = set(self.model2.get('model_per_address', {}).keys())
        
        only_in_1 = addrs1 - addrs2
        only_in_2 = addrs2 - addrs1
        common = addrs1 & addrs2
        
        return {
            'model1_addresses': len(addrs1),
            'model2_addresses': len(addrs2),
            'common_addresses': len(common),
            'only_in_model1': [hex(a) for a in only_in_1],
            'only_in_model2': [hex(a) for a in only_in_2],
            'addresses_match': len(only_in_1) == 0 and len(only_in_2) == 0
        }
        
    def _compare_state_machines(self) -> Dict[str, Any]:
        """比较状态机结构"""
        states1 = self._count_states(self.model1)
        states2 = self._count_states(self.model2)
        
        return {
            'model1_states': states1,
            'model2_states': states2,
            'difference': states1 - states2,
            'reduction_ratio': f"{(states1 - states2) / max(states1, 1) * 100:.1f}%" if states1 > 0 else "N/A"
        }
        
    def _count_states(self, model: Dict) -> int:
        """统计模型中的状态数量"""
        count = 0
        for p in model.get('peripherals', []):
            count += len(p.get('all_states', []))
        return count
        
    def _compare_size(self) -> Dict[str, Any]:
        """比较模型文件大小"""
        size1 = os.path.getsize(self.model1_path) if os.path.exists(self.model1_path) else 0
        size2 = os.path.getsize(self.model2_path) if os.path.exists(self.model2_path) else 0
        
        return {
            'model1_bytes': size1,
            'model2_bytes': size2,
            'model1_kb': f"{size1 / 1024:.2f}",
            'model2_kb': f"{size2 / 1024:.2f}",
            'reduction_ratio': f"{(size1 - size2) / max(size1, 1) * 100:.1f}%" if size1 > 0 else "N/A"
        }
        
    def generate_report(self, results: Dict) -> str:
        """生成对比报告"""
        report = []
        report.append("=" * 70)
        report.append("模型结构对比报告")
        report.append("=" * 70)
        report.append("")
        report.append(f"模型1 (原始): {results['model1']}")
        report.append(f"模型2 (精简): {results['model2']}")
        report.append(f"对比时间: {results['timestamp']}")
        report.append("")
        
        c = results['comparisons']
        
        # 外设数量
        report.append("-" * 50)
        report.append("1. 外设数量对比")
        report.append("-" * 50)
        report.append(f"  模型1 外设数: {c['peripheral_count']['model1_count']}")
        report.append(f"  模型2 外设数: {c['peripheral_count']['model2_count']}")
        report.append(f"  差异: {c['peripheral_count']['difference']}")
        report.append("")
        
        # 地址映射
        report.append("-" * 50)
        report.append("2. 地址映射对比")
        report.append("-" * 50)
        report.append(f"  模型1 地址数: {c['address_mapping']['model1_addresses']}")
        report.append(f"  模型2 地址数: {c['address_mapping']['model2_addresses']}")
        report.append(f"  共有地址: {c['address_mapping']['common_addresses']}")
        report.append(f"  地址完全匹配: {'是' if c['address_mapping']['addresses_match'] else '否'}")
        if c['address_mapping']['only_in_model1']:
            report.append(f"  仅在模型1中: {', '.join(c['address_mapping']['only_in_model1'])}")
        if c['address_mapping']['only_in_model2']:
            report.append(f"  仅在模型2中: {', '.join(c['address_mapping']['only_in_model2'])}")
        report.append("")
        
        # 状态机
        report.append("-" * 50)
        report.append("3. 状态机状态数量对比")
        report.append("-" * 50)
        report.append(f"  模型1 状态数: {c['state_machines']['model1_states']}")
        report.append(f"  模型2 状态数: {c['state_machines']['model2_states']}")
        report.append(f"  状态减少: {c['state_machines']['difference']}")
        report.append(f"  精简比例: {c['state_machines']['reduction_ratio']}")
        report.append("")
        
        # 文件大小
        report.append("-" * 50)
        report.append("4. 模型文件大小对比")
        report.append("-" * 50)
        report.append(f"  模型1 大小: {c['model_size']['model1_kb']} KB")
        report.append(f"  模型2 大小: {c['model_size']['model2_kb']} KB")
        report.append(f"  精简比例: {c['model_size']['reduction_ratio']}")
        report.append("")
        
        return "\n".join(report)


class SimulationResultComparator:
    """仿真结果对比器"""
    
    def __init__(self, result1_path: str, result2_path: str):
        self.result1_path = result1_path
        self.result2_path = result2_path
        self.results1 = []
        self.results2 = []
        
    def load_results(self) -> Tuple[bool, bool]:
        """加载两个仿真结果文件"""
        loaded1 = self._load_tsv(self.result1_path, self.results1)
        loaded2 = self._load_tsv(self.result2_path, self.results2)
        return loaded1, loaded2
        
    def _load_tsv(self, path: str, results: List) -> bool:
        """加载TSV文件"""
        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            return False
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, dialect='excel-tab')
                next(reader)  # 跳过表头
                for row in reader:
                    if len(row) >= 4:
                        results.append(row)
            logger.info(f"Loaded {len(results)} records from {path}")
            return True
        except Exception as e:
            logger.error(f"Error loading {path}: {e}")
            return False
            
    def compare(self) -> Dict[str, Any]:
        """比较仿真结果"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'result1': self.result1_path,
            'result2': self.result2_path,
            'comparisons': {}
        }
        
        # 记录数对比
        results['comparisons']['record_count'] = {
            'result1_count': len(self.results1),
            'result2_count': len(self.results2),
            'same': len(self.results1) == len(self.results2)
        }
        
        # 地址操作对比
        results['comparisons']['address_operations'] = self._compare_address_operations()
        
        # 值匹配率对比
        results['comparisons']['value_match'] = self._compare_values()
        
        return results
        
    def _compare_address_operations(self) -> Dict[str, Any]:
        """比较地址操作"""
        ops1 = self._extract_operations(self.results1)
        ops2 = self._extract_operations(self.results2)
        
        # 按地址和操作统计
        stats1 = self._aggregate_by_address(ops1)
        stats2 = self._aggregate_by_address(ops2)
        
        all_addrs = set(stats1.keys()) | set(stats2.keys())
        matches = 0
        mismatches = []
        
        for addr in all_addrs:
            if addr in stats1 and addr in stats2:
                if stats1[addr] == stats2[addr]:
                    matches += 1
                else:
                    mismatches.append({
                        'address': hex(addr),
                        'model1': stats1[addr],
                        'model2': stats2[addr]
                    })
            else:
                mismatches.append({
                    'address': hex(addr),
                    'model1': stats1.get(addr, 'N/A'),
                    'model2': stats2.get(addr, 'N/A')
                })
                
        return {
            'total_addresses': len(all_addrs),
            'matching_addresses': matches,
            'match_ratio': f"{matches / max(len(all_addrs), 1) * 100:.1f}%",
            'mismatches': mismatches[:10]  # 只显示前10个
        }
        
    def _extract_operations(self, results: List) -> List[Tuple]:
        """提取操作序列"""
        ops = []
        for row in results:
            try:
                op = row[0].strip()
                addr = int(row[1], 16) if isinstance(row[1], str) else row[1]
                val = int(row[3], 16) if isinstance(row[3], str) else row[3]
                ops.append((op, addr, val))
            except:
                continue
        return ops
        
    def _aggregate_by_address(self, ops: List[Tuple]) -> Dict:
        """按地址聚合操作"""
        stats = defaultdict(lambda: {'READ': 0, 'WRITE': 0, 'values': set()})
        for op, addr, val in ops:
            if op in ['READ', '0']:
                stats[addr]['READ'] += 1
            elif op in ['WRITE', '1']:
                stats[addr]['WRITE'] += 1
            stats[addr]['values'].add(val)
        return dict(stats)
        
    def _compare_values(self) -> Dict[str, Any]:
        """比较值匹配"""
        ops1 = self._extract_operations(self.results1)
        ops2 = self._extract_operations(self.results2)
        
        if len(ops1) != len(ops2):
            return {
                'match_count': 0,
                'total_count': max(len(ops1), len(ops2)),
                'match_ratio': 'N/A (different lengths)',
                'note': 'Operation sequences have different lengths'
            }
            
        matches = 0
        mismatches = []
        
        for i, (op1, op2) in enumerate(zip(ops1, ops2)):
            if op1 == op2:
                matches += 1
            else:
                if len(mismatches) < 10:
                    mismatches.append({
                        'index': i,
                        'model1': op1,
                        'model2': op2
                    })
                    
        return {
            'match_count': matches,
            'total_count': len(ops1),
            'match_ratio': f"{matches / len(ops1) * 100:.1f}%",
            'sample_mismatches': mismatches
        }
        
    def generate_report(self, results: Dict) -> str:
        """生成对比报告"""
        report = []
        report.append("=" * 70)
        report.append("仿真结果对比报告")
        report.append("=" * 70)
        report.append("")
        report.append(f"结果1 (原始模型): {results['result1']}")
        report.append(f"结果2 (精简模型): {results['result2']}")
        report.append(f"对比时间: {results['timestamp']}")
        report.append("")
        
        c = results['comparisons']
        
        # 记录数
        report.append("-" * 50)
        report.append("1. 记录数量对比")
        report.append("-" * 50)
        report.append(f"  结果1 记录数: {c['record_count']['result1_count']}")
        report.append(f"  结果2 记录数: {c['record_count']['result2_count']}")
        report.append(f"  数量相同: {'是' if c['record_count']['same'] else '否'}")
        report.append("")
        
        # 地址操作
        report.append("-" * 50)
        report.append("2. 地址操作统计对比")
        report.append("-" * 50)
        report.append(f"  总地址数: {c['address_operations']['total_addresses']}")
        report.append(f"  匹配地址数: {c['address_operations']['matching_addresses']}")
        report.append(f"  匹配率: {c['address_operations']['match_ratio']}")
        if c['address_operations']['mismatches']:
            report.append("  部分不匹配地址:")
            for m in c['address_operations']['mismatches'][:5]:
                report.append(f"    {m['address']}: 原始={m['model1']}, 精简={m['model2']}")
        report.append("")
        
        # 值匹配
        report.append("-" * 50)
        report.append("3. 操作序列匹配对比")
        report.append("-" * 50)
        report.append(f"  匹配数量: {c['value_match']['match_count']}")
        report.append(f"  总数量: {c['value_match']['total_count']}")
        report.append(f"  匹配率: {c['value_match']['match_ratio']}")
        if c['value_match'].get('sample_mismatches'):
            report.append("  样例不匹配:")
            for m in c['value_match']['sample_mismatches'][:5]:
                report.append(f"    位置{m['index']}: 原始={m['model1']}, 精简={m['model2']}")
        report.append("")
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="对比原始模型与精简模型"
    )
    parser.add_argument(
        '--model1', '-m1',
        help='原始模型路径 (.pkl)'
    )
    parser.add_argument(
        '--model2', '-m2',
        help='精简模型路径 (.pkl)'
    )
    parser.add_argument(
        '--sim1', '-s1',
        help='原始模型仿真结果 (.csv/.tsv)'
    )
    parser.add_argument(
        '--sim2', '-s2',
        help='精简模型仿真结果 (.csv/.tsv)'
    )
    parser.add_argument(
        '--dir', '-d',
        help='目录路径，自动查找配对文件'
    )
    parser.add_argument(
        '--output', '-o',
        help='输出报告路径'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    reports = []
    
    # 目录模式
    if args.dir:
        dir_path = args.dir
        model1_path = os.path.join(dir_path, 'conware_model.pkl')
        model2_path = os.path.join(dir_path, 'conware_model_simplified.pkl')
        sim1_path = os.path.join(dir_path, 'emulated_output.csv')
        sim2_path = os.path.join(dir_path, 'emulated_simplified_output.csv')
        
    # 单独指定文件模式
    else:
        if not args.model1 or not args.model2:
            logger.error("请指定 --model1 和 --model2 或使用 --dir")
            return 1
        model1_path = args.model1
        model2_path = args.model2
        sim1_path = args.sim1
        sim2_path = args.sim2
        
    # 模型结构对比
    if os.path.exists(model1_path) and os.path.exists(model2_path):
        logger.info("执行模型结构对比...")
        comparator = ModelStructureComparator(model1_path, model2_path)
        if comparator.load_models():
            results = comparator.compare()
            report = comparator.generate_report(results)
            reports.append("【模型结构对比】\n" + report)
            print(report)
    
    # 仿真结果对比
    if sim1_path and sim2_path and os.path.exists(sim1_path) and os.path.exists(sim2_path):
        logger.info("执行仿真结果对比...")
        comparator = SimulationResultComparator(sim1_path, sim2_path)
        if comparator.load_results():
            results = comparator.compare()
            report = comparator.generate_report(results)
            reports.append("\n【仿真结果对比】\n" + report)
            print("\n" + report)
            
    # 保存报告
    if args.output and reports:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("\n".join(reports))
        logger.info(f"报告已保存: {args.output}")
        
    return 0


if __name__ == "__main__":
    exit(main())
