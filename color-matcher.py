import sys
import os
import cv2
import numpy as np
import datetime
import json
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QSlider, QComboBox, QMessageBox,
                             QSizePolicy, QMenu)
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen

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

class ZoomableImageLabel(QLabel):
    """縦横比維持・ホイールズーム・ドラッグ移動対応の画像表示ラベル"""
    MIN_ZOOM = 0.01
    MAX_ZOOM = 20.0  # 2000%

    def __init__(self, title, parent=None, accept_drops=False, dashed_border=False, border_color="#00ffff"):
        super().__init__(title, parent)
        self.title = title
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(accept_drops)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.OpenHandCursor)

        self.accept_drops = accept_drops
        self.dashed_border = dashed_border
        self.border_color = border_color
        self.bg_color = "#1a1a1a"
        self.text_color = "#ffffff"

        self.image_path = None
        self.original_cv_image = None
        self.fit_mode = True
        self.zoom_scale = 1.0
        self.center = None
        self.dragging = False
        self.last_drag_pos = None

    def dragEnterEvent(self, event):
        if self.accept_drops and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.accept_drops:
            event.ignore()
            return
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.load_image(path)
            event.acceptProposedAction()

    def load_image(self, path):
        img = imread_japanese(path)
        if img is not None:
            self.image_path = path
            self.set_cv_image(img, reset_view=True)
            self.parent().process_image()

    def set_cv_image(self, img, reset_view=False):
        if img is None:
            self.original_cv_image = None
            self.center = None
            self.update()
            return

        old_shape = self.original_cv_image.shape[:2] if self.original_cv_image is not None else None
        new_shape = img.shape[:2]
        self.original_cv_image = img.copy()

        if reset_view or old_shape != new_shape or self.center is None:
            self.reset_view()
        else:
            self.clamp_center()
            self.update()

    def reset_view(self):
        self.fit_mode = True
        self.zoom_scale = 1.0
        if self.original_cv_image is not None:
            h, w = self.original_cv_image.shape[:2]
            self.center = QPointF(w / 2.0, h / 2.0)
        else:
            self.center = None
        self.update()

    def center_on_image(self):
        if self.original_cv_image is None:
            return
        h, w = self.original_cv_image.shape[:2]
        self.center = QPointF(w / 2.0, h / 2.0)
        self.clamp_center()
        self.update()

    def get_fit_scale(self):
        if self.original_cv_image is None:
            return 1.0
        h, w = self.original_cv_image.shape[:2]
        area_w = max(1, self.width() - 8)
        area_h = max(1, self.height() - 8)
        return max(self.MIN_ZOOM, min(area_w / max(1, w), area_h / max(1, h)))

    def get_current_scale(self):
        if self.fit_mode:
            return self.get_fit_scale()
        return max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom_scale))

    def set_zoom(self, scale, anchor_pos=None):
        if self.original_cv_image is None:
            return

        old_scale = self.get_current_scale()
        if anchor_pos is not None:
            anchor_img = self.screen_to_image(anchor_pos, old_scale)
        else:
            anchor_img = None

        self.fit_mode = False
        self.zoom_scale = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(scale)))
        new_scale = self.get_current_scale()

        if anchor_img is not None:
            self.center = QPointF(
                anchor_img.x() - (anchor_pos.x() - self.width() / 2.0) / new_scale,
                anchor_img.y() - (anchor_pos.y() - self.height() / 2.0) / new_scale,
            )
        self.clamp_center()
        self.update()

    def zoom_by_factor(self, factor, anchor_pos=None):
        self.set_zoom(self.get_current_scale() * factor, anchor_pos=anchor_pos)

    def screen_to_image(self, pos, scale=None):
        if self.original_cv_image is None:
            return QPointF(0.0, 0.0)
        if scale is None:
            scale = self.get_current_scale()
        if self.center is None:
            h, w = self.original_cv_image.shape[:2]
            self.center = QPointF(w / 2.0, h / 2.0)
        return QPointF(
            self.center.x() + (pos.x() - self.width() / 2.0) / scale,
            self.center.y() + (pos.y() - self.height() / 2.0) / scale,
        )

    def clamp_center(self):
        if self.original_cv_image is None:
            return
        h, w = self.original_cv_image.shape[:2]
        scale = self.get_current_scale()
        view_w = self.width() / max(scale, 1e-6)
        view_h = self.height() / max(scale, 1e-6)

        if self.center is None:
            self.center = QPointF(w / 2.0, h / 2.0)

        if view_w >= w:
            cx = w / 2.0
        else:
            half = view_w / 2.0
            cx = min(max(self.center.x(), half), w - half)

        if view_h >= h:
            cy = h / 2.0
        else:
            half = view_h / 2.0
            cy = min(max(self.center.y(), half), h - half)

        self.center = QPointF(cx, cy)

    def cv_to_qpixmap(self, cv_img):
        if cv_img.ndim == 2:
            rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_GRAY2RGB)
            h, w = rgb_img.shape[:2]
            qt_img = QImage(rgb_img.data, w, h, 3 * w, QImage.Format_RGB888)
        elif cv_img.shape[2] == 4:
            rgba_img = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA)
            h, w = rgba_img.shape[:2]
            qt_img = QImage(rgba_img.data, w, h, 4 * w, QImage.Format_RGBA8888)
        else:
            rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            h, w = rgb_img.shape[:2]
            qt_img = QImage(rgb_img.data, w, h, 3 * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qt_img.copy())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(self.bg_color))

        if self.original_cv_image is None:
            painter.setPen(QColor(self.text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, self.title)
        else:
            self.clamp_center()
            img = self.original_cv_image
            img_h, img_w = img.shape[:2]
            scale = self.get_current_scale()

            view_w_img = self.width() / max(scale, 1e-6)
            view_h_img = self.height() / max(scale, 1e-6)
            x0_f = self.center.x() - view_w_img / 2.0
            y0_f = self.center.y() - view_h_img / 2.0
            x1_f = self.center.x() + view_w_img / 2.0
            y1_f = self.center.y() + view_h_img / 2.0

            x0 = max(0, int(np.floor(x0_f)))
            y0 = max(0, int(np.floor(y0_f)))
            x1 = min(img_w, int(np.ceil(x1_f)))
            y1 = min(img_h, int(np.ceil(y1_f)))

            if x1 > x0 and y1 > y0:
                crop = img[y0:y1, x0:x1]
                pixmap = self.cv_to_qpixmap(crop)

                target_x = self.width() / 2.0 - (self.center.x() - x0) * scale
                target_y = self.height() / 2.0 - (self.center.y() - y0) * scale
                target_w = (x1 - x0) * scale
                target_h = (y1 - y0) * scale
                painter.drawPixmap(QRectF(target_x, target_y, target_w, target_h), pixmap, QRectF(pixmap.rect()))

            zoom_text = "FIT" if self.fit_mode else f"{int(round(scale * 100))}%"
            overlay = f"{zoom_text}"
            text_rect = painter.fontMetrics().boundingRect(overlay).adjusted(-6, -4, 6, 4)
            text_rect.moveBottomRight(self.rect().adjusted(0, 0, -8, -8).bottomRight())
            painter.fillRect(text_rect, QColor(0, 0, 0, 150))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(text_rect, Qt.AlignCenter, overlay)

        pen = QPen(QColor(self.border_color), 2)
        if self.dashed_border:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def resizeEvent(self, event):
        self.clamp_center()
        super().resizeEvent(event)
        self.update()

    def wheelEvent(self, event):
        if self.original_cv_image is None:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            event.ignore()
            return
        factor = 1.25 ** steps
        self.zoom_by_factor(factor, anchor_pos=event.pos())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.original_cv_image is not None:
            self.dragging = True
            self.last_drag_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and self.last_drag_pos is not None and self.original_cv_image is not None:
            scale = self.get_current_scale()
            delta = event.pos() - self.last_drag_pos
            self.center = QPointF(
                self.center.x() - delta.x() / max(scale, 1e-6),
                self.center.y() - delta.y() / max(scale, 1e-6),
            )
            self.last_drag_pos = event.pos()
            self.clamp_center()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.last_drag_pos = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.original_cv_image is None:
            return
        menu = QMenu(self)
        fit_action = menu.addAction("表示リセット（枠に合わせる）")
        center_action = menu.addAction("表示位置を中央へ")
        menu.addSeparator()
        zoom_actions = [
            (menu.addAction("100%"), 1.0),
            (menu.addAction("200%"), 2.0),
            (menu.addAction("400%"), 4.0),
            (menu.addAction("1000%"), 10.0),
            (menu.addAction("2000%"), 20.0),
        ]
        chosen = menu.exec_(event.globalPos())
        if chosen == fit_action:
            self.reset_view()
        elif chosen == center_action:
            self.center_on_image()
        else:
            for action, scale in zoom_actions:
                if chosen == action:
                    self.set_zoom(scale, anchor_pos=event.pos())
                    break

class ColorMatcherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.result_image = None # ★ ここには常に高画質な処理結果が入る
        self.settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "color-matcher-settings.json")
        self.initUI()

    def initUI(self):
        self.setWindowTitle('色合わせツール')
        self.setStyleSheet("background-color: #0d0d0d; color: #ffffff;")
        
        main_layout = QVBoxLayout()

        drop_layout = QHBoxLayout()
        self.source_label = ZoomableImageLabel("ここに元画像を\nドロップ\n(透過PNG対応)", self, accept_drops=True, dashed_border=True, border_color="#00ffff")
        self.target_label = ZoomableImageLabel("ここに色参考画像を\nドロップ", self, accept_drops=True, dashed_border=True, border_color="#00ffff")
        drop_layout.addWidget(self.source_label)
        drop_layout.addWidget(self.target_label)
        main_layout.addLayout(drop_layout)

        self.preview_label = ZoomableImageLabel("プレビュー", self, accept_drops=False, dashed_border=False, border_color="#a020f0")
        self.preview_label.setMinimumSize(600, 520)
        main_layout.addWidget(self.preview_label, stretch=1)

        hint_label = QLabel("ホイール: 拡大縮小 / 左ドラッグ: 表示位置移動 / 右クリック: 表示メニュー", self)
        hint_label.setStyleSheet("color: #bfbfbf; padding: 2px;")
        main_layout.addWidget(hint_label)

        control_layout = QHBoxLayout()
        
        algo_label = QLabel("モード:", self)
        control_layout.addWidget(algo_label)
        
        self.algo_combo = QComboBox(self)
        self.algo_combo.setStyleSheet("background-color: #2a2a2a; color: #00ffff; border: 1px solid #a020f0; padding: 5px; font-weight: bold;")
        self.algo_combo.addItems([
            "1. 標準 (全体平均)", 
            "2. 白黒除外 (輝度マスク)", 
            "3. 主要色抽出 (K-Means)", 
            "4. ヒストグラムマッチング",
            "5. 明度保持 (色味のみ)",
            "6. 明暗別マッチング",
            "7. 安定補正 (外れ値除外)"
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
        self.load_app_settings()

    def read_app_settings(self):
        """スクリプトと同じフォルダのJSONから設定を読み込む"""
        if not os.path.exists(self.settings_path):
            return {}
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"Settings Load Error: {e}")
        return {}

    def load_app_settings(self):
        """前回終了時のパラメータとウィンドウ位置・サイズを復元する"""
        settings = self.read_app_settings()
        if not settings:
            return

        try:
            algo_index = int(settings.get("algo_index", self.algo_combo.currentIndex()))
            if 0 <= algo_index < self.algo_combo.count():
                self.algo_combo.setCurrentIndex(algo_index)
        except Exception:
            pass

        try:
            blend_value = int(settings.get("blend_value", self.slider.value()))
            self.slider.setValue(max(self.slider.minimum(), min(self.slider.maximum(), blend_value)))
        except Exception:
            pass

        window = settings.get("window", {})
        if isinstance(window, dict):
            try:
                width = int(window.get("width", self.width()))
                height = int(window.get("height", self.height()))
                if width > 0 and height > 0:
                    self.resize(width, height)
            except Exception:
                pass

            try:
                x = int(window.get("x", self.x()))
                y = int(window.get("y", self.y()))
                pos = QPoint(x, y)
                desktop = QApplication.desktop()
                is_visible_pos = any(
                    desktop.availableGeometry(i).adjusted(-80, -80, 80, 80).contains(pos)
                    for i in range(desktop.screenCount())
                )
                if is_visible_pos:
                    self.move(x, y)
            except Exception:
                pass

    def save_app_settings(self):
        """現在のパラメータとウィンドウ位置・サイズをJSONへ保存する"""
        settings = {
            "algo_index": self.algo_combo.currentIndex(),
            "blend_value": self.slider.value(),
            "window": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            },
        }
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Settings Save Error: {e}")

    def closeEvent(self, event):
        self.save_app_settings()
        super().closeEvent(event)

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

        def safe_mask(mask):
            """有効ピクセルが少なすぎる場合は全体マスクへ戻す"""
            if cv2.countNonZero(mask) < 10:
                return np.ones(mask.shape, dtype="uint8")
            return mask

        def mean_std_channel(ch, mask):
            """OpenCVのmeanStdDevを使った通常統計"""
            mask = safe_mask(mask)
            mean, std = cv2.meanStdDev(ch, mask=mask)
            return float(mean[0][0]), float(std[0][0])

        def trimmed_mean_std_channel(ch, mask, trim=5):
            """上下の外れ値を除外した平均・標準偏差"""
            mask = safe_mask(mask)
            pixels = ch[mask > 0].astype("float32")
            if pixels.size < 10:
                pixels = ch.reshape(-1).astype("float32")
            if pixels.size == 0:
                return 0.0, 1.0

            low, high = np.percentile(pixels, [trim, 100 - trim])
            trimmed = pixels[(pixels >= low) & (pixels <= high)]
            if trimmed.size < 10:
                trimmed = pixels

            return float(np.mean(trimmed)), float(np.std(trimmed))

        def transfer_channel(src_ch, src_mean, src_std, tgt_mean, tgt_std):
            return (src_ch - src_mean) * (tgt_std / (src_std + 1e-5)) + tgt_mean

        def transfer_lab_by_stats(s_lab, t_lab, s_mask, t_mask, stats_func=mean_std_channel, keep_l=False):
            """LABの平均・標準偏差を合わせる共通処理。keep_l=Trueなら明度は元画像を維持する。"""
            s_l_mean, s_l_std = stats_func(s_lab[:, :, 0], s_mask)
            s_a_mean, s_a_std = stats_func(s_lab[:, :, 1], s_mask)
            s_b_mean, s_b_std = stats_func(s_lab[:, :, 2], s_mask)

            t_l_mean, t_l_std = stats_func(t_lab[:, :, 0], t_mask)
            t_a_mean, t_a_std = stats_func(t_lab[:, :, 1], t_mask)
            t_b_mean, t_b_std = stats_func(t_lab[:, :, 2], t_mask)

            if keep_l:
                out_l = s_lab[:, :, 0].copy()
            else:
                out_l = transfer_channel(s_lab[:, :, 0], s_l_mean, s_l_std, t_l_mean, t_l_std)
            out_a = transfer_channel(s_lab[:, :, 1], s_a_mean, s_a_std, t_a_mean, t_a_std)
            out_b = transfer_channel(s_lab[:, :, 2], s_b_mean, s_b_std, t_b_mean, t_b_std)
            return out_l, out_a, out_b

        if algo_idx in [0, 1, 2, 4, 6]: 
            if algo_idx == 1:
                # 白黒除外: 明るすぎる/暗すぎる画素を統計から外す
                lum_min, lum_max = 20, 235
                src_lum_mask = ((src_lab[:, :, 0] >= lum_min) & (src_lab[:, :, 0] <= lum_max)).astype("uint8")
                tgt_lum_mask = ((tgt_lab[:, :, 0] >= lum_min) & (tgt_lab[:, :, 0] <= lum_max)).astype("uint8")

                s_mask = cv2.bitwise_and(src_mask, src_lum_mask)
                t_mask = cv2.bitwise_and(tgt_mask, tgt_lum_mask)

                if cv2.countNonZero(s_mask) < 10:
                    s_mask = src_mask
                if cv2.countNonZero(t_mask) < 10:
                    t_mask = tgt_mask
            else:
                s_mask = src_mask
                t_mask = tgt_mask

            if algo_idx == 2: 
                def get_kmeans_stats(lab_img, mask, k=5):
                    pixels = lab_img[mask > 0]
                    if len(pixels) < k:
                        return np.mean(lab_img, axis=(0, 1)), np.std(lab_img, axis=(0, 1))

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

                l = transfer_channel(src_lab[:, :, 0], src_mean[0], src_std[0], tgt_mean[0], tgt_std[0])
                a = transfer_channel(src_lab[:, :, 1], src_mean[1], src_std[1], tgt_mean[1], tgt_std[1])
                b = transfer_channel(src_lab[:, :, 2], src_mean[2], src_std[2], tgt_mean[2], tgt_std[2])

            elif algo_idx == 4:
                # 明度保持: Lは元画像のまま、a/bだけ参考画像へ寄せる
                l, a, b = transfer_lab_by_stats(src_lab, tgt_lab, s_mask, t_mask, keep_l=True)

            elif algo_idx == 6:
                # 安定補正: 上下5%の外れ値を除外して統計を取る
                l, a, b = transfer_lab_by_stats(
                    src_lab, tgt_lab, s_mask, t_mask,
                    stats_func=lambda ch, mask: trimmed_mean_std_channel(ch, mask, trim=5),
                    keep_l=False
                )

            else: 
                l, a, b = transfer_lab_by_stats(src_lab, tgt_lab, s_mask, t_mask, keep_l=False)

        elif algo_idx == 3: 
            def match_hist(src_ch, tgt_ch, s_mask, t_mask):
                s_mask = safe_mask(s_mask)
                t_mask = safe_mask(t_mask)
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

        elif algo_idx == 5:
            # 明暗別: 暗部/中間/明部で別々に統計を取り、元画像Lに応じてなめらかに合成する
            ranges = [
                (0, 95, 42.0),
                (80, 185, 128.0),
                (160, 255, 213.0),
            ]
            weight_width = 95.0
            weight_sum = np.zeros(src_lab.shape[:2], dtype="float32") + 1e-5
            l = np.zeros(src_lab.shape[:2], dtype="float32")
            a = np.zeros(src_lab.shape[:2], dtype="float32")
            b = np.zeros(src_lab.shape[:2], dtype="float32")

            for low, high, center in ranges:
                src_l_range = ((src_lab[:, :, 0] >= low) & (src_lab[:, :, 0] <= high)).astype("uint8")
                tgt_l_range = ((tgt_lab[:, :, 0] >= low) & (tgt_lab[:, :, 0] <= high)).astype("uint8")
                s_mask = cv2.bitwise_and(src_mask, src_l_range)
                t_mask = cv2.bitwise_and(tgt_mask, tgt_l_range)

                if cv2.countNonZero(s_mask) < 10:
                    s_mask = src_mask
                if cv2.countNonZero(t_mask) < 10:
                    t_mask = tgt_mask

                part_l, part_a, part_b = transfer_lab_by_stats(src_lab, tgt_lab, s_mask, t_mask, keep_l=False)
                weight = np.maximum(0.0, 1.0 - np.abs(src_lab[:, :, 0] - center) / weight_width).astype("float32")

                l += part_l * weight
                a += part_a * weight
                b += part_b * weight
                weight_sum += weight

            l /= weight_sum
            a /= weight_sum
            b /= weight_sum

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
        # ★ 表示枠側で縦横比維持・ズーム・パンを処理する
        if self.result_image is not None:
            self.preview_label.set_cv_image(self.result_image, reset_view=False)

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