import sys
import os
import shutil
import mpv
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QSlider, QLabel, QMessageBox, QMenuBar,
    QMenu, QLineEdit, QDialog, QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, QElapsedTimer
from PyQt6.QtGui import QAction, QKeySequence, QIcon, QMovie

RECENT_FILES_LIMIT = 10

class VideoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMinimumHeight(350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #111;")  # dark placeholder background

class StreamDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open Stream URL")
        self.setFixedSize(400, 100)
        layout = QVBoxLayout(self)
        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Enter stream URL (YouTube, Twitch, etc.)")
        layout.addWidget(self.url_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_url(self):
        return self.url_input.text().strip()

class BlitzPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- App Icon ---
        ico_path = os.path.join(os.path.dirname(__file__), "logo.ico")
        if os.path.isfile(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        self.setWindowTitle("BlitzPlayer")
        self.setGeometry(200, 200, 900, 600)
        self.recent_files = []
        self.is_fullscreen = False
        self.playbar_visible = True
        self._is_seeking = False
        self._awaiting_stream = False

        # Fullscreen Playbar
        self.fullscreen_hide_delay = 2000  # ms
        self.last_mouse_event = QElapsedTimer()
        self.mouse_in_playbar_area = False

        # yt-dlp Check
        self.ytdlp_path = shutil.which("yt-dlp")
        if not self.ytdlp_path:
            QMessageBox.critical(self, "yt-dlp Missing", 
                "yt-dlp is not found in your PATH. Streaming from YouTube/Twitch will not work.\n"
                "Please install yt-dlp and ensure it is in your system PATH.")

        # --- Central widget & Video ---
        central = QWidget(self)
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        self.video = VideoWidget(self)
        vbox.addWidget(self.video, stretch=2)

        # --- Loading Overlay & GIF ---
        self.loading_overlay = QWidget(self.video)
        self.loading_overlay.setStyleSheet("background: rgba(0,0,0,0.6);")  # semi-transparent overlay
        self.loading_overlay.hide()
        self.loading_label = QLabel(self.loading_overlay)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("background: transparent;")
        spinner_path = os.path.join(os.path.dirname(__file__), "loading.gif")
        if os.path.isfile(spinner_path):
            self.loading_movie = QMovie(spinner_path)
            self.loading_label.setMovie(self.loading_movie)
        else:
            self.loading_movie = None

        # --- Playbar ---
        self.playbar_widget = QWidget(self)
        playbar = QHBoxLayout(self.playbar_widget)
        playbar.setContentsMargins(12, 8, 12, 8)
        playbar.setSpacing(8)
        self.playbar_widget.setStyleSheet("background: rgba(32,32,32,0.92); border-top: 1px solid #111;")

        def icon_button(text, tooltip, slot):
            btn = QPushButton(text)
            btn.setMinimumSize(36, 36)
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet("font-size: 20px;")
            return btn

        # Buttons
        self.btn_open = icon_button("📂", "Open File (Ctrl+O)", self.open_file)
        playbar.addWidget(self.btn_open)
        self.btn_back = icon_button("⏮️", "Back 10s", self.skip_back)
        playbar.addWidget(self.btn_back)
        self.play_symbol = "▶️"
        self.pause_symbol = "⏸️"
        self.btn_play = icon_button(self.play_symbol, "Play/Pause (Space)", self.toggle_play)
        playbar.addWidget(self.btn_play)
        self.btn_stop = icon_button("⏹️", "Stop (S)", self.stop_playback)
        playbar.addWidget(self.btn_stop)
        self.btn_forward = icon_button("⏭️", "Forward 10s", self.skip_forward)
        playbar.addWidget(self.btn_forward)
        self.volume_on_symbol = "🔊"
        self.volume_mute_symbol = "🔇"
        self.btn_volume = icon_button(self.volume_on_symbol, "Mute/Unmute (M)", self.toggle_mute)
        playbar.addWidget(self.btn_volume)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumWidth(110)
        self.volume_slider.valueChanged.connect(self.set_volume)
        playbar.addWidget(self.volume_slider)
        self.time_label = QLabel("00:00")
        self.time_label.setMinimumWidth(55)
        playbar.addWidget(self.time_label)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._seek_start)
        self.slider.sliderReleased.connect(self._seek_end)
        self.slider.sliderMoved.connect(self.seek_position)
        self.slider.setMinimumWidth(150)
        playbar.addWidget(self.slider, stretch=1)
        self.total_time_label = QLabel("00:00")
        self.total_time_label.setMinimumWidth(55)
        playbar.addWidget(self.total_time_label)
        self.full_symbol = "⛶"
        self.window_symbol = "🗗"
        self.btn_fullscreen = icon_button(self.full_symbol, "Fullscreen (F)", self.toggle_fullscreen)
        playbar.addWidget(self.btn_fullscreen)
        vbox.addWidget(self.playbar_widget, stretch=0)

        # --- MPV Setup ---
        self.mpv = mpv.MPV(
            ytdl=True,
            script_opts=f"ytdl_hook-ytdl_path={self.ytdlp_path or 'yt-dlp'}",
            wid=int(self.video.winId()),
            input_default_bindings=True,
            input_vo_keyboard=True,
        )
        self.mpv.observe_property('playback-time', self._on_playback_time)
        self.mpv.observe_property('pause', self._on_pause)
        self.mpv.observe_property('seeking', self._on_seeking)
        self.mpv.observe_property('idle', self._on_idle)
        self.mpv.event_callback("start-file")(self._on_start_file)
        self.mpv.event_callback("file-loaded")(self._on_file_loaded)
        self.mpv.observe_property("mute", self._on_mute_changed)

        # --- Timer for UI ---
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(500)

        # --- Fullscreen Playbar Timer ---
        self.hide_playbar_timer = QTimer(self)
        self.hide_playbar_timer.setInterval(self.fullscreen_hide_delay)
        self.hide_playbar_timer.timeout.connect(self._fullscreen_hide_playbar)
        self.last_mouse_event.start()

        # --- Menubar ---
        self.menubar = QMenuBar(self)
        self.setMenuBar(self.menubar)
        file_menu = QMenu("File", self)
        open_file_action = QAction("Open File", self)
        open_file_action.setShortcut(QKeySequence("Ctrl+O"))
        open_file_action.triggered.connect(self.open_file)
        file_menu.addAction(open_file_action)
        self.recent_menu = QMenu("Recent Files", self)
        file_menu.addMenu(self.recent_menu)
        self.update_recent_files_menu()
        self.menubar.addMenu(file_menu)
        stream_menu = QMenu("Stream", self)
        open_stream_action = QAction("Open Stream URL", self)
        open_stream_action.setShortcut(QKeySequence("Ctrl+U"))
        open_stream_action.triggered.connect(self.open_stream_url)
        stream_menu.addAction(open_stream_action)
        self.menubar.addMenu(stream_menu)
        about_menu = QMenu("About", self)
        about_menu.addAction("About BlitzPlayer").triggered.connect(self.show_about)
        self.menubar.addMenu(about_menu)

        # --- Shortcuts ---
        self.add_shortcut("Space", self.toggle_play)
        self.add_shortcut("S", self.stop_playback)
        self.add_shortcut("F", self.toggle_fullscreen)
        self.add_shortcut("M", self.toggle_mute)
        self.add_shortcut("Q", self.close)
        self.add_shortcut("Esc", self.esc_action)
        self.add_shortcut("Ctrl+O", self.open_file)
        self.add_shortcut("Ctrl+U", self.open_stream_url)

        # --- Event Filter ---
        self.video.installEventFilter(self)
        self.setMouseTracking(True)
        self.video.setMouseTracking(True)
        self.last_mouse_pos = QPoint(0, 0)

    # =========================
    # --- Loading GIF -------
    # =========================
    def show_loading(self):
        if self.loading_movie:
            self.loading_overlay.setGeometry(self.video.rect())
            self.loading_label.setGeometry(
                (self.video.width() - 180)//2,
                (self.video.height() - 180)//2,
                180, 180
            )
            self.loading_overlay.show()
            self.loading_label.show()
            self.loading_movie.start()
            self.loading_overlay.raise_()
            self.loading_label.raise_()
            QApplication.processEvents()  # ensures GIF shows instantly

    def hide_loading(self):
        if self.loading_movie:
            self.loading_movie.stop()
            self.loading_label.hide()
            self.loading_overlay.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.loading_overlay.isVisible():
            self.loading_overlay.setGeometry(self.video.rect())
            self.loading_label.setGeometry(
                (self.video.width() - 180)//2,
                (self.video.height() - 180)//2,
                180, 180
            )

    # =========================
    # --- MPV Callbacks ------
    # =========================
    def _on_start_file(self, event):
        if self._awaiting_stream:
            self.show_loading()

    def _on_file_loaded(self, event):
        self.hide_loading()
        self._awaiting_stream = False

    def _on_playback_time(self, _name, value):
        self.hide_loading()
        self._awaiting_stream = False

    def _on_pause(self, _name, value): 
        if not self._is_seeking: self.hide_loading()
        self.update_play_button()

    def _on_seeking(self, _name, value):
        if value:
            if self._awaiting_stream:
                self.show_loading()
            self._is_seeking = True
        else:
            self.hide_loading()
            self._is_seeking = False

    def _on_idle(self, _name, value): 
        self.hide_loading()
        self._awaiting_stream = False

    def _on_mute_changed(self, _name, value):
        if value:
            self.btn_volume.setText(self.volume_mute_symbol)
        else:
            self.btn_volume.setText(self.volume_on_symbol)

    # =========================
    # --- File & Stream ------
    # =========================
    def open_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open Media File")
        if file:
            self.play_file(file)

    def play_file(self, file):
        self._awaiting_stream = False
        self.hide_loading()
        self.mpv.play(file)
        self.add_recent_file(file)

    def add_recent_file(self, file):
        if file in self.recent_files:
            self.recent_files.remove(file)
        self.recent_files.insert(0, file)
        if len(self.recent_files) > RECENT_FILES_LIMIT:
            self.recent_files.pop()
        self.update_recent_files_menu()

    def update_recent_files_menu(self):
        self.recent_menu.clear()
        if not self.recent_files:
            act = QAction("(No Recent Files)", self.recent_menu)
            act.setEnabled(False)
            self.recent_menu.addAction(act)
            return
        for file in self.recent_files:
            act = QAction(os.path.basename(file), self.recent_menu)
            act.setToolTip(file)
            act.triggered.connect(lambda checked, f=file: self.play_file(f))
            self.recent_menu.addAction(act)

    def open_stream_url(self):
        if not self.ytdlp_path:
            QMessageBox.critical(self, "yt-dlp Missing", 
                "yt-dlp is required for streaming from URLs. Please install yt-dlp and ensure it is in your system PATH.")
            return
        dlg = StreamDialog(self)
        if dlg.exec():
            url = dlg.get_url()
            if url:
                self._awaiting_stream = True
                self.show_loading()
                QApplication.processEvents()  # <--- Force spinner to show!
                try:
                    self.mpv.play(url)
                except Exception as e:
                    self.hide_loading()
                    self._awaiting_stream = False
                    QMessageBox.critical(self, "Stream Error", f"Could not play stream:\n{e}")

    # =========================
    # --- Playback Controls ---
    # =========================
    def toggle_play(self):
        self.mpv.pause = not (self.mpv.pause or False)

    def stop_playback(self):
        self.mpv.stop()

    def toggle_mute(self):
        self.mpv.mute = not (self.mpv.mute or False)

    def set_volume(self, value):
        self.mpv.volume = value
        self.mpv.mute = (value==0)

    def skip_back(self):
        self.mpv.command("seek", -10)

    def skip_forward(self):
        self.mpv.command("seek", 10)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.btn_fullscreen.setText(self.full_symbol)
            self.show_playbar()
            self.menubar.show()
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.btn_fullscreen.setText(self.window_symbol)
            self.show_playbar()
            self.hide_playbar_timer.start()
            self.menubar.hide()

    def esc_action(self):
        if self.is_fullscreen:
            self.toggle_fullscreen()

    def _seek_start(self): self._is_seeking = True
    def _seek_end(self): self._is_seeking = False
    def seek_position(self, value):
        dur = self.mpv.duration or 0
        if dur > 0:
            pos = (value/1000) * dur
            self.mpv.seek(pos, reference="absolute")

    # =========================
    # --- UI Updates ---------
    # =========================
    def update_ui(self):
        try:
            pos = self.mpv.time_pos or 0
            dur = self.mpv.duration or 0
            if dur > 0:
                self.slider.setValue(int((pos/dur)*1000))
            self.time_label.setText(self.format_time(pos))
            self.total_time_label.setText(self.format_time(dur))
            self.update_play_button()
        except Exception: pass

    def update_play_button(self):
        if getattr(self.mpv, "pause", True):
            self.btn_play.setText(self.play_symbol)
        else:
            self.btn_play.setText(self.pause_symbol)

    @staticmethod
    def format_time(seconds):
        m, s = int(seconds//60), int(seconds%60)
        return f"{m:02}:{s:02}"

    # =========================
    # --- Playbar -----------
    # =========================
    def show_playbar(self):
        self.playbar_widget.show()
        self.playbar_visible = True

    def hide_playbar(self):
        if self.is_fullscreen:
            self.playbar_widget.hide()
            self.playbar_visible = False

    def _fullscreen_hide_playbar(self):
        if self.is_fullscreen:
            self.hide_playbar()

    # =========================
    # --- About -------------
    # =========================
    def show_about(self):
        QMessageBox.information(self, "About BlitzPlayer", "BlitzPlayer v1.0\nBuilt with PyQt6 + MPV + yt-dlp")

    # =========================
    # --- Shortcuts ---------
    # =========================
    def add_shortcut(self, key, slot):
        sc = QAction(self)
        sc.setShortcut(QKeySequence(key))
        sc.triggered.connect(slot)
        self.addAction(sc)

    # =========================
    # --- Events -------------
    # =========================
    def closeEvent(self, event):
        try:
            self.mpv.terminate()
        except Exception: pass
        event.accept()

    def eventFilter(self, obj, event):
        if self.is_fullscreen and obj == self.video:
            if event.type() == QEvent.Type.MouseMove:
                self.show_playbar()
                self.hide_playbar_timer.start(self.fullscreen_hide_delay)
        return super().eventFilter(obj, event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BlitzPlayer()
    window.show()
    sys.exit(app.exec())
