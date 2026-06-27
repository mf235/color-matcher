import sys
import os
import cv2
import numpy as np
import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QSlider, QComboBox, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

def imread_japanese(filename):
    """日本語パス対応の画像読み込み"""
    try:
        n = np.fromfile(filename, np.uint8)
        img = cv2.imdecode(n, cv2.IMREAD_UNCHANGED) 
        return img
    except Exception as e:
        print(f"Read Error: {e}")
        return None

def imwrite_japanese(filename, img):
    """日本語パス対応の画像保存"""
    try:
        ext = os.path.splitext(filename)[1]
        result, n = cv2.imencode(ext, img)
        if result:
            with open(filename, mode='w+b') as f:
                n.tofile(f)
            return True
        return False
    except Exception as e:
        print(f"Write Error: {e}")
        return False

class DropLabel(QLabel):
    """ドラッグ＆ドロップ対応のラベル"""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 2px dashed #00ffff; background-color: #1a1a1a; color: #ffffff;")
        self.setAcceptDrops(True)
        self.image_path = None
        self.original_cv_image = None # ★ 高画質の元データを退避
        self.cv_image = None          # ★ UIプレビュー用の縮小データ
        self.setMinimumSize(300, 300)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.load_image(path)

    def load_image(self, path):
        img = imread_japanese(path)
        if img is not None:
            self.image_path = path
            
            # ★ オリジナルの高画質画像をそのままメモリに退避
            self.original_cv_image = img.copy() 
            
            # ★ サムネイル表示用だけにリサイズを行う
            h, w = img.shape[:2]
            scale = min(600/w, 600/h)
            if scale < 1:
                new_w, new_h = int(w * scale), int(h * scale)
                self.cv_image = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                self.cv_image = img.copy()
            
            self.update_display()
            self.parent().process_image()

    def update_display(self):
        if self.cv_image is not None:
            h, w, ch = self.cv_image.shape
            if ch == 4:
                rgb_img = cv2.cvtColor(self.cv_image, cv2.COLOR_BGRA2RGBA)
                bytes_per_line = ch * w
                qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGBA8888)
            else:
                rgb_img = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2RGB)
                bytes_per_line = ch * w
                qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_img)
            self.setPixmap(pixmap)

class ColorMatcherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.result_image = None # ★ ここには常に高画質な処理結果が入る
        self.initUI()

    def initUI(self):
        self.setWindowTitle('色合わせツール')
        self.setStyleSheet("background-color: #0d0d0d; color: #ffffff;")
        
        main_layout = QVBoxLayout()

        drop_layout = QHBoxLayout()
        self.source_label = DropLabel("ここに元画像を\nドロップ\n(透過PNG対応)", self)
        self.target_label = DropLabel("ここに色参考画像を\nドロップ", self)
        drop_layout.addWidget(self.source_label)
        drop_layout.addWidget(self.target_label)
        main_layout.addLayout(drop_layout)

        self.preview_label = QLabel("プレビュー", self)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 2px solid #a020f0; background-color: #1a1a1a;")
        self.preview_label.setMinimumSize(600, 600)
        main_layout.addWidget(self.preview_label)

        control_layout = QHBoxLayout()
        
        algo_label = QLabel("モード:", self)
        control_layout.addWidget(algo_label)
        
        self.algo_combo = QComboBox(self)
        self.algo_combo.setStyleSheet("background-color: #2a2a2a; color: #00ffff; border: 1px solid #a020f0; padding: 5px; font-weight: bold;")
        self.algo_combo.addItems([
            "1. 標準 (全体平均)", 
            "2. 白黒除外 (輝度マスク)", 
            "3. 主要色抽出 (K-Means)", 
            "4. ヒストグラムマッチング"
        ])
        self.algo_combo.setCurrentIndex(1) # ★ デフォルトを「2. 白黒除外」に設定
        self.algo_combo.currentIndexChanged.connect(self.process_image)
        control_layout.addWidget(self.algo_combo)

        slider_label = QLabel(" 適用度:", self)
        control_layout.addWidget(slider_label)
        
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(10)
        self.slider.setStyleSheet("QSlider::handle:horizontal { background-color: #00ffff; }")
        self.slider.valueChanged.connect(self.process_image)
        control_layout.addWidget(self.slider)

        self.save_btn = QPushButton("保存する", self)
        self.save_btn.setStyleSheet("background-color: #a020f0; color: white; font-weight: bold; padding: 10px;")
        self.save_btn.clicked.connect(self.save_image)
        control_layout.addWidget(self.save_btn)

        main_layout.addLayout(control_layout)
        self.setLayout(main_layout)

    def process_image(self):
        # ★ 計算はすべて「退避してあるオリジナル画像」に対して行う
        if self.source_label.original_cv_image is None or self.target_label.original_cv_image is None:
            return

        source = self.source_label.original_cv_image.copy()
        target = self.target_label.original_cv_image.copy()
        blend_ratio = self.slider.value() / 100.0
        algo_idx = self.algo_combo.currentIndex()

        if source.shape[2] == 3:
            source = cv2.cvtColor(source, cv2.COLOR_BGR2BGRA)
        if target.shape[2] == 3:
            target = cv2.cvtColor(target, cv2.COLOR_BGR2BGRA)

        if blend_ratio == 0:
            self.result_image = source.copy()
            self.update_preview()
            return

        src_alpha = source[:, :, 3]
        tgt_alpha = target[:, :, 3]

        mask_threshold = 10
        src_mask = (src_alpha >= mask_threshold).astype("uint8")
        tgt_mask = (tgt_alpha >= mask_threshold).astype("uint8")

        src_rgb = source[:, :, :3]
        tgt_rgb = target[:, :, :3]
        src_lab = cv2.cvtColor(src_rgb, cv2.COLOR_BGR2LAB).astype("float32")
        tgt_lab = cv2.cvtColor(tgt_rgb, cv2.COLOR_BGR2LAB).astype("float32")

        if algo_idx in [0, 1, 2]: 
            if algo_idx == 1: 
                lum_min, lum_max = 20, 235
                src_lum_mask = ((src_lab[:,:,0] >= lum_min) & (src_lab[:,:,0] <= lum_max)).astype("uint8")
                tgt_lum_mask = ((tgt_lab[:,:,0] >= lum_min) & (tgt_lab[:,:,0] <= lum_max)).astype("uint8")
                
                s_mask = cv2.bitwise_and(src_mask, src_lum_mask)
                t_mask = cv2.bitwise_and(tgt_mask, tgt_lum_mask)
                
                if cv2.countNonZero(s_mask) < 10: s_mask = src_mask
                if cv2.countNonZero(t_mask) < 10: t_mask = tgt_mask
            else:
                s_mask = src_mask
                t_mask = tgt_mask

            if algo_idx == 2: 
                def get_kmeans_stats(lab_img, mask, k=5):
                    pixels = lab_img[mask > 0]
                    if len(pixels) < k:
                        return np.mean(lab_img, axis=(0,1)), np.std(lab_img, axis=(0,1))
                    
                    np.random.seed(42) 
                    # 重くならないようサンプリング数を制限
                    if len(pixels) > 10000:
                        indices = np.random.choice(len(pixels), 10000, replace=False)
                        pixels = pixels[indices]
                        
                    pixels = np.float32(pixels)
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
                    _, _, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
                    return np.mean(centers, axis=0), np.std(centers, axis=0)

                src_mean, src_std = get_kmeans_stats(src_lab, s_mask)
                tgt_mean, tgt_std = get_kmeans_stats(tgt_lab, t_mask)

                l = (src_lab[:, :, 0] - src_mean[0]) * (tgt_std[0] / (src_std[0] + 1e-5)) + tgt_mean[0]
                a = (src_lab[:, :, 1] - src_mean[1]) * (tgt_std[1] / (src_std[1] + 1e-5)) + tgt_mean[1]
                b = (src_lab[:, :, 2] - src_mean[2]) * (tgt_std[2] / (src_std[2] + 1e-5)) + tgt_mean[2]

            else: 
                (lMeanSrc, lStdSrc) = cv2.meanStdDev(src_lab[:, :, 0], mask=s_mask)
                (aMeanSrc, aStdSrc) = cv2.meanStdDev(src_lab[:, :, 1], mask=s_mask)
                (bMeanSrc, bStdSrc) = cv2.meanStdDev(src_lab[:, :, 2], mask=s_mask)

                (lMeanTgt, lStdTgt) = cv2.meanStdDev(tgt_lab[:, :, 0], mask=t_mask)
                (aMeanTgt, aStdTgt) = cv2.meanStdDev(tgt_lab[:, :, 1], mask=t_mask)
                (bMeanTgt, bStdTgt) = cv2.meanStdDev(tgt_lab[:, :, 2], mask=t_mask)

                l = (src_lab[:, :, 0] - lMeanSrc[0][0]) * (lStdTgt[0][0] / (lStdSrc[0][0] + 1e-5)) + lMeanTgt[0][0]
                a = (src_lab[:, :, 1] - aMeanSrc[0][0]) * (aStdTgt[0][0] / (aStdSrc[0][0] + 1e-5)) + aMeanTgt[0][0]
                b = (src_lab[:, :, 2] - bMeanSrc[0][0]) * (bStdTgt[0][0] / (bStdSrc[0][0] + 1e-5)) + bMeanTgt[0][0]

        elif algo_idx == 3: 
            def match_hist(src_ch, tgt_ch, s_mask, t_mask):
                src_hist, _ = np.histogram(src_ch[s_mask > 0], bins=256, range=[0, 256])
                tgt_hist, _ = np.histogram(tgt_ch[t_mask > 0], bins=256, range=[0, 256])
                
                if src_hist.sum() == 0 or tgt_hist.sum() == 0:
                    return src_ch

                src_cdf = src_hist.cumsum() / src_hist.sum()
                tgt_cdf = tgt_hist.cumsum() / tgt_hist.sum()
                
                lut = np.zeros(256, dtype="uint8")
                for i in range(256):
                    idx = np.abs(tgt_cdf - src_cdf[i]).argmin()
                    lut[i] = idx
                    
                src_ch_uint8 = np.clip(src_ch, 0, 255).astype("uint8")
                res = cv2.LUT(src_ch_uint8, lut)
                return res.astype("float32")

            l = match_hist(src_lab[:, :, 0], tgt_lab[:, :, 0], src_mask, tgt_mask)
            a = match_hist(src_lab[:, :, 1], tgt_lab[:, :, 1], src_mask, tgt_mask)
            b = match_hist(src_lab[:, :, 2], tgt_lab[:, :, 2], src_mask, tgt_mask)

        l = np.clip(l, 0, 255)
        a = np.clip(a, 0, 255)
        b = np.clip(b, 0, 255)

        transfer_lab = cv2.merge([l, a, b]).astype("uint8")
        transfer_rgb = cv2.cvtColor(transfer_lab, cv2.COLOR_LAB2BGR)

        src_mask_float = src_alpha.astype("float32") / 255.0
        src_mask_float = np.expand_dims(src_mask_float, axis=2)
        src_mask_float = np.repeat(src_mask_float, 3, axis=2)

        blended_rgb = (src_mask_float * transfer_rgb.astype("float32")) + ((1.0 - src_mask_float) * src_rgb.astype("float32"))
        blended_rgb = np.clip(blended_rgb, 0, 255).astype("uint8")

        transfer_bgra = cv2.cvtColor(blended_rgb, cv2.COLOR_BGR2BGRA)
        transfer_bgra[:, :, 3] = src_alpha

        if blend_ratio < 1.0:
            self.result_image = cv2.addWeighted(transfer_bgra, blend_ratio, source, 1.0 - blend_ratio, 0)
        else:
            self.result_image = transfer_bgra

        self.update_preview()

    def update_preview(self):
        # ★ ここで「高画質な結果」をプレビュー枠に合わせて縮小表示する
        if self.result_image is not None:
            preview_img = self.result_image.copy()
            h, w = preview_img.shape[:2]
            scale = min(600/w, 600/h)
            if scale < 1:
                new_w, new_h = int(w * scale), int(h * scale)
                preview_img = cv2.resize(preview_img, (new_w, new_h), interpolation=cv2.INTER_AREA)

            h, w, ch = preview_img.shape
            rgb_img = cv2.cvtColor(preview_img, cv2.COLOR_BGRA2RGBA)
            bytes_per_line = ch * w
            qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qt_img)
            self.preview_label.setPixmap(pixmap)

    def save_image(self):
        # ★ 高画質そのままの result_image を保存する
        if self.result_image is None:
            QMessageBox.warning(self, "エラー", "保存する画像がありません！")
            return

        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"recolor-{now}.png"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

        success = imwrite_japanese(filepath, self.result_image)
        if success:
            QMessageBox.information(self, "成功", f"画像を透過PNGとして保存したぞ！\n{filepath}")
        else:
            QMessageBox.critical(self, "エラー", "画像の保存に失敗したみたいだ...")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ColorMatcherApp()
    ex.show()
    sys.exit(app.exec_())