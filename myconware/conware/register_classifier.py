#!/usr/bin/env python3
"""
寄存器分类与精简算法 - Register Classification & Simplification

根据开题报告要求，对recording.tsv中的寄存器访问数据进行分类和精简，
生成可用于简化建模的分类数据。

核心思想：
1. 根据寄存器访问模式分类
2. 不同类型的寄存器需要不同的建模数据
3. 精简冗余数据，保留建模必需信息

分类类别:
- STORAGE: 简单存储寄存器 → 只需保留初始值和写操作
- CONFIG: 配置寄存器 → 只需保留初始化序列
- PATTERN: 模式寄存器 → 保留一个完整周期
- STATUS: 状态寄存器 → 需要完整读写序列
- INCREASING: 递增寄存器 → 只需保留起始值和增长规律
- MARKOV: 马尔可夫寄存器 → 需要完整序列进行概率建模
"""

import csv
import os
import logging
import argparse
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any, Optional, Set
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RegisterClass(Enum):
    """寄存器分类枚举"""
    STORAGE = "STORAGE"        # 简单存储：只需保留写操作
    CONFIG = "CONFIG"          # 配置寄存器：只需初始化序列
    PATTERN = "PATTERN"        # 模式寄存器：只需一个周期
    STATUS = "STATUS"          # 状态寄存器：需要完整序列
    INCREASING = "INCREASING"  # 递增寄存器：只需起始值和增长规律
    MARKOV = "MARKOV"          # 马尔可夫寄存器：需要完整序列


class RegisterRecord:
    """单个寄存器的访问记录"""
    
    def __init__(self, address: int):
        self.address = address
        self.reads: List[Tuple[int, int, int, int]] = []  # (seqn, value, pc, timestamp)
        self.writes: List[Tuple[int, int, int, int]] = []  # (seqn, value, pc, timestamp)
        
    def add_read(self, seqn: int, value: int, pc: int, timestamp: int):
        self.reads.append((seqn, value, pc, timestamp))
        
    def add_write(self, seqn: int, value: int, pc: int, timestamp: int):
        self.writes.append((seqn, value, pc, timestamp))
        
    @property
    def has_writes(self) -> bool:
        return len(self.writes) > 0
        
    @property
    def read_count(self) -> int:
        return len(self.reads)
        
    @property
    def write_count(self) -> int:
        return len(self.writes)
        
    @property
    def unique_read_values(self) -> set:
        return set(r[1] for r in self.reads)
        
    @property
    def unique_write_values(self) -> set:
        return set(w[1] for w in self.writes)
        
    def get_simplified_data(self, register_class: RegisterClass) -> Dict[str, Any]:
        """
        根据寄存器类型，返回精简后的建模数据
        """
        if register_class == RegisterClass.STORAGE:
            return self._simplify_storage()
        elif register_class == RegisterClass.CONFIG:
            return self._simplify_config()
        elif register_class == RegisterClass.PATTERN:
            return self._simplify_pattern()
        elif register_class == RegisterClass.INCREASING:
            return self._simplify_increasing()
        elif register_class == RegisterClass.MARKOV:
            return self._simplify_markov()
        else:  # STATUS
            return self._simplify_status()
            
    def _simplify_storage(self) -> Dict:
        """STORAGE: 只保留最后一次写入值"""
        if self.has_writes:
            last_write = self.writes[-1]
            return {
                'type': 'STORAGE',
                'init_value': last_write[1],
                'write_count': len(self.writes),
                'reads_preserved': 0  # 读取可通过写值推断
            }
        else:
            # 只读的情况
            return {
                'type': 'STORAGE',
                'init_value': self.reads[0][1] if self.reads else 0,
                'write_count': 0,
                'reads_preserved': 1
            }
            
    def _simplify_config(self) -> Dict:
        """CONFIG: 只保留初始化序列（唯一写值）"""
        unique_writes = []
        seen = set()
        for w in self.writes:
            if w[1] not in seen:
                unique_writes.append(w)
                seen.add(w[1])
                
        return {
            'type': 'CONFIG',
            'init_sequence': [(w[1], w[3]) for w in unique_writes],  # (value, timestamp)
            'unique_write_count': len(unique_writes),
            'total_writes': len(self.writes),
            'stable_value': self._get_most_common_value()
        }
        
    def _simplify_pattern(self) -> Dict:
        """PATTERN: 提取一个重复周期"""
        if not self.reads:
            return self._simplify_storage()
            
        read_vals = [r[1] for r in self.reads]
        pattern = self._extract_pattern(read_vals)
        
        return {
            'type': 'PATTERN',
            'pattern': pattern,
            'pattern_length': len(pattern),
            'compression_ratio': len(read_vals) / len(pattern) if pattern else 1
        }
        
    def _simplify_increasing(self) -> Dict:
        """INCREASING: 保留起始值和增长规律"""
        if not self.reads:
            return {'type': 'INCREASING', 'error': 'no_reads'}
            
        read_vals = [r[1] for r in self.reads]
        start_val = read_vals[0]
        
        # 计算平均增长
        if len(read_vals) > 1:
            total_growth = read_vals[-1] - read_vals[0]
            avg_increment = total_growth / (len(read_vals) - 1)
        else:
            avg_increment = 0
            
        return {
            'type': 'INCREASING',
            'start_value': start_val,
            'end_value': read_vals[-1],
            'avg_increment': avg_increment,
            'total_reads': len(read_vals)
        }
        
    def _simplify_markov(self) -> Dict:
        """MARKOV: 精简为值分布"""
        if not self.reads:
            return {'type': 'MARKOV', 'error': 'no_reads'}
            
        value_counts = Counter(r[1] for r in self.reads)
        total = len(self.reads)
        
        # 只保留概率分布
        distribution = {v: c / total for v, c in value_counts.items()}
        
        return {
            'type': 'MARKOV',
            'distribution': distribution,
            'unique_values': len(distribution),
            'total_reads': total
        }
        
    def _simplify_status(self) -> Dict:
        """STATUS: 保留完整序列（但可精简重复）"""
        return {
            'type': 'STATUS',
            'write_sequence': [w[1] for w in self.writes],
            'read_sequence': [r[1] for r in self.reads],
            'total_writes': len(self.writes),
            'total_reads': len(self.reads)
        }
        
    def _extract_pattern(self, values: List[int]) -> List[int]:
        """提取重复模式"""
        if len(values) < 2:
            return values
            
        for pattern_len in range(1, len(values) // 2 + 1):
            pattern = values[:pattern_len]
            is_pattern = True
            
            for i in range(pattern_len, len(values), pattern_len):
                chunk = values[i:i + pattern_len]
                if chunk != pattern[:len(chunk)]:
                    is_pattern = False
                    break
                    
            if is_pattern:
                return pattern
                
        return values
        
    def _get_most_common_value(self) -> Optional[int]:
        """获取最常见的值"""
        if self.reads:
            return Counter(r[1] for r in self.reads).most_common(1)[0][0]
        elif self.writes:
            return Counter(w[1] for w in self.writes).most_common(1)[0][0]
        return None


class RegisterClassifier:
    """寄存器分类器"""
    
    def __init__(self):
        self.registers: Dict[int, RegisterRecord] = {}
        self.raw_data: List[List[str]] = []  # 原始数据行
        self.header: List[str] = []
        
    def parse_tsv(self, filepath: str) -> bool:
        """解析TSV文件"""
        logger.info(f"Parsing TSV file: {filepath}")
        
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return False
            
        try:
            self.raw_data = []
            self.header = []
            
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, dialect='excel-tab')
                
                # 保留表头
                self.header = next(reader)
                logger.debug(f"Header: {self.header}")
                
                for line_num, line in enumerate(reader):
                    # 允许7列（无Model列）或8/9列（有Model列）
                    if len(line) < 7:
                        continue
                    self.raw_data.append(line)
                    
                    try:
                        op = line[0].strip()
                        seqn = int(line[1])
                        addr = int(line[2], 16)
                        val = int(line[3], 16)
                        # 根据列数判断PC和Timestamp的位置
                        if len(line) >= 8:
                            # 8/9列格式: ..., Value, Value(Model), PC, Size, Timestamp, ...
                            pc = int(line[5], 16) if line[5].startswith('0x') else int(line[5])
                            timestamp = int(line[7])
                        else:
                            # 7列格式: ..., Value, PC, Size, Timestamp
                            pc = int(line[4], 16) if line[4].startswith('0x') else int(line[4])
                            timestamp = int(line[6])
                        
                        if addr not in self.registers:
                            self.registers[addr] = RegisterRecord(addr)
                            
                        if op in ["READ", "0"]:
                            self.registers[addr].add_read(seqn, val, pc, timestamp)
                        elif op in ["WRITE", "1"]:
                            self.registers[addr].add_write(seqn, val, pc, timestamp)
                            
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Error parsing line {line_num + 2}: {e}")
                        continue
                        
            logger.info(f"Parsed {len(self.registers)} unique addresses, {len(self.raw_data)} records")
            return True
            
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return False
            
    def classify_storage(self, reg: RegisterRecord) -> bool:
        """STORAGE: 简单读-写存储"""
        if len(reg.reads) == 0:
            return False
            
        # 只有READ操作且值相同
        if not reg.has_writes:
            if len(reg.unique_read_values) == 1:
                return True
            return False
            
        # 检查是否写后总是返回写入值
        if len(reg.writes) == 1:
            write_val = reg.writes[0][1]
            # 所有读取是否都返回写入值
            if all(r[1] == write_val for r in reg.reads):
                return True
                
        # 检查读值是否稳定
        if len(reg.unique_read_values) == 1 and len(reg.writes) <= 5:
            return True
            
        return False
        
    def classify_config(self, reg: RegisterRecord) -> bool:
        """CONFIG: 配置寄存器"""
        if not reg.has_writes:
            return False
            
        if len(reg.unique_read_values) > 4:
            return False
            
        if len(reg.writes) <= 20 and len(reg.reads) <= 50:
            most_common = reg._get_most_common_value()
            if most_common is not None:
                stable_ratio = sum(1 for r in reg.reads if r[1] == most_common) / max(len(reg.reads), 1)
                if stable_ratio >= 0.6:
                    return True
                    
        return False
        
    def classify_pattern(self, reg: RegisterRecord) -> bool:
        """PATTERN: 模式寄存器"""
        if len(reg.reads) < 4:
            return False
            
        read_vals = [r[1] for r in reg.reads]
        pattern = reg._extract_pattern(read_vals)
        
        # 模式长度明显小于原始长度
        if len(pattern) < len(read_vals) and len(pattern) >= 2:
            return True
            
        return False
        
    def classify_increasing(self, reg: RegisterRecord) -> bool:
        """INCREASING: 递增寄存器"""
        if len(reg.reads) < 3:
            return False
            
        read_vals = [r[1] for r in reg.reads]
        
        # 检查单调递增
        increasing_count = sum(1 for i in range(1, len(read_vals)) if read_vals[i] >= read_vals[i-1])
        increasing_ratio = increasing_count / (len(read_vals) - 1)
        
        return increasing_ratio >= 0.8 and read_vals[-1] > read_vals[0]
        
    def classify_markov(self, reg: RegisterRecord) -> bool:
        """MARKOV: 马尔可夫寄存器"""
        if len(reg.reads) < 3:
            return False
            
        if len(reg.unique_read_values) < 2:
            return False
            
        # 排除其他分类
        if self.classify_storage(reg) or self.classify_increasing(reg) or self.classify_pattern(reg):
            return False
            
        return True
        
    def classify_register(self, reg: RegisterRecord) -> RegisterClass:
        """对单个寄存器进行分类"""
        if self.classify_increasing(reg):
            return RegisterClass.INCREASING
        if self.classify_storage(reg):
            return RegisterClass.STORAGE
        if self.classify_pattern(reg):
            return RegisterClass.PATTERN
        if self.classify_config(reg):
            return RegisterClass.CONFIG
        if self.classify_markov(reg):
            return RegisterClass.MARKOV
        return RegisterClass.STATUS
        
    def classify_all(self) -> Dict[int, RegisterClass]:
        """对所有寄存器进行分类"""
        return {addr: self.classify_register(reg) for addr, reg in self.registers.items()}


class SimplifiedTSVWriter:
    """写精简后的TSV文件"""
    
    def __init__(self, classifier: RegisterClassifier):
        self.classifier = classifier
        self.classifications = {}
        
    def write_simplified_tsv(self, input_path: str, output_dir: Optional[str] = None) -> Tuple[bool, str, Dict]:
        """
        生成精简后的TSV文件
        
        Returns:
            (成功标志, 输出文件路径, 精简统计)
        """
        if output_dir is None:
            output_dir = os.path.dirname(input_path)
            
        base_name = os.path.basename(input_path)
        name_without_ext = os.path.splitext(base_name)[0]
        output_path = os.path.join(output_dir, f"{name_without_ext}_simplified.tsv")
        
        logger.info(f"Writing simplified TSV to: {output_path}")
        
        # 进行分类
        if not self.classifications:
            self.classifications = self.classifier.classify_all()
            
        # 生成精简数据
        simplified_data, stats = self._generate_simplified_data()
        
        try:
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, dialect='excel-tab')
                writer.writerow(self.classifier.header)
                for row in simplified_data:
                    # 保持与原始header相同的列数
                    header_len = len(self.classifier.header)
                    if len(row) < header_len:
                        row = row + [''] * (header_len - len(row))
                    elif len(row) > header_len:
                        row = row[:header_len]
                    writer.writerow(row)
                
            logger.info(f"Simplified from {len(self.classifier.raw_data)} to {len(simplified_data)} records")
            return True, output_path, stats
            
        except Exception as e:
            logger.error(f"Error writing simplified TSV: {e}")
            return False, "", {}
            
    def _generate_simplified_data(self) -> Tuple[List[List[str]], Dict]:
        """生成精简后的数据"""
        simplified = []
        stats = {
            'original_records': len(self.classifier.raw_data),
            'simplified_records': 0,
            'by_class': defaultdict(int)
        }
        
        # 按地址分组原始数据
        addr_data: Dict[int, List[List[str]]] = defaultdict(list)
        for row in self.classifier.raw_data:
            try:
                addr = int(row[2], 16)
                addr_data[addr].append(row)
            except:
                continue
                
        for addr, rows in addr_data.items():
            cls = self.classifications.get(addr, RegisterClass.STATUS)
            simplified_rows = self._simplify_by_class(rows, cls, addr)
            simplified.extend(simplified_rows)
            stats['by_class'][cls.value] += len(simplified_rows)
            
        stats['simplified_records'] = len(simplified)
        stats['compression_ratio'] = f"{stats['simplified_records'] / max(stats['original_records'], 1):.2%}"
        
        return simplified, stats
        
    def _simplify_by_class(self, rows: List[List[str]], cls: RegisterClass, addr: int) -> List[List[str]]:
        """根据分类精简数据，只保留原始8列"""
        if cls == RegisterClass.STORAGE:
            return self._simplify_storage_rows(rows)
        elif cls == RegisterClass.CONFIG:
            return self._simplify_config_rows(rows)
        elif cls == RegisterClass.PATTERN:
            return self._simplify_pattern_rows(rows)
        elif cls == RegisterClass.INCREASING:
            return self._simplify_increasing_rows(rows)
        elif cls == RegisterClass.MARKOV:
            return self._simplify_markov_rows(rows)
        else:
            return [r[:8] for r in rows]
            
    def _simplify_storage_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """STORAGE: 只保留最后一次写和必要的读"""
        result = []
        writes = [r[:8] for r in rows if r[0] in ["WRITE", "1"]]
        reads = [r[:8] for r in rows if r[0] in ["READ", "0"]]
        
        if writes:
            result.append(writes[-1])
        if reads and len(reads) <= 3:
            for r in reads:
                result.append(r)
        if not result and reads:
            result.append(reads[0])
        return result
        
    def _simplify_config_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """CONFIG: 只保留唯一写序列"""
        result = []
        seen_values = set()
        rows = [r[:8] for r in rows]
        sorted_rows = sorted(rows, key=lambda x: int(x[7]) if len(x) > 7 else 0)
        
        for r in sorted_rows:
            val = int(r[3], 16)
            if r[0] in ["WRITE", "1"]:
                if val not in seen_values:
                    result.append(r)
                    seen_values.add(val)
            else:
                if not any(x[0] in ["READ", "0"] for x in result):
                    result.append(r)
        return result
        
    def _simplify_pattern_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """PATTERN: 保留一个完整周期"""
        rows = [r[:8] for r in rows]
        reads = [r for r in rows if r[0] in ["READ", "0"]]
        
        if len(reads) < 4:
            return reads
        read_vals = [int(r[3], 16) for r in reads]
        for pattern_len in range(2, len(read_vals) // 2 + 1):
            pattern = read_vals[:pattern_len]
            full_periods = len(read_vals) // pattern_len
            if full_periods >= 2:
                return reads[:pattern_len]
        return reads[:min(10, len(reads))]
        
    def _simplify_increasing_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """INCREASING: 保留起始和结束"""
        rows = [r[:8] for r in rows]
        reads = [r for r in rows if r[0] in ["READ", "0"]]
        writes = [r for r in rows if r[0] in ["WRITE", "1"]]
        result = []
        if reads:
            result.append(reads[0])
        for w in writes[:5]:
            result.append(w)
        if reads:
            result.append(reads[-1])
        return result
        
    def _simplify_markov_rows(self, rows: List[List[str]]) -> List[List[str]]:
        """MARKOV: 精简重复序列，只保留值变化时的记录"""
        rows = [r[:8] for r in rows]
        result = []
        last_val = None
        sorted_rows = sorted(rows, key=lambda x: int(x[1]) if len(x) > 1 else 0)
        
        for r in sorted_rows:
            try:
                val = int(r[3], 16)
            except:
                val = None
            is_write = r[0] in ["WRITE", "1"]
            if val != last_val or is_write or len(result) == 0:
                result.append(r)
                last_val = val
        return result
        
    def write_simplification_report(self, stats: Dict, output_path: str) -> bool:
        """写精简报告"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("数据精简报告\n")
                f.write("=" * 60 + "\n\n")
                
                f.write(f"原始记录数: {stats['original_records']}\n")
                f.write(f"精简后记录数: {stats['simplified_records']}\n")
                f.write(f"压缩比: {stats['compression_ratio']}\n\n")
                
                f.write("按类别精简统计:\n")
                for cls, count in stats['by_class'].items():
                    f.write(f"  {cls}: {count} 条\n")
                    
            return True
            
        except Exception as e:
            logger.error(f"Error writing report: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description="寄存器分类与精简算法"
    )
    parser.add_argument(
        'input',
        nargs='?',
        help='输入TSV文件路径'
    )
    parser.add_argument(
        '-d', '--input-dir',
        help='输入目录'
    )
    parser.add_argument(
        '-o', '--output-dir',
        help='输出目录'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='详细输出'
    )
    parser.add_argument(
        '-r', '--report',
        action='store_true',
        help='生成精简报告'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # 处理输入
    input_files = []
    
    if args.input:
        input_files.append(args.input)
    elif args.input_dir:
        for root, dirs, files in os.walk(args.input_dir):
            for f in files:
                if f.endswith('recording.tsv'):
                    input_files.append(os.path.join(root, f))
    else:
        logger.error("请指定输入文件或输入目录")
        return 1
        
    if not input_files:
        logger.error("未找到recording.tsv文件")
        return 1
        
    logger.info(f"将处理 {len(input_files)} 个文件")
    
    for input_path in input_files:
        logger.info(f"\n{'='*60}")
        logger.info(f"处理: {input_path}")
        logger.info(f"{'='*60}")
        
        classifier = RegisterClassifier()
        
        if not classifier.parse_tsv(input_path):
            continue
            
        classifications = classifier.classify_all()
        
        # 显示分类报告
        print("\n寄存器分类:")
        class_stats = defaultdict(list)
        for addr, cls in classifications.items():
            class_stats[cls].append(addr)
            
        for cls in RegisterClass:
            addrs = class_stats[cls]
            print(f"  {cls.value}: {len(addrs)} 个")
            
        # 精简数据
        writer = SimplifiedTSVWriter(classifier)
        success, output_path, stats = writer.write_simplified_tsv(
            input_path,
            args.output_dir
        )
        
        if success:
            print(f"\n精简统计:")
            print(f"  原始记录: {stats['original_records']}")
            print(f"  精简后: {stats['simplified_records']}")
            print(f"  压缩比: {stats['compression_ratio']}")
            print(f"\n输出文件: {output_path}")
            
            if args.report:
                report_path = output_path.replace('_simplified.tsv', '_simplification_report.txt')
                writer.write_simplification_report(stats, report_path)
                print(f"报告文件: {report_path}")
                
    logger.info("\n处理完成!")
    return 0


if __name__ == "__main__":
    exit(main())
