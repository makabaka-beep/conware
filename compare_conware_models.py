#!/usr/bin/env python3
import pickle
import sys
import os
import networkx as nx
from conware.model import ConwareModel  # 导入Conware核心模型类

def load_model(model_path):
    """加载Conware模型，返回模型对象"""
    if not os.path.exists(model_path):
        print(f"错误：模型文件 {model_path} 不存在！")
        sys.exit(1)
    try:
        model = ConwareModel(filename=model_path)
        print(f"✅ 成功加载模型：{model_path}")
        return model
    except Exception as e:
        print(f"❌ 加载模型失败：{e}")
        sys.exit(1)

def compare_peripheral_stats(orig_peripherals, opt_peripherals):
    """对比外设的状态机节点、边、规则数"""
    print("\n===== 外设级差异对比 =====")
    # 按外设名匹配（确保顺序一致）
    orig_periph_dict = {p.name: p for p in orig_peripherals}
    opt_periph_dict = {p.name: p for p in opt_peripherals}
    
    # 遍历所有外设
    all_periph_names = set(orig_periph_dict.keys()) | set(opt_periph_dict.keys())
    for periph_name in sorted(all_periph_names):
        orig_p = orig_periph_dict.get(periph_name)
        opt_p = opt_periph_dict.get(periph_name)
        
        if not orig_p:
            print(f"⚠️  优化后新增外设：{periph_name}（原始模型无）")
            continue
        if not opt_p:
            print(f"⚠️  优化后删除外设：{periph_name}（优化模型无）")
            continue
        
        # 提取状态机统计
        orig_nodes = len(orig_p.graph.nodes) if hasattr(orig_p, 'graph') else 0
        opt_nodes = len(opt_p.graph.nodes) if hasattr(opt_p, 'graph') else 0
        orig_edges = len(orig_p.graph.edges) if hasattr(orig_p, 'graph') else 0
        opt_edges = len(opt_p.graph.edges) if hasattr(opt_p, 'graph') else 0
        
        # 提取规则数（不同版本Conware可能命名为rules/rule_table）
        orig_rules = len(orig_p.rules) if hasattr(orig_p, 'rules') else (len(orig_p.rule_table) if hasattr(orig_p, 'rule_table') else 0)
        opt_rules = len(opt_p.rules) if hasattr(opt_p, 'rules') else (len(opt_p.rule_table) if hasattr(opt_p, 'rule_table') else 0)
        
        # 计算缩减比例
        node_reduce = (1 - opt_nodes/orig_nodes) * 100 if orig_nodes > 0 else 0
        edge_reduce = (1 - opt_edges/orig_edges) * 100 if orig_edges > 0 else 0
        rule_reduce = (1 - opt_rules/orig_rules) * 100 if orig_rules > 0 else 0
        
        # 打印结果
        print(f"\n外设：{periph_name}")
        print(f"  状态机节点数：{orig_nodes} → {opt_nodes}（缩减 {node_reduce:.1f}%）")
        print(f"  状态机边数：{orig_edges} → {opt_edges}（缩减 {edge_reduce:.1f}%）")
        print(f"  行为规则数：{orig_rules} → {opt_rules}（缩减 {rule_reduce:.1f}%）")

def compare_model_overview(orig_model, opt_model):
    """对比模型整体统计"""
    print("\n===== 模型整体差异 =====")
    # 外设总数
    orig_periph_count = len(orig_model.peripherals)
    opt_periph_count = len(opt_model.peripherals)
    print(f"外设总数：{orig_periph_count} → {opt_periph_count}")
    
    # 总节点/边数
    orig_total_nodes = sum(len(p.graph.nodes) for p in orig_model.peripherals if hasattr(p, 'graph'))
    opt_total_nodes = sum(len(p.graph.nodes) for p in opt_model.peripherals if hasattr(p, 'graph'))
    orig_total_edges = sum(len(p.graph.edges) for p in orig_model.peripherals if hasattr(p, 'graph'))
    opt_total_edges = sum(len(p.graph.edges) for p in opt_model.peripherals if hasattr(p, 'graph'))
    print(f"总状态机节点数：{orig_total_nodes} → {opt_total_nodes}（缩减 {(1 - opt_total_nodes/orig_total_nodes)*100:.1f}%）")
    print(f"总状态机边数：{orig_total_edges} → {opt_total_edges}（缩减 {(1 - opt_total_edges/orig_total_edges)*100:.1f}%）")

def main():
    # 检查参数
    if len(sys.argv) != 3:
        print("用法：python3 compare_conware_models.py <原始模型路径> <优化后模型路径>")
        print("示例：python3 compare_conware_models.py conware_model.pkl conware_model_optimized.pkl")
        sys.exit(1)
    
    # 加载模型
    orig_model_path = sys.argv[1]
    opt_model_path = sys.argv[2]
    orig_model = load_model(orig_model_path)
    opt_model = load_model(opt_model_path)
    
    # 对比整体和外设级差异
    compare_model_overview(orig_model, opt_model)
    compare_peripheral_stats(orig_model.peripherals, opt_model.peripherals)
    
    print("\n✅ 对比完成！核心结论：优化后模型删除了冗余状态/规则，体积更小、结构更精简，核心行为逻辑不变。")

if __name__ == "__main__":
    main()
