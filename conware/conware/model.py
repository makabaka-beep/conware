# Native
import logging
import os
import pickle
import sys
import traceback

# Conware
import conware.globals as G

from conware.ground_truth.arduino_due import PeripheralMemoryMap
from conware.interrupts import Interrupter
from conware.tools.logger import LogReader
from conware.models.simple_storage import SimpleStorageModel
from conware.peripheral_model import PeripheralModel

logger = logging.getLogger(__name__)

peripheral_memory_map = PeripheralMemoryMap()


class ConwareModel:
    def __init__(self, name=None, address=None, size=None,
                 filename=None, **kwargs):
        self.peripherals = []
        self.model_per_address = {}
        self.model_per_interrupt = {}
        self.peripheral_clusters = {}
        self.log_per_cluster = {}
        self.accessed_addresses = set()
        self.stats = {
            'missed_reads': 0,
            'missed_writes': 0,
            'total_reads': 0,
            'total_writes': 0,
            'interrupts': 0
        }

        # 初始化中断映射（简化写法）
        self.interrupt_map = kwargs.get('interrupt_map', {})
        # 初始化主机信息
        self.host = kwargs.get('host', None)

        # 从磁盘加载模型（使用上下文管理器，避免文件句柄泄漏）
        if filename is not None:
            try:
                with open(filename, "rb") as f:
                    self.__dict__ = pickle.load(f)
                # 重置所有外设状态
                for p in self.peripherals:
                    p.reset()
            except FileNotFoundError:
                logger.error(f"Model file {filename} not found!")
            except pickle.UnpicklingError:
                logger.error(f"Corrupted model file {filename}!")

        # 兜底：确保 interrupt_map 存在
        if "interrupt_map" not in self.__dict__:
            self.interrupt_map = {}

    def __del__(self):
        self.shutdown()

    def __contains__(self, peripheral):
        """ Check to see if the given peripheral is in this model """
        return peripheral in self.peripherals

    def get_runtime_stats(self):
        for p in self.peripherals:
            self.stats[p.name] = p.stats
        return self.stats

    def add_peripheral(self, peripheral):
        """ Add a peripiheral to our list"""
        self.peripherals.append(peripheral)
        for addr in peripheral.addresses:
            self.model_per_address[int(addr)] = peripheral  # 强制转整数

    def shutdown(self):
        pass

    def save(self, filename):
        """ Save our model to the specified directory """
        model_file = os.path.join(filename)
        logger.info("Saving model to %s", model_file)
        # 使用上下文管理器，自动关闭文件
        try:
            with open(model_file, "wb+") as f:
                pickle.dump(self.__dict__, f)
        except IOError as e:
            logger.error(f"Failed to save model: {e}")

    def _safe_hex_to_int(self, hex_str):
        """安全的十六进制字符串转整数（兼容浮点格式）"""
        try:
            # 清理字符串：去除空格、小数点及后续内容
            clean_str = hex_str.strip().split('.')[0]
            # 处理空字符串
            if not clean_str:
                return 0
            # 先尝试直接转十六进制整数
            return int(clean_str, 16)
        except ValueError:
            # 若失败，尝试转十进制浮点再转整数
            try:
                return int(float(hex_str))
            except:
                logger.error(f"Failed to convert {hex_str} to integer")
                return 0

    def train(self, filename):
        """
        Train our model, potentially using a specific training model
        :return: bool - 训练是否成功
        """
        logger.info("Training peripheral model (%s)" % filename)

        try:
            l = LogReader(filename)
        except FileNotFoundError:
            logger.error(f"Log file {filename} not found!")
            return False

        try:
            # 跳过日志头部（处理空日志异常）
            next(l)
        except StopIteration:
            logger.error("Log file is empty!")
            l.close()
            return False
        except Exception as e:
            logger.error(f"Error reading log header: {e}")
            traceback.print_exc()
            l.close()
            return False

        # Step 0: 获取所有被访问的地址
        try:
            for line in l:
                try:
                    # ['Operation', 'Seqn', 'Address', 'Value', 'Value (Model)',
                    # 'PC', 'Size', 'Timestamp', 'Model']
                    op, seqn, addr, val, val_model, pc, size, timestamp, model = line
                except ValueError:
                    logger.warning("Weird line: " + repr(line))
                    continue
                if op in ["0", "1", "READ", "WRITE"]:
                    # 安全转换地址为整数
                    addr_int = self._safe_hex_to_int(addr)
                    self.accessed_addresses.add(addr_int)
        except Exception as e:
            logger.error(f"Error processing log addresses: {e}")
            traceback.print_exc()
        finally:
            l.close()

        if len(self.accessed_addresses) == 0:
            logger.error("No memory accesses were recorded!")
            return False

        # Step 1: 将地址划分到对应外设
        used_peripherals = set()
        for addr in self.accessed_addresses:
            peripheral = peripheral_memory_map.get_peripheral(int(addr))  # 强制转整数
            if peripheral and peripheral[0] not in used_peripherals:
                used_peripherals.add(peripheral[0])

        # 为每个外设创建模型并关联地址
        for periph_name in peripheral_memory_map.peripheral_memory:
            if periph_name not in used_peripherals:
                continue
            logger.info("Packing peripheral %s" % periph_name)

            try:
                addrs_range = peripheral_memory_map.peripheral_memory[periph_name]
                # 强制转换地址范围为整数
                start_addr = int(addrs_range[0])
                end_addr = int(addrs_range[1])
                addrs = set(range(start_addr, end_addr))
                peripheral = PeripheralModel(addrs, name=periph_name)
                self.peripherals.append(peripheral)
                for addr in addrs:
                    self.model_per_address[int(addr)] = peripheral  # 强制转整数

                # 关联外设中断
                if periph_name in peripheral_memory_map.interrupt_map:
                    for irq in peripheral_memory_map.interrupt_map[periph_name]:
                        self.model_per_interrupt[int(irq)] = peripheral  # 强制转整数
            except Exception as e:
                logger.error(f"Error creating peripheral {periph_name}: {e}")
                traceback.print_exc()
                continue

        # Step 2: 解析日志，训练外设访问行为
        try:
            l = LogReader(filename)
        except FileNotFoundError:
            logger.error(f"Log file {filename} not found!")
            return False

        try:
            next(l)  # 跳过头部
        except StopIteration:
            logger.error("Log file is empty after re-opening!")
            l.close()
            return False
        except Exception as e:
            logger.error(f"Error reading log header again: {e}")
            traceback.print_exc()
            l.close()
            return False

        last_write_addr = None  # 记录最后一次写地址，用于关联中断
        try:
            for line in l:
                try:
                    op, seqn, addr, val, val_model, pc, size, timestamp, model = line
                except ValueError:
                    logger.warning("Weird line: " + repr(line))
                    continue

                # 安全转换所有数值为整数
                addr_int = self._safe_hex_to_int(addr)
                val_int = self._safe_hex_to_int(val)
                pc_int = self._safe_hex_to_int(pc)
                size_int = int(size) if size.strip() else 0

                # 处理写操作
                if op in ["1", "WRITE"]:
                    if addr_int in self.model_per_address:
                        self.model_per_address[addr_int].train_write(addr_int, val_int)
                    last_write_addr = addr_int
                # 处理读操作
                elif op in ["0", "READ"]:
                    if addr_int in self.model_per_address:
                        self.model_per_address[addr_int].train_read(
                            addr_int, val_int, pc_int, size_int, timestamp)
                # 处理中断（修复未定义的 irq 变量）
                elif op in ["2", "INTERRUPT"]:
                    irq_val = int(val_int)  # 强制转整数
                    # 跳过已映射的中断
                    if irq_val in self.interrupt_map:
                        logger.debug("Found mapped interrupt (0x%08X), skipping" % irq_val)
                        continue
                    # 关联到已知外设的中断
                    elif irq_val in self.model_per_interrupt:
                        logger.info("Trained interrupt (%s)" % str(irq_val))
                        self.model_per_interrupt[irq_val].train_interrupt(irq_val, timestamp)
                    # 回退到最后一次写地址
                    elif last_write_addr is not None:
                        logger.warning(
                            f"Got interrupt {irq_val} and it is not mapped to a peripheral! Fallback to last write address")
                        self.model_per_address[last_write_addr].train_interrupt(irq_val, timestamp)
                    else:
                        logger.warning(
                            f"Got interrupt {irq_val} but no peripheral mapping and no last write address!")
                else:
                    logger.error("Saw an unrecognized operation (%s)!" % op)
        except Exception as e:
            logger.error(f"Error training model with log data: {e}")
            traceback.print_exc()
        finally:
            l.close()

        # 完成外设训练
        try:
            for idx, peripheral in enumerate(self.peripherals):
                peripheral.train()
                self.peripherals[idx] = peripheral
        except Exception as e:
            logger.error(f"Error finalizing peripheral training: {e}")
            traceback.print_exc()
            return False

        return True

    def get_model(self, address):
        """
        return the name of the model that is controlling the address
        :param address:
        :return: str or None
        """
        addr_int = int(address)  # 强制转整数
        if addr_int in self.model_per_address:
            return repr(self.model_per_address[addr_int])
        else:
            return None

    def get_interrupts(self, address):
        """"
            Return a dictionary of all of the interrupts in the current state, with their counts
            :param address: Address that return the interrupts for the current state for
            :return: dict
        """
        addr_int = int(address)  # 强制转整数
        if addr_int in self.model_per_address:
            if isinstance(self.model_per_address[addr_int], SimpleStorageModel):
                return {}
            return self.model_per_address[addr_int].get_interrupts()
        else:
            return {}

    def write_memory(self, address, size, value):
        """
        On a write, we need to check if this value affects any other address
        return values and update the state accordingly

        :param address:
        :param size:
        :param value:
        :return: bool
        """
        try:
            # 强制转换所有参数为整数
            address = int(address)
            size = int(size)
            value = int(value)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid integer values - addr:{address}, size:{size}, val:{value}, error:{e}")
            self.stats['missed_writes'] += 1
            return False

        logger.debug("Write 0x%08X %d 0x%08X" % (address, size, value))
        self.stats['total_writes'] += 1

        if address not in self.model_per_address:
            self.stats['missed_writes'] += 1
            logger.debug("No model found for 0x%08X, using SimpleStorageModel...", address)
            self.model_per_address[address] = SimpleStorageModel()
            rtn = True
        else:
            try:
                if isinstance(self.model_per_address[address], PeripheralModel):
                    rtn = self.model_per_address[address].write(address, size, value)
                else:
                    rtn = self.model_per_address[address].write(value)
            except Exception as e:
                logger.error(f"Error writing to address 0x%08X: {e}" % address)
                traceback.print_exc()
                self.stats['missed_writes'] += 1
                return False

        # 触发中断（优化日志打印）
        if (address, value) in self.interrupt_map:
            self.stats['interrupts'] += 1
            logger.info("Injecting interrupt!")
            logger.info(f"Host: {self.host}")
            irq_num = int(self.interrupt_map[(address, value)])  # 强制转整数
            try:
                interrupter = Interrupter(irq_num, self.host, count=1)
                interrupter.start()
            except Exception as e:
                logger.error(f"Error injecting interrupt {irq_num}: {e}")
                traceback.print_exc()

        return rtn

    def read_memory(self, address, size):
        """
        On a read, we will use our model to return an appropriate value

        :param address:
        :param size:
        :return: int
        """
        try:
            # 强制转换所有参数为整数
            address = int(address)
            size = int(size)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid integer values - addr:{address}, size:{size}, error:{e}")
            self.stats['missed_reads'] += 1
            return 0

        logger.debug("Read 0x%08X %d" % (address, size))
        self.stats['total_reads'] += 1

        # 修复 Python 2 print 语法 + 移除冗余地址检查
        if address not in self.model_per_address:
            self.stats['missed_reads'] += 1
            logger.debug("No model found for 0x%08X, using SimpleStorageModel...", address)
            self.model_per_address[address] = SimpleStorageModel()
            print(f"No model found for 0x{address:08X}, using SimpleStorageModel...")

        # 调用对应模型的读方法
        try:
            peripheral = self.model_per_address[address]
            if isinstance(peripheral, PeripheralModel):
                return int(peripheral.read(address, size))  # 强制转整数
            else:
                return int(peripheral.read())  # 强制转整数
        except Exception as e:
            logger.error(f"Error reading from address 0x%08X: {e}" % address)
            traceback.print_exc()
            self.stats['missed_reads'] += 1
            return 0

    def get_peripherals(self):
        return self.peripherals
