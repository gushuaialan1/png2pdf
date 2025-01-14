
from PyQt6.QtWidgets import QFrame, QStyle, QStyleOption
from PyQt6.QtGui import QPainter

class LightBlueStyle:
    """淡蓝色主题样式"""
    
    # 颜色定义
    COLORS = {
        'background': '#F0F8FF',
        'primary': '#87CEEB',
        'primary_hover': '#ADD8E6',
        'primary_pressed': '#4682B4',
        'border': '#ADD8E6',
        'border_hover': '#87CEEB',
        'text': '#333333',
        'text_secondary': '#666666',
        'white': '#FFFFFF',
        'disabled': '#D3D3D3',
        'disabled_text': '#A9A9A9',
    }
    
    @classmethod
    def get_main_window_style(cls):
        """获取主窗口样式"""
        return f"""
            QMainWindow, QDialog {{
                background-color: {cls.COLORS['background']};
            }}
            QWidget {{
                background-color: {cls.COLORS['background']};
            }}
            QLabel {{
                color: {cls.COLORS['text']};
            }}
            QLineEdit {{
                border: 1px solid {cls.COLORS['border']};
                border-radius: 3px;
                padding: 5px;
                background-color: {cls.COLORS['white']};
            }}
            QLineEdit:focus {{
                border: 1px solid {cls.COLORS['border_hover']};
            }}
            QPushButton {{
                background-color: {cls.COLORS['primary']};
                border: none;
                border-radius: 3px;
                padding: 8px 16px;
                color: {cls.COLORS['white']};
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {cls.COLORS['primary_hover']};
            }}
            QPushButton:pressed {{
                background-color: {cls.COLORS['primary_pressed']};
            }}
            QPushButton:disabled {{
                background-color: {cls.COLORS['disabled']};
                color: {cls.COLORS['disabled_text']};
            }}
            QComboBox {{
                border: 1px solid {cls.COLORS['border']};
                border-radius: 3px;
                padding: 5px;
                min-width: 150px;
                background-color: {cls.COLORS['white']};
            }}
            QComboBox:hover {{
                border: 1px solid {cls.COLORS['border_hover']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
            }}
            QProgressBar {{
                border: none;
                border-radius: 3px;
                background-color: #E6E6E6;
                text-align: center;
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {cls.COLORS['primary']};
                border-radius: 3px;
            }}
            QTextEdit {{
                border: 1px solid {cls.COLORS['border']};
                border-radius: 3px;
                padding: 5px;
                background-color: {cls.COLORS['white']};
            }}
            QScrollBar:vertical {{
                border: none;
                background-color: #F0F0F0;
                width: 10px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {cls.COLORS['border']};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {cls.COLORS['primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """
    
    @classmethod
    def get_task_card_style(cls):
        """获取任务卡片样式"""
        return f"""
            QFrame#taskCard {{
                background-color: {cls.COLORS['white']};
                border: 1px solid #E6E6E6;
                border-radius: 4px;
                margin: 4px;
                padding: 8px;
            }}
            QFrame#taskCard:hover {{
                border: 1px solid {cls.COLORS['border']};
            }}
            QPushButton[text="取消"] {{
                background-color: #F0F0F0;
                color: {cls.COLORS['text_secondary']};
            }}
            QPushButton[text="取消"]:hover {{
                background-color: #E0E0E0;
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """

class StyledFrame(QFrame):
    """自定义样式框架"""
    def __init__(self):
        super().__init__()
        self.setObjectName("taskCard")
        
    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self) 