from PIL import Image
import numpy as np
from PyPDF2 import PdfWriter
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QIcon
from style import LightBlueStyle  # 导入样式类

# A4尺寸（300dpi）
A4_WIDTH = 2480
A4_HEIGHT = 3508

def find_text_by_color(image):
    """通过颜色识别文字区域"""
    # 转换图片为RGB模式
    img_rgb = image.convert('RGB')
    img_array = np.array(img_rgb)
    
    # 获取背景色（使用图片边缘的颜色中值）
    background_color = np.median(img_array[0:20], axis=0)  # 使用前20行的中值颜色
    
    # 创建掩码来标记文字区域
    text_mask = np.zeros((img_array.shape[0],), dtype=bool)
    
    # 对每一行进行分析
    for y in range(img_array.shape[0]):
        row = img_array[y]
        
        # 检查每个像素是否是文字
        # 1. 黑色文字 (RGB接近0,0,0)
        black_text = np.all(row < [50, 50, 50], axis=1)
        
        # 2. 红色文字 (R明显大于G和B)
        red_text = (row[:, 0] > 150) & (row[:, 1] < 50) & (row[:, 2] < 50)
        
        # 3. 与背景色的差异
        color_diff = np.abs(row - background_color)
        diff_text = np.any(color_diff > 30, axis=1)
        
        # 如果这一行包含任何文字像素
        if np.any(black_text | red_text | diff_text):
            text_mask[y] = True
    
    return text_mask

def calculate_target_height(image_width):
    """根据图片宽度计算目标高度（A4比例）"""
    return int(image_width / (A4_WIDTH / A4_HEIGHT))

def find_split_points(image):
    """找到合适的分割点"""
    width, height = image.size
    
    # 计算目标页面高度（基于A4比例）
    target_height = calculate_target_height(width)
    
    # 获取文字区域掩码
    text_mask = find_text_by_color(image)
    
    # 计算需要分割的页数
    page_count = max(1, int(np.ceil(height / target_height)))
    
    # 寻找分割点
    split_points = []
    for i in range(page_count):
        if i == page_count - 1:
            # 最后一页
            split_points.append(height)
            break
            
        # 计算理想分割位置
        ideal_split = (i + 1) * target_height
        
        # 在理想位置上下100像素范围内寻找最佳空白区域
        search_start = max(0, ideal_split - 100)
        search_end = min(height, ideal_split + 100)
        
        # 在搜索范围内寻找最佳分割点
        best_split = None
        max_blank_height = 0
        
        for y in range(search_start, search_end):
            # 检查当前位置是否是空白
            if not text_mask[y]:
                # 向上寻找连续空白区域的开始
                blank_start = y
                while blank_start > search_start and not text_mask[blank_start - 1]:
                    blank_start -= 1
                
                # 向下寻找连续空白区域的结束
                blank_end = y
                while blank_end < search_end - 1 and not text_mask[blank_end + 1]:
                    blank_end += 1
                
                blank_height = blank_end - blank_start
                
                # 计算与理想分割点的距离
                distance_to_ideal = abs(y - ideal_split)
                
                # 如果这是最大的空白区域，或者空白区域足够大且更接近理想分割点
                if (blank_height > max_blank_height or 
                    (blank_height >= 20 and distance_to_ideal < abs(best_split - ideal_split if best_split else float('inf')))):
                    max_blank_height = blank_height
                    best_split = y
                
                # 跳过已经检查过的空白区域
                y = blank_end
        
        if best_split is not None:
            split_points.append(best_split)
        else:
            # 如果找不到合适的空白区域，就在理想位置分割
            split_points.append(ideal_split)
    
    return split_points

def split_image(image_path, output_dir):
    """分割图片"""
    img = Image.open(image_path)
    
    # 找到分割点
    split_points = find_split_points(img)
    
    # 分割并保存图片
    images = []
    prev_point = 0
    for i, point in enumerate(split_points):
        # 裁剪图片
        cropped = img.crop((0, prev_point, img.width, point))
        
        # 保存图片
        output_path = os.path.join(output_dir, f'page_{i+1}.png')
        cropped.save(output_path)
        images.append(output_path)
        
        prev_point = point
    
    return images

def create_pdf(image_paths, output_pdf):
    """生成PDF"""
    pdf_writer = PdfWriter()
    
    for img_path in image_paths:
        img = Image.open(img_path)
        pdf_path = img_path.replace('.png', '.pdf')
        img.save(pdf_path, "PDF", resolution=300.0)
        pdf_writer.append(pdf_path)
        os.remove(pdf_path)  # 删除临时PDF文件
    
    with open(output_pdf, 'wb') as f:
        pdf_writer.write(f)

class ConversionThread(QThread):
    """后台转换线程"""
    progress = pyqtSignal(int)  # 进度信号
    finished = pyqtSignal(list)  # 完成信号，返回所有生成的PDF路径
    error = pyqtSignal(str)     # 错误信号
    current_file = pyqtSignal(str)  # 当前正在处理的文件名
    
    def __init__(self, input_images, output_path):
        super().__init__()
        self.input_images = input_images
        self.output_path = output_path
        self._is_running = True
        
    def run(self):
        try:
            if not self._is_running:
                return
            
            output_pdfs = []
            total_files = len(self.input_images)
            
            for i, image_path in enumerate(self.input_images):
                if not self._is_running:
                    return
                
                # 发送当前处理的文件名
                self.current_file.emit(os.path.basename(image_path))
                
                # 为每个输入文件创建对应的输出目录和PDF文件名
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_dir = os.path.join(self.output_path, f'output_{base_name}')
                output_pdf = os.path.join(self.output_path, f'{base_name}.pdf')
                
                # 创建输出目录
                os.makedirs(output_dir, exist_ok=True)
                
                # 更新总体进度
                base_progress = (i * 100) // total_files
                self.progress.emit(base_progress)
                
                # 分割图片
                image_paths = split_image(image_path, output_dir)
                
                if not self._is_running:
                    return
                
                # 生成PDF
                create_pdf(image_paths, output_pdf)
                output_pdfs.append(output_pdf)
                
                # 清理临时文件
                for tmp_img in image_paths:
                    try:
                        os.remove(tmp_img)
                    except:
                        pass
                try:
                    os.rmdir(output_dir)
                except:
                    pass
            
            self.progress.emit(100)
            self.finished.emit(output_pdfs)
            
        except Exception as e:
            self.error.emit(f"转换出错：{str(e)}")
            import traceback
            traceback.print_exc()
            
    def stop(self):
        self._is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.conversion_thread = None
        self.input_images = []
        self.output_path = None
        
    def initUI(self):
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), 'ico.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setWindowTitle('图片转PDF工具')
        self.setFixedSize(500, 350)  # 增加窗口高度
        
        # 应用淡蓝色主题
        self.setStyleSheet(LightBlueStyle.get_main_window_style())
        
        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        main_widget.setLayout(layout)
        
        # 拖放区域
        self.drop_area = QLabel('将图片拖放到此处', self)
        self.drop_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_area.setStyleSheet(f'''
            QLabel {{
                background-color: {LightBlueStyle.COLORS['white']};
                border: 2px dashed {LightBlueStyle.COLORS['border']};
                border-radius: 6px;
                padding: 20px;
                font-size: 14px;
                color: {LightBlueStyle.COLORS['text_secondary']};
            }}
        ''')
        self.drop_area.setAcceptDrops(True)
        self.drop_area.setMinimumHeight(200)  # 增加拖放区域高度
        layout.addWidget(self.drop_area, stretch=1)  # 添加stretch参数让拖放区域占据更多空间
        
        # 输出路径选择
        output_widget = QWidget()
        output_layout = QHBoxLayout()
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        output_widget.setLayout(output_layout)
        
        self.output_label = QLabel('输出路径：未选择', self)
        self.output_label.setStyleSheet(f'color: {LightBlueStyle.COLORS["text_secondary"]};')
        output_layout.addWidget(self.output_label)
        
        self.select_output_btn = QPushButton('选择路径', self)
        self.select_output_btn.setFixedWidth(80)
        self.select_output_btn.clicked.connect(self.select_output_path)
        output_layout.addWidget(self.select_output_btn)
        layout.addWidget(output_widget)
        
        # 进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(20)  # 增加高度到20
        self.progress_bar.setStyleSheet(f'''
            QProgressBar {{
                border: none;
                background-color: #F0F0F0;
                border-radius: 10px;
                text-align: center;
                color: #333333;
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {LightBlueStyle.COLORS['primary']};
                border-radius: 10px;
            }}
        ''')
        layout.addWidget(self.progress_bar)
        
        # 按钮容器
        button_widget = QWidget()
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_widget.setLayout(button_layout)
        
        # 添加弹性空间，使按钮居中
        button_layout.addStretch()
        
        # 转换按钮
        self.convert_btn = QPushButton('开始转换', self)
        self.convert_btn.setEnabled(False)
        self.convert_btn.setFixedWidth(100)
        self.convert_btn.clicked.connect(self.start_conversion)
        button_layout.addWidget(self.convert_btn)
        
        # 取消按钮
        self.cancel_btn = QPushButton('取消', self)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setStyleSheet(f'''
            QPushButton {{
                background-color: #F0F0F0;
                color: {LightBlueStyle.COLORS['text_secondary']};
            }}
            QPushButton:hover {{
                background-color: #E0E0E0;
            }}
        ''')
        button_layout.addWidget(self.cancel_btn)
        
        # 添加弹性空间，使按钮居中
        button_layout.addStretch()
        
        layout.addWidget(button_widget)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        valid_images = []
        for url in urls:
            file_path = url.toLocalFile()
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                valid_images.append(file_path)
        
        if valid_images:
            self.input_images = valid_images
            if len(valid_images) == 1:
                self.drop_area.setText(f'已选择文件：\n{os.path.basename(valid_images[0])}')
            else:
                self.drop_area.setText(f'已选择 {len(valid_images)} 个文件')
            
            self.drop_area.setStyleSheet(f'''
                QLabel {{
                    background-color: {LightBlueStyle.COLORS['white']};
                    border: 2px solid {LightBlueStyle.COLORS['primary']};
                    border-radius: 6px;
                    padding: 20px;
                    font-size: 14px;
                    color: {LightBlueStyle.COLORS['primary']};
                }}
            ''')
            if self.output_path:
                self.convert_btn.setEnabled(True)
        else:
            QMessageBox.warning(self, '错误', '请拖放有效的图片文件（PNG/JPG）')
                
    def select_output_path(self):
        path = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if path:
            self.output_path = path
            self.output_label.setText(f'输出路径：{path}')
            if self.input_images:
                self.convert_btn.setEnabled(True)
                
    def start_conversion(self):
        """开始转换"""
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 创建后台线程
        self.conversion_thread = ConversionThread(
            self.input_images, 
            self.output_path
        )
        self.conversion_thread.progress.connect(self.update_progress)
        self.conversion_thread.finished.connect(self.conversion_finished)
        self.conversion_thread.error.connect(self.conversion_error)
        self.conversion_thread.current_file.connect(self.update_current_file)
        self.conversion_thread.start()
    
    def update_current_file(self, filename):
        """更新当前处理的文件名"""
        self.drop_area.setText(f'正在处理：\n{filename}')
    
    def cancel_conversion(self):
        """取消转换"""
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.conversion_thread.wait()
        self.cancel_btn.setEnabled(False)
        self.convert_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
    def conversion_finished(self, output_pdfs):
        """转换完成"""
        self.progress_bar.setValue(100)
        self.cancel_btn.setEnabled(False)
        self.convert_btn.setEnabled(True)
        
        if len(output_pdfs) == 1:
            QMessageBox.information(self, '完成', f'PDF文件已保存到：\n{output_pdfs[0]}')
        else:
            message = "所有PDF文件已保存到：\n" + "\n".join(output_pdfs)
            QMessageBox.information(self, '完成', message)
        
    def conversion_error(self, error_message):
        """转换出错"""
        self.cancel_btn.setEnabled(False)
        self.convert_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, '错误', error_message)
        
    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)

# 添加这段代码到文件末尾
if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
