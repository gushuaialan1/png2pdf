"""
图片分割模块

包含两种分割策略：
- BasicSplitter: 基础颜色检测分割（原有逻辑）
- TableSplitter: 表格感知分割（新增）
"""

from PIL import Image
import numpy as np
from abc import ABC, abstractmethod

# A4尺寸（300dpi）
A4_WIDTH = 2480
A4_HEIGHT = 3508


class BaseSplitter(ABC):
    """分割器基类"""
    
    def __init__(self):
        self.search_range = 100  # 默认搜索范围
    
    @abstractmethod
    def find_text_mask(self, image) -> np.ndarray:
        """获取文字区域掩码"""
        pass
    
    def calculate_target_height(self, image_width: int) -> int:
        """根据图片宽度计算目标高度（A4比例）"""
        return int(image_width / (A4_WIDTH / A4_HEIGHT))
    
    def find_split_points(self, image: Image.Image) -> list:
        """找到合适的分割点"""
        width, height = image.size
        
        target_height = self.calculate_target_height(width)
        text_mask = self.find_text_mask(image)
        page_count = max(1, int(np.ceil(height / target_height)))
        
        split_points = []
        prev_split = 0
        
        for i in range(page_count):
            if i == page_count - 1:
                split_points.append(height)
                break
                
            ideal_split = (i + 1) * target_height
            best_split = self._find_best_split_in_range(
                ideal_split, text_mask, height, prev_split, target_height
            )
            split_points.append(best_split)
            prev_split = best_split
        
        # 去重并排序
        unique_splits = []
        seen = set()
        for point in split_points:
            point_int = int(point)
            if point_int not in seen:
                seen.add(point_int)
                unique_splits.append(point_int)
        
        if unique_splits[-1] != height:
            unique_splits.append(height)
        
        return sorted(unique_splits)
    
    def _find_best_split_in_range(self, ideal_split: int, text_mask: np.ndarray, 
                                   height: int, prev_split: int = 0, target_height: int = 3508) -> int:
        """在搜索范围内寻找最佳分割点"""
        search_start = max(0, ideal_split - self.search_range)
        search_end = min(height, ideal_split + self.search_range)
        
        best_split = None
        max_blank_height = 0
        
        y = search_start
        while y < search_end:
            # 检查当前位置是否是空白
            if not text_mask[y]:
                blank_start = y
                while blank_start > search_start and not text_mask[blank_start - 1]:
                    blank_start -= 1
                
                blank_end = y
                while blank_end < search_end - 1 and not text_mask[blank_end + 1]:
                    blank_end += 1
                
                blank_height = blank_end - blank_start
                distance_to_ideal = abs(y - ideal_split)
                
                if (blank_height > max_blank_height or 
                    (blank_height >= 20 and best_split is not None and 
                     distance_to_ideal < abs(best_split - ideal_split))):
                    max_blank_height = blank_height
                    best_split = y
                
                y = blank_end + 1
            else:
                y += 1
        
        return best_split if best_split is not None else ideal_split


class BasicSplitter(BaseSplitter):
    """基础分割器"""
    
    def __init__(self):
        super().__init__()
        self.search_range = 100
    
    def find_text_mask(self, image: Image.Image) -> np.ndarray:
        """通过颜色识别文字区域"""
        img_rgb = image.convert('RGB')
        img_array = np.array(img_rgb)
        background_color = np.median(img_array[0:20], axis=0)
        text_mask = np.zeros((img_array.shape[0],), dtype=bool)
        
        for y in range(img_array.shape[0]):
            row = img_array[y]
            
            black_text = np.all(row < [50, 50, 50], axis=1)
            red_text = (row[:, 0] > 150) & (row[:, 1] < 50) & (row[:, 2] < 50)
            
            # 3. 与背景色的差异
            color_diff = np.abs(row - background_color)
            diff_text = np.any(color_diff > 30, axis=1)
            
            # 如果这一行包含任何文字像素
            if np.any(black_text | red_text | diff_text):
                text_mask[y] = True
        
        return text_mask


class TableSplitter(BaseSplitter):
    """表格感知分割器 - 识别表格结构，避免在表格中间切割"""
    
    def __init__(self):
        super().__init__()
        self.search_range = 300
        self.vertical_line_threshold = 0.15
        self.table_regions = []
    
    def _detect_table_regions(self, image: Image.Image) -> list:
        """使用形态学操作+投影算法检测表格区域"""
        import cv2
        
        img_array = np.array(image.convert('RGB'))
        img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        height, width = img_cv.shape[:2]
        
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (width//20, 1))
        horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_h)
        row_projection = np.sum(horizontal, axis=1) / 255
        
        threshold = width / 10
        has_line = row_projection > threshold
        
        table_regions = []
        in_table = False
        region_start = 0
        line_count = 0
        gap_count = 0
        
        for y in range(height):
            if has_line[y]:
                if not in_table:
                    region_start = y
                    in_table = True
                    line_count = 1
                    gap_count = 0
                else:
                    line_count += 1
                    gap_count = 0
            else:
                if in_table:
                    gap_count += 1
                    if gap_count > 100:
                        if line_count >= 3:
                            actual_start = max(0, region_start - 20)
                            actual_end = min(height - 1, y - gap_count + 20)
                            table_regions.append((actual_start, actual_end))
                        in_table = False
                        line_count = 0
                        gap_count = 0
        
        if in_table and line_count >= 3:
            actual_start = max(0, region_start - 20)
            actual_end = min(height - 1, height)
            table_regions.append((actual_start, actual_end))
        
        return table_regions
    
    def find_text_mask(self, image: Image.Image) -> np.ndarray:
        """通过颜色识别文字区域，同时检测表格区域"""
        # 转换图片为RGB模式
        img_rgb = image.convert('RGB')
        img_array = np.array(img_rgb)
        
        # 获取背景色（使用图片边缘的颜色中值）
        background_color = np.median(img_array[0:20], axis=0)
        
        # 创建掩码来标记文字区域
        text_mask = np.zeros((img_array.shape[0],), dtype=bool)
        
        # 检测表格区域
        self.table_regions = self._detect_table_regions(image)
        
        # 对每一行进行分析
        for y in range(img_array.shape[0]):
            row = img_array[y]
            
            # 检查每个像素是否是文字
            # 1. 黑色文字/线条 (RGB接近0,0,0)
            black_pixels = np.all(row < [50, 50, 50], axis=1)
            
            # 2. 红色文字 (R明显大于G和B)
            red_text = (row[:, 0] > 150) & (row[:, 1] < 50) & (row[:, 2] < 50)
            
            # 3. 与背景色的差异（包括彩色表头）
            color_diff = np.abs(row - background_color)
            diff_text = np.any(color_diff > 30, axis=1)
            
            # 如果这一行包含任何文字像素或颜色差异
            if np.any(black_pixels | red_text | diff_text):
                text_mask[y] = True
        
        # 将所有表格区域标记为"有内容"（不可分割）
        for start_y, end_y in self.table_regions:
            text_mask[start_y:end_y+1] = True
        
        return text_mask
    
    def _find_best_split_in_range(self, ideal_split: int, text_mask: np.ndarray,
                                   height: int) -> int:
        """在搜索范围内寻找最佳分割点，避免在表格内部分割"""
    def _find_best_split_in_range(self, ideal_split: int, text_mask: np.ndarray, 
                                   height: int, prev_split: int = 0, target_height: int = 3508) -> int:
        """在搜索范围内寻找最佳分割点，确保页面高度不超过A4的110%"""
        search_start = max(0, ideal_split - self.search_range)
        search_end = min(height, ideal_split + self.search_range)
        
        # 计算最大允许的页面高度（A4的110%）
        max_page_height = int(target_height * 1.10)
        
        best_split = None
        max_blank_height = 0
        
        y = search_start
        while y < search_end:
            # 检查当前位置是否是空白
            if not text_mask[y]:
                # 找到空白行，向前后扩展找到完整的空白区域
                blank_start = y
                while blank_start > search_start and not text_mask[blank_start - 1]:
                    blank_start -= 1
                
                blank_end = y
                while blank_end < search_end - 1 and not text_mask[blank_end + 1]:
                    blank_end += 1
                
                blank_height = blank_end - blank_start
                distance_to_ideal = abs(y - ideal_split)
                
                if (blank_height > max_blank_height or 
                    (blank_height >= 20 and best_split is not None and 
                     distance_to_ideal < abs(best_split - ideal_split))):
                    max_blank_height = blank_height
                    best_split = y
                
                y = blank_end + 1
            else:
                y += 1
        
        # 如果找到了足够大的空白区域，直接使用
        if best_split is not None and max_blank_height >= 10:
            return best_split
        
        # 如果没找到合适的空白区域，检查理想分割点是否在表格内部
        # 策略：优先选择表格下边界，但必须确保页面高度不超过110%
        for start_y, end_y in self.table_regions:
            if start_y <= ideal_split <= end_y:
                # 理想分割点在这个表格内部
                
                # 计算如果选择下边界，页面高度是多少
                page_height_if_end = end_y - prev_split
                
                # 如果下边界不会导致页面过高（<=110%），优先选择下边界
                if page_height_if_end <= max_page_height:

                    return end_y
                else:
                    # 下边界太远，需要选择上边界
                    # 但不能直接选择表格上边界，要向上回溯找空白区域（标题之前）
                    
                    # 向上搜索300像素，找标题之前的空白区域
                    search_up_start = max(prev_split + 100, start_y - 300)
                    search_up_end = start_y
                    
                    best_gap = None
                    max_gap_size = 0
                    
                    # 向上搜索空白区域
                    for y in range(search_up_end - 1, search_up_start, -1):
                        if not text_mask[y]:
                            # 找到空白行，扩展找到完整空白区域
                            gap_end = y
                            gap_start = y
                            while gap_start > search_up_start and not text_mask[gap_start - 1]:
                                gap_start -= 1
                            
                            gap_size = gap_end - gap_start
                            if gap_size > max_gap_size:
                                max_gap_size = gap_size
                                best_gap = gap_start
                    
                    if best_gap is not None and max_gap_size >= 10:
                        page_height_final = best_gap - prev_split

                        return best_gap
                    else:
                        # 没找到合适的空白区域，只能选择表格上边界
                        page_height_if_start = start_y - prev_split

                        return start_y
        
        # 如果理想分割点不在表格内部，尝试在搜索范围内找表格边界
        best_boundary = None
        min_distance = float('inf')
        
        for start_y, end_y in self.table_regions:
            # 检查表格上边界
            if search_start <= start_y <= search_end:
                distance = abs(start_y - ideal_split)
                if distance < min_distance:
                    min_distance = distance
                    best_boundary = start_y
            
            # 检查表格下边界
            if search_start <= end_y <= search_end:
                # 同样检查高度限制
                page_height_if_end = end_y - prev_split
                if page_height_if_end <= max_page_height:
                    distance = abs(end_y - ideal_split)
                    if distance < min_distance:
                        min_distance = distance
                        best_boundary = end_y
        
        if best_boundary is not None:
            return best_boundary
        
        # 如果都没找到，返回已找到的最佳位置或理想位置
        return best_split if best_split is not None else ideal_split


def get_splitter(has_table: bool = False) -> BaseSplitter:
    """
    获取分割器实例
    
    Args:
        has_table: 是否包含表格
        
    Returns:
        对应的分割器实例
    """
    if has_table:
        return TableSplitter()
    return BasicSplitter()
