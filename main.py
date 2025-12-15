from PIL import Image
import numpy as np
from PyPDF2 import PdfWriter
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QProgressBar, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QIcon
from style import LightBlueStyle  # 导入样式类
from splitter import get_splitter  # 导入分割器模块

# A4尺寸（300dpi）- 仅用于 PDF 生成
A4_WIDTH = 2480
A4_HEIGHT = 3508

def split_image(image_path, output_dir, has_table=False):
    """分割图片
    
    Args:
        image_path: 图片路径
        output_dir: 输出目录
        has_table: 是否包含表格（使用表格感知分割）
    """
    img = Image.open(image_path)
    
    # 根据是否有表格选择分割器
    splitter = get_splitter(has_table=has_table)
    
    # 找到分割点
    split_points = splitter.find_split_points(img)
    
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
    
    def __init__(self, input_images, output_path, has_table=False):
        super().__init__()
        self.input_images = input_images
        self.output_path = output_path
        self.has_table = has_table  # 是否包含表格
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
                image_paths = split_image(image_path, output_dir, self.has_table)
                
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
        self.setFixedSize(500, 380)  # 增加窗口高度以容纳勾选框
        
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
        
        # 表格选项勾选框
        self.table_checkbox = QCheckBox('内有表格（避免在表格中间分割）', self)
        self.table_checkbox.setStyleSheet(f'''
            QCheckBox {{
                color: {LightBlueStyle.COLORS['text']};
                font-size: 13px;
                padding: 5px 0;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid {LightBlueStyle.COLORS['border']};
                border-radius: 4px;
                background-color: {LightBlueStyle.COLORS['white']};
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid {LightBlueStyle.COLORS['primary']};
                border-radius: 4px;
                background-color: {LightBlueStyle.COLORS['primary']};
            }}
        ''')
        layout.addWidget(self.table_checkbox)
        
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
            self.output_path,
            has_table=self.table_checkbox.isChecked()  # 传递勾选框状态
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
