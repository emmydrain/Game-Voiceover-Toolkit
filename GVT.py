import os
import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QListWidget, QWidget, QProgressBar,
    QTabWidget, QComboBox, QGroupBox, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from mutagen import File
import subprocess
import vlc

class AudioScanner(QThread):
    scan_complete = pyqtSignal(dict)
    progress_updated = pyqtSignal(int)

    def __init__(self, game_path):
        super().__init__()
        self.game_path = game_path
        self.audio_extensions = ('.wav', '.ogg', '.mp3', '.flac')

    def run(self):
        audio_files = {}
        total_files = 0
        scanned_files = 0

        # Сначала подсчитываем общее количество файлов для прогресса
        for root, _, files in os.walk(self.game_path):
            for file in files:
                if file.lower().endswith(self.audio_extensions):
                    total_files += 1

        for root, _, files in os.walk(self.game_path):
            for file in files:
                if file.lower().endswith(self.audio_extensions):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.game_path)
                    audio_files[relative_path] = full_path
                    scanned_files += 1
                    self.progress_updated.emit(int(scanned_files / total_files * 100))

        self.scan_complete.emit(audio_files)

class AudioProcessor(QThread):
    progress_updated = pyqtSignal(int)
    status_message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks  # Список словарей: {'game_path': '', 'replacements': {}}

    def run(self):
        total_tasks = sum(len(task['replacements']) for task in self.tasks)
        processed = 0

        for task in self.tasks:
            game_path = task['game_path']
            replacements = task['replacements']

            for original_rel, replacement in replacements.items():
                original_full = os.path.join(game_path, original_rel)
                backup_path = original_full + '.bak'

                try:
                    self.status_message.emit(f"Обработка: {original_rel}")

                    # Создаем backup если его нет
                    if not os.path.exists(backup_path):
                        os.rename(original_full, backup_path)

                    # Конвертируем и заменяем файл
                    subprocess.run([
                        "ffmpeg", "-i", replacement, "-c:a", "libvorbis", "-q:a", "5",
                        original_full
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    processed += 1
                    self.progress_updated.emit(int(processed / total_tasks * 100))

                except Exception as e:
                    self.status_message.emit(f"Ошибка: {str(e)}")

        self.finished.emit()
        self.status_message.emit("Все операции завершены!")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Voiceover Toolkit (emmydrain 2025)")
        self.setGeometry(100, 100, 1000, 700)
        self.setup_ui()
        self.setup_style()
        self.current_game_path = ""
        self.audio_files = {}
        self.vlc_instance = vlc.Instance()
        self.vlc_player = self.vlc_instance.media_player_new()
        self.mod_profiles = {}
        self.load_profiles()

    def setup_ui(self):
        self.tabs = QTabWidget()
        
        # Вкладка основного функционала
        self.main_tab = QWidget()
        self.setup_main_tab()
        
        # Вкладка управления модами
        self.mods_tab = QWidget()
        self.setup_mods_tab()
        
        self.tabs.addTab(self.main_tab, "Основной функционал")
        self.tabs.addTab(self.mods_tab, "Управление модами")
        
        self.setCentralWidget(self.tabs)

    def setup_main_tab(self):
        layout = QVBoxLayout()

        # Группа выбора игры
        game_group = QGroupBox("Выбор игры")
        game_layout = QVBoxLayout()
        
        self.game_path_label = QLabel("Путь к игре: Не выбран")
        self.btn_select_game = QPushButton("Выбрать игру")
        self.btn_scan_audio = QPushButton("Сканировать аудиофайлы")
        
        game_layout.addWidget(self.game_path_label)
        game_layout.addWidget(self.btn_select_game)
        game_layout.addWidget(self.btn_scan_audio)
        game_group.setLayout(game_layout)

        # Группа аудиофайлов
        audio_group = QGroupBox("Управление аудио")
        audio_layout = QVBoxLayout()
        
        self.original_audio_list = QListWidget()
        self.original_audio_list.itemDoubleClicked.connect(self.play_original_audio)
        self.replacement_audio_list = QListWidget()
        
        self.btn_add_replacement = QPushButton("Добавить замену")
        self.btn_remove_replacement = QPushButton("Удалить замену")
        self.btn_preview_replacement = QPushButton("Прослушать замену")
        
        audio_buttons_layout = QHBoxLayout()
        audio_buttons_layout.addWidget(self.btn_add_replacement)
        audio_buttons_layout.addWidget(self.btn_remove_replacement)
        audio_buttons_layout.addWidget(self.btn_preview_replacement)
        
        audio_layout.addWidget(QLabel("Оригинальные файлы:"))
        audio_layout.addWidget(self.original_audio_list)
        audio_layout.addWidget(QLabel("Файлы для замены:"))
        audio_layout.addWidget(self.replacement_audio_list)
        audio_layout.addLayout(audio_buttons_layout)
        audio_group.setLayout(audio_layout)

        # Группа обработки
        process_group = QGroupBox("Обработка")
        process_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Готово к работе")
        self.btn_process = QPushButton("Применить изменения")
        
        process_layout.addWidget(self.progress_bar)
        process_layout.addWidget(self.status_label)
        process_layout.addWidget(self.btn_process)
        process_group.setLayout(process_layout)

        layout.addWidget(game_group)
        layout.addWidget(audio_group)
        layout.addWidget(process_group)
        self.main_tab.setLayout(layout)

        # Подключение сигналов
        self.btn_select_game.clicked.connect(self.select_game)
        self.btn_scan_audio.clicked.connect(self.scan_audio_files)
        self.btn_add_replacement.clicked.connect(self.add_replacement)
        self.btn_remove_replacement.clicked.connect(self.remove_replacement)
        self.btn_preview_replacement.clicked.connect(self.preview_replacement)
        self.btn_process.clicked.connect(self.process_audio)

    def setup_mods_tab(self):
        layout = QVBoxLayout()

        # Группа профилей
        profile_group = QGroupBox("Профили модов")
        profile_layout = QVBoxLayout()
        
        self.profile_combo = QComboBox()
        self.profile_combo.currentTextChanged.connect(self.load_profile)
        
        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.setPlaceholderText("Название профиля")
        
        self.btn_save_profile = QPushButton("Сохранить профиль")
        self.btn_delete_profile = QPushButton("Удалить профиль")
        
        profile_buttons_layout = QHBoxLayout()
        profile_buttons_layout.addWidget(self.btn_save_profile)
        profile_buttons_layout.addWidget(self.btn_delete_profile)
        
        profile_layout.addWidget(QLabel("Текущие профили:"))
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(QLabel("Новый профиль:"))
        profile_layout.addWidget(self.profile_name_edit)
        profile_layout.addLayout(profile_buttons_layout)
        profile_group.setLayout(profile_layout)

        # Группа пакетной обработки
        batch_group = QGroupBox("Пакетная обработка")
        batch_layout = QVBoxLayout()
        
        self.batch_progress = QProgressBar()
        self.batch_status = QLabel("Выберите профили для обработки")
        
        self.profiles_to_process = QListWidget()
        self.profiles_to_process.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        self.btn_add_to_batch = QPushButton("Добавить в пакет")
        self.btn_remove_from_batch = QPushButton("Удалить из пакета")
        self.btn_run_batch = QPushButton("Выполнить пакетную обработку")
        
        batch_buttons_layout = QHBoxLayout()
        batch_buttons_layout.addWidget(self.btn_add_to_batch)
        batch_buttons_layout.addWidget(self.btn_remove_from_batch)
        
        batch_layout.addWidget(self.batch_progress)
        batch_layout.addWidget(self.batch_status)
        batch_layout.addWidget(QLabel("Профили в пакете:"))
        batch_layout.addWidget(self.profiles_to_process)
        batch_layout.addLayout(batch_buttons_layout)
        batch_layout.addWidget(self.btn_run_batch)
        batch_group.setLayout(batch_layout)

        layout.addWidget(profile_group)
        layout.addWidget(batch_group)
        self.mods_tab.setLayout(layout)

        # Подключение сигналов
        self.btn_save_profile.clicked.connect(self.save_profile)
        self.btn_delete_profile.clicked.connect(self.delete_profile)
        self.btn_add_to_batch.clicked.connect(self.add_to_batch)
        self.btn_remove_from_batch.clicked.connect(self.remove_from_batch)
        self.btn_run_batch.clicked.connect(self.run_batch_processing)

    def setup_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-size: 14px; }
            QPushButton {
                background-color: #4CAF50; color: white; border: none;
                padding: 8px; font-size: 13px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #45a049; }
            QListWidget, QLineEdit, QComboBox {
                background-color: #3c3c3c; color: #ffffff;
                border: 1px solid #555; padding: 5px;
            }
            QGroupBox {
                border: 1px solid #555; border-radius: 5px;
                margin-top: 10px; color: #ffffff;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; }
            QProgressBar {
                border: 1px solid #444; border-radius: 3px;
                text-align: center; color: white;
            }
            QProgressBar::chunk { background-color: #4CAF50; }
        """)

    def select_game(self):
        path = QFileDialog.getExistingDirectory(self, "Выберите папку с игрой")
        if path:
            self.current_game_path = path
            self.game_path_label.setText(f"Путь к игре: {path}")
            self.original_audio_list.clear()
            self.replacement_audio_list.clear()
            self.status_label.setText("Выбрана новая игра. Нажмите 'Сканировать аудиофайлы'")

    def scan_audio_files(self):
        if not self.current_game_path:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку с игрой!")
            return

        self.scanner = AudioScanner(self.current_game_path)
        self.scanner.scan_complete.connect(self.on_scan_complete)
        self.scanner.progress_updated.connect(self.progress_bar.setValue)
        self.status_label.setText("Сканирование аудиофайлов...")
        self.scanner.start()

    def on_scan_complete(self, audio_files):
        self.audio_files = audio_files
        self.original_audio_list.clear()
        for rel_path in audio_files.keys():
            self.original_audio_list.addItem(rel_path)
        self.status_label.setText(f"Найдено {len(audio_files)} аудиофайлов")
        self.progress_bar.setValue(0)

    def add_replacement(self):
        selected_items = self.original_audio_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Выберите файл для замены!")
            return

        original_rel = selected_items[0].text()
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите аудиофайл для замены", "", 
            "Аудио (*.mp3 *.wav *.ogg *.flac)"
        )
        
        if files:
            self.replacement_audio_list.addItem(f"{original_rel} -> {files[0]}")
            self.status_label.setText(f"Добавлена замена для {original_rel}")

    def remove_replacement(self):
        selected_items = self.replacement_audio_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Выберите замену для удаления!")
            return

        for item in selected_items:
            self.replacement_audio_list.takeItem(self.replacement_audio_list.row(item))
        self.status_label.setText("Замена удалена")

    def play_original_audio(self, item):
        rel_path = item.text()
        full_path = self.audio_files[rel_path]
        
        try:
            media = self.vlc_instance.media_new(full_path)
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self.status_label.setText(f"Воспроизведение: {rel_path}")
        except Exception as e:
            self.status_label.setText(f"Ошибка воспроизведения: {str(e)}")

    def preview_replacement(self):
        selected_items = self.replacement_audio_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Выберите замену для прослушивания!")
            return

        replacement_path = selected_items[0].text().split(" -> ")[1]
        
        try:
            media = self.vlc_instance.media_new(replacement_path)
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self.status_label.setText(f"Воспроизведение замены: {os.path.basename(replacement_path)}")
        except Exception as e:
            self.status_label.setText(f"Ошибка воспроизведения: {str(e)}")

    def process_audio(self):
        if not self.current_game_path:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите папку с игрой!")
            return

        if self.replacement_audio_list.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Нет файлов для замены!")
            return

        replacements = {}
        for i in range(self.replacement_audio_list.count()):
            text = self.replacement_audio_list.item(i).text()
            original_rel, replacement_path = text.split(" -> ")
            replacements[original_rel] = replacement_path

        task = {
            'game_path': self.current_game_path,
            'replacements': replacements
        }

        self.processor = AudioProcessor([task])
        self.processor.progress_updated.connect(self.progress_bar.setValue)
        self.processor.status_message.connect(self.status_label.setText)
        self.processor.finished.connect(self.on_processing_finished)
        self.processor.start()
        self.status_label.setText("Начата обработка...")

    def on_processing_finished(self):
        QMessageBox.information(self, "Готово", "Все аудиофайлы успешно заменены!")
        self.progress_bar.setValue(0)

    # Функции для работы с профилями модов
    def load_profiles(self):
        try:
            with open('mod_profiles.json', 'r') as f:
                self.mod_profiles = json.load(f)
            self.profile_combo.clear()
            self.profile_combo.addItems(self.mod_profiles.keys())
        except (FileNotFoundError, json.JSONDecodeError):
            self.mod_profiles = {}

    def save_profile(self):
        profile_name = self.profile_name_edit.text()
        if not profile_name:
            QMessageBox.warning(self, "Ошибка", "Введите название профиля!")
            return

        if not self.current_game_path:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите игру!")
            return

        replacements = {}
        for i in range(self.replacement_audio_list.count()):
            text = self.replacement_audio_list.item(i).text()
            original_rel, replacement_path = text.split(" -> ")
            replacements[original_rel] = replacement_path

        self.mod_profiles[profile_name] = {
            'game_path': self.current_game_path,
            'replacements': replacements
        }

        with open('mod_profiles.json', 'w') as f:
            json.dump(self.mod_profiles, f)

        self.profile_combo.addItem(profile_name)
        self.profile_name_edit.clear()
        self.status_label.setText(f"Профиль '{profile_name}' сохранен")

    def load_profile(self, profile_name):
        if profile_name in self.mod_profiles:
            profile = self.mod_profiles[profile_name]
            self.current_game_path = profile['game_path']
            self.game_path_label.setText(f"Путь к игре: {self.current_game_path}")
            
            self.replacement_audio_list.clear()
            for original_rel, replacement_path in profile['replacements'].items():
                self.replacement_audio_list.addItem(f"{original_rel} -> {replacement_path}")
            
            self.status_label.setText(f"Загружен профиль '{profile_name}'")

    def delete_profile(self):
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            return

        reply = QMessageBox.question(
            self, "Подтверждение", 
            f"Удалить профиль '{profile_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.mod_profiles.pop(profile_name)
            with open('mod_profiles.json', 'w') as f:
                json.dump(self.mod_profiles, f)
            
            self.profile_combo.removeItem(self.profile_combo.currentIndex())
            self.status_label.setText(f"Профиль '{profile_name}' удален")

    # Функции пакетной обработки
    def add_to_batch(self):
        selected_items = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())
                         if self.profile_combo.itemText(i) not in 
                         [self.profiles_to_process.item(i).text() for i in range(self.profiles_to_process.count())]]
        
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Нет доступных профилей для добавления!")
            return

        item, ok = QInputDialog.getItem(
            self, "Добавить в пакет", "Выберите профиль:", selected_items, 0, False
        )
        
        if ok and item:
            self.profiles_to_process.addItem(item)

    def remove_from_batch(self):
        selected_items = self.profiles_to_process.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Ошибка", "Выберите профили для удаления!")
            return

        for item in selected_items:
            self.profiles_to_process.takeItem(self.profiles_to_process.row(item))

    def run_batch_processing(self):
        if self.profiles_to_process.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Нет профилей для обработки!")
            return

        tasks = []
        for i in range(self.profiles_to_process.count()):
            profile_name = self.profiles_to_process.item(i).text()
            tasks.append(self.mod_profiles[profile_name])

        self.batch_processor = AudioProcessor(tasks)
        self.batch_processor.progress_updated.connect(self.batch_progress.setValue)
        self.batch_processor.status_message.connect(self.batch_status.setText)
        self.batch_processor.finished.connect(self.on_batch_complete)
        self.batch_processor.start()
        self.batch_status.setText("Пакетная обработка начата...")

    def on_batch_complete(self):
        QMessageBox.information(self, "Готово", "Пакетная обработка завершена!")
        self.batch_progress.setValue(0)
        self.batch_status.setText("Готово к новой обработке")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())