import csv
import logging
import sys

logger = logging.getLogger(__name__)


class PretenderLog:
    HEADER = [
        'Operation', 'Seqn', 'Address', 'Value', 'Value (Model)',
        'PC', 'Size', 'Timestamp', 'Model'
    ]

    def __init__(self):
        pass


class LogWriter(PretenderLog):
    """
    Write CSV logs in our standard format
    """

    def __init__(self, filename, buffer=True):
        self.csvfile = None
        try:
            if not buffer:
                # Python 3 中 open 无 bufsize=0 的文本模式，用 binary 模式
                self.csvfile = open(filename, 'wb', 0)  # 0 for no buffer
            else:
                self.csvfile = open(filename, 'w', newline='', encoding='utf-8')
            # 兼容 Python 2/3 的 csv 写入
            if sys.version_info >= (3, 0):
                self.writer = csv.writer(
                    self.csvfile, delimiter='\t',
                    quotechar='|', quoting=csv.QUOTE_MINIMAL
                )
            else:
                self.writer = csv.writer(
                    self.csvfile, delimiter='\t',
                    quotechar='|', quoting=csv.QUOTE_MINIMAL
                )
            self.writer.writerow(self.HEADER)
        except IOError as e:
            logger.error(f"Failed to open log file {filename}: {e}")
            raise

    def write_row(self, row):
        """
        Write a list of values to our log file
        :param row:
        :return:
        """
        if len(row) != len(self.HEADER):
            logger.warning("The row written does not match our format: %s" % repr(self.HEADER))
        try:
            self.writer.writerow(row)
        except Exception as e:
            logger.error(f"Failed to write row {row}: {e}")

    def close(self):
        if self.csvfile:
            self.csvfile.close()


class LogReader(PretenderLog):
    """
        Read CSV logs in our standard format
    """

    def __init__(self, filename):
        self.csvfile = None
        try:
            # Python 3 用 newline='' 保证跨平台换行符处理
            self.csvfile = open(filename, 'r', newline='', encoding='utf-8')
            self.reader = csv.reader(
                self.csvfile, delimiter='\t',
                quotechar='|', quoting=csv.QUOTE_MINIMAL
            )
        except FileNotFoundError:
            logger.error(f"Log file {filename} not found!")
            raise
        except IOError as e:
            logger.error(f"Failed to open log file {filename}: {e}")
            raise

    def __iter__(self):
        return self

    def __next__(self):
        """Python 3 迭代器接口"""
        return self.read_row()

    def next(self):
        """Python 2 迭代器接口"""
        return self.__next__()

    def close(self):
        if self.csvfile:
            self.csvfile.close()

    def read_row(self):
        try:
            return next(self.reader)
        except StopIteration:
            raise
        except Exception as e:
            logger.error(f"Failed to read row: {e}")
            raise
