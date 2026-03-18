#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conware 外围设备模型工具
用于加载和使用 conware 模型
Python 3 适配版本
"""

import sys
import os
import pickle
import datetime  # 显式导入datetime，Python3更规范

print("="*70)
print("🎯 Conware 外围设备模型工具 (Python 3 版本)")
print("="*70)

# 添加 conware 到 Python 路径
conware_path = "/home/makabaka/conware/conware"
if os.path.exists(conware_path):
    sys.path.insert(0, conware_path)

# 加载模型（支持命令行传参指定模型文件，兼容原有默认值）
model_file = "model.pickle"
# 如果命令行传入了模型文件路径，则使用传入的路径
if len(sys.argv) > 1:
    model_file = sys.argv[1]

print("📁 加载模型文件: " + model_file)

try:
    # Python3 读取pickle时指定编码，兼容Python2保存的pickle文件
    with open(model_file, 'rb') as f:
        # 解决Python2 pickle在Python3中加载的编码问题
        conware_data = pickle.load(f, encoding='latin1')
    
    print("✅ 模型加载成功!")
    print("模型类型: 外围设备仿真字典")
    
except FileNotFoundError:
    print(f"❌ 加载失败: 模型文件 '{model_file}' 不存在")
    sys.exit(1)
except Exception as e:
    print(f"❌ 加载失败: {str(e)}")
    sys.exit(1)

class ConwareModelExplorer:
    """Conware 模型探索器 (Python 3)"""
    
    def __init__(self, data):
        self.data = data
        self.model_per_address = data.get('model_per_address', {})
        self.peripherals = data.get('peripherals', [])
        self.stats = data.get('stats', {})
        
    def show_summary(self):
        """显示模型摘要"""
        print("\n" + "="*60)
        print("📊 模型摘要")
        print("="*60)
        
        print("📈 统计信息:")
        for key, value in self.stats.items():
            print(f"  {key:15}: {value}")
        
        print("\n🔧 模型数量:")
        print(f"  地址模型数量: {len(self.model_per_address)}")
        print(f"  外设数量: {len(self.peripherals)}")
        
        accessed_addrs = self.data.get('accessed_addresses', set())
        print(f"\n🌐 访问过的地址: {len(accessed_addrs)}")
        
        # 显示外设列表
        print("\n📋 外设列表:")
        for i, peripheral in enumerate(self.peripherals, 1):
            if hasattr(peripheral, 'name'):
                addr_count = len(peripheral.addresses) if hasattr(peripheral, 'addresses') else '?'
                print(f"  {i:2}. {peripheral.name} ({addr_count} 个地址)")
    
    def explore_peripheral(self):
        """探索特定外设"""
        if not self.peripherals:
            print("❌ 没有外设数据")
            return
        
        print("\n" + "="*60)
        print("🔍 探索外设")
        print("="*60)
        
        print("可用的外设:")
        for i, peripheral in enumerate(self.peripherals, 1):
            if hasattr(peripheral, 'name'):
                print(f"  {i:2}. {peripheral.name}")
        
        while True:
            # Python3 使用 input() 替代 raw_input()
            choice = input("\n选择外设编号 (或输入 'q' 返回): ").strip()
            
            if choice.lower() == 'q':
                break
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(self.peripherals):
                    peripheral = self.peripherals[idx]
                    self.show_peripheral_details(peripheral)
                else:
                    print("❌ 编号无效")
            except ValueError:  # 明确捕获数值转换错误，Python3更规范
                print("❌ 输入无效，请输入数字或 'q'")
    
    def show_peripheral_details(self, peripheral):
        """显示外设详细信息"""
        peripheral_name = peripheral.name if hasattr(peripheral, 'name') else "未知"
        print("\n" + "-"*50)
        print(f"🔬 外设详情: {peripheral_name}")
        print("-"*50)
        
        # 显示属性
        print("📋 属性:")
        for attr in dir(peripheral):
            if not attr.startswith('_'):
                try:
                    value = getattr(peripheral, attr)
                    if not callable(value):
                        value_str = str(value)
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                        print(f"  {attr:20}: {value_str}")
                except Exception as e:  # 捕获具体异常，避免程序崩溃
                    print(f"  {attr:20}: (无法访问: {str(e)[:20]})")
        
        # 显示状态信息
        if hasattr(peripheral, 'current_state'):
            print(f"\n🎯 当前状态: {peripheral.current_state}")
        
        if hasattr(peripheral, 'stats'):
            print("\n📈 统计:")
            for key, value in peripheral.stats.items():
                print(f"  {key:15}: {value}")
        
        if hasattr(peripheral, 'addresses'):
            addrs = list(peripheral.addresses)
            print(f"\n📌 地址 ({len(addrs)})个:")
            for i, addr in enumerate(addrs[:10], 1):
                print(f"  {i:2}. 0x{addr:08X}")  # Python3 f-string 格式化更简洁
            if len(addrs) > 10:
                print(f"  ... 还有 {len(addrs) - 10} 个地址")
    
    def query_address(self):
        """查询地址对应的模型"""
        print("\n" + "="*60)
        print("📍 地址查询")
        print("="*60)
        
        while True:
            addr_input = input("\n输入地址 (十六进制, 如 0x400e081c 或输入 'q' 返回): ").strip()
            
            if addr_input.lower() == 'q':
                break
            
            try:
                # 转换地址（兼容十进制/十六进制输入）
                if addr_input.startswith(('0x', '0X')):
                    addr = int(addr_input, 16)
                else:
                    addr = int(addr_input)
                
                # 查找地址
                if addr in self.model_per_address:
                    model = self.model_per_address[addr]
                    self.show_address_model(addr, model)
                else:
                    print(f"❌ 地址 0x{addr:08X} 不在模型中")
                    
            except ValueError:
                print("❌ 地址格式无效，请输入有效的十六进制(0x开头)或十进制数字")
            except Exception as e:
                print(f"❌ 查询失败: {str(e)}")
    
    def show_address_model(self, address, model):
        """显示地址模型详情"""
        print("\n" + "-"*50)
        print(f"🔧 地址模型: 0x{address:08X}")
        print("-"*50)
        
        print(f"模型类型: {type(model).__name__}")
        
        if hasattr(model, '__class__'):
            print(f"类名: {model.__class__.__name__}")
        
        # 显示属性
        print("\n📋 属性:")
        # 过滤属性并排序，更易读
        attrs = [
            a for a in dir(model) 
            if not a.startswith('_') and not callable(getattr(model, a))
        ]
        # 只显示前15个属性，避免输出过长
        for attr in sorted(attrs)[:15]:  
            try:
                value = getattr(model, attr)
                value_str = str(value)
                if len(value_str) > 40:
                    value_str = value_str[:37] + "..."
                print(f"  {attr:20}: {value_str}")
            except Exception as e:
                print(f"  {attr:20}: (无法访问: {str(e)[:20]})")
        
        # 显示方法
        methods = [
            a for a in dir(model) 
            if not a.startswith('_') and callable(getattr(model, a))
        ]
        if methods:
            print(f"\n🛠️  可用方法 ({len(methods)}个):")
            for i, method in enumerate(sorted(methods)[:10], 1):
                print(f"  {i:2}. {method}()")
            if len(methods) > 10:
                print(f"  ... 还有 {len(methods) - 10} 个方法")
    
    def save_report(self):
        """保存模型报告"""
        report_file = "conware_model_report.txt"
        try:
            # Python3 写入文件时指定编码，避免中文乱码
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write("Conware 外围设备模型报告\n")
                f.write("="*70 + "\n\n")
                
                f.write(f"模型文件: {model_file}\n")
                f.write(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("📊 统计信息:\n")
                for key, value in self.stats.items():
                    f.write(f"  {key:15}: {value}\n")
                
                f.write("\n🔧 模型数量:\n")
                f.write(f"  地址模型数量: {len(self.model_per_address)}\n")
                f.write(f"  外设数量: {len(self.peripherals)}\n\n")
                
                f.write("📋 外设列表:\n")
                for i, peripheral in enumerate(self.peripherals, 1):
                    if hasattr(peripheral, 'name'):
                        addr_count = len(peripheral.addresses) if hasattr(peripheral, 'addresses') else 0
                        f.write(f"  {i:2}. {peripheral.name} ({addr_count} 个地址)\n")
            
            print(f"✅ 报告已保存到: {report_file}")
            
        except PermissionError:
            print(f"❌ 保存报告失败: 没有写入权限")
        except Exception as e:
            print(f"❌ 保存报告失败: {str(e)}")
    
    def run(self):
        """运行主菜单"""
        while True:
            print("\n" + "="*60)
            print("📋 主菜单")
            print("="*60)
            print("1. 📊 查看模型摘要")
            print("2. 🔍 探索外设")
            print("3. 📍 查询地址")
            print("4. 💾 保存报告")
            print("5. 🚪 退出")
            print("="*60)
            
            choice = input("请选择 (1-5): ").strip()
            
            if choice == '1':
                self.show_summary()
            elif choice == '2':
                self.explore_peripheral()
            elif choice == '3':
                self.query_address()
            elif choice == '4':
                self.save_report()
            elif choice == '5':
                print("\n👋 再见!")
                break
            else:
                print("❌ 无效选择，请输入 1-5 之间的数字")

# 运行工具
if __name__ == "__main__":
    try:
        explorer = ConwareModelExplorer(conware_data)
        explorer.run()
    except KeyboardInterrupt:  # 处理Ctrl+C中断
        print("\n\n⚠️  用户中断程序，退出中...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 程序运行出错: {str(e)}")
        sys.exit(1)
