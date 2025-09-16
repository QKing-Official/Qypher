import sys
import os
import json
import requests
import zipfile
import io
import shutil
import webbrowser
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QListWidget, QPushButton, QLabel, 
                               QSystemTrayIcon, QMenu, QStyle, QMessageBox, QProgressBar,
                               QComboBox, QCheckBox, QFrame, QStackedWidget, QSizePolicy,
                               QListWidgetItem, QLineEdit, QDialog, QDialogButtonBox, QFormLayout)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QSettings, QStandardPaths
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction, QPalette, QGuiApplication

# Configuration
APP_NAME = "Qypher Launcher"
ORGANIZATION = "QKing-Official"
DEFAULT_REPO_URL = "https://github.com/QKing-Official/Qypher-Manifest"
DEFAULT_MANIFEST_URL = f"{DEFAULT_REPO_URL}/raw/refs/heads/main/manifest.json"
LAUNCHER_REPO_URL = "https://github.com/QKing-Official/Qypher"
DEFAULT_INSTALL_DIR = os.path.join(os.environ.get("APPDATA", ""), "Qypher", "Apps")
ICON_CACHE = os.path.join(os.environ.get("APPDATA", ""), "Qypher", "icons")
LAUNCHER_VERSION = "v1.0.0"

# Ensure directories exist
Path(DEFAULT_INSTALL_DIR).mkdir(parents=True, exist_ok=True)
Path(ICON_CACHE).mkdir(parents=True, exist_ok=True)

class CustomRepoDialog(QDialog):
    def __init__(self, parent=None, current_repo=""):
        super().__init__(parent)
        self.setWindowTitle("Custom Manifest Repository")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.repo_edit = QLineEdit(current_repo)
        self.repo_edit.setPlaceholderText("https://github.com/user/repo")
        form_layout.addRow("Repository URL:", self.repo_edit)
        
        layout.addLayout(form_layout)
        
        info_label = QLabel("The repository should contain a 'manifest.json' file in the main branch.")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.check_self_update()
        self.check_manifest_updates()
    
    def get_repo_url(self):
        return self.repo_edit.text().strip()

class DownloadThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)
    info = Signal(str)

    def __init__(self, url, destination):
        super().__init__()
        self.url = url
        self.destination = destination

        def run(self):
            try:
                self.info.emit(f"Downloading {os.path.basename(self.destination)}...")
                response = requests.get(self.url, stream=True)
                total_size = int(response.headers.get('content-length', 0))
                
                with open(self.destination, 'wb') as f:
                    downloaded = 0
                    for data in response.iter_content(chunk_size=4096):
                        f.write(data)
                        downloaded += len(data)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress.emit(progress)
                
                self.info.emit("Download completed!")
                self.finished.emit(True, "")
            except Exception as e:
                self.finished.emit(False, str(e))

class ManifestUpdateThread(QThread):
    finished = Signal(bool, str, dict)
    info = Signal(str)

    def __init__(self, manifest_url):
        super().__init__()
        self.manifest_url = manifest_url

    def run(self):
        try:
            self.info.emit("Checking for manifest updates...")
            response = requests.get(self.manifest_url, timeout=10)
            if response.status_code == 200:
                manifest_data = response.json()
                self.info.emit("Manifest loaded successfully!")
                self.finished.emit(True, "", manifest_data)
            else:
                self.finished.emit(False, f"HTTP {response.status_code}", {})
        except Exception as e:
            self.finished.emit(False, str(e), {})

class SelfUpdateThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)
    info = Signal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        try:
            self.info.emit("Checking for launcher updates...")
            
            # Get latest release from GitHub API
            api_url = f"https://api.github.com/repos/QKing-Official/Qypher/releases/latest"
            response = requests.get(api_url, timeout=10)
            
            if response.status_code != 200:
                self.finished.emit(False, "Failed to check for updates")
                return
            
            release_data = response.json()
            latest_version = release_data.get('tag_name', '')
            
            exe_asset = None
            for asset in release_data.get('assets', []):
                if asset['name'].endswith('.exe'):
                    exe_asset = asset
                    break
            
            if not exe_asset:
                self.finished.emit(False, "No executable found in latest release")
                return
            
            self.info.emit(f"Downloading launcher update {latest_version}...")
            self.progress.emit(25)
            
            # Download the new exe
            current_exe = sys.executable
            current_dir = os.path.dirname(current_exe)
            temp_exe = os.path.join(current_dir, "qypher_launcher_new.exe")
            
            download_response = requests.get(exe_asset['browser_download_url'], stream=True)
            total_size = int(download_response.headers.get('content-length', 0))
            
            with open(temp_exe, 'wb') as f:
                downloaded = 0
                for data in download_response.iter_content(chunk_size=4096):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        progress = 25 + int((downloaded / total_size) * 50)
                        self.progress.emit(progress)
            
            self.progress.emit(75)
            self.info.emit("Preparing to restart...")
            
            # Create update script
            update_script = os.path.join(current_dir, "update_launcher.bat")
            script_content = f'''@echo off
timeout /t 2 /nobreak >nul
del "{current_exe}"
ren "{temp_exe}" "{os.path.basename(current_exe)}"
start "" "{current_exe}"
del "%~f0"
'''
            
            with open(update_script, 'w') as f:
                f.write(script_content)
            
            self.progress.emit(100)
            self.info.emit("Update ready! Restarting launcher...")
            
            # Start the update script and exit
            subprocess.Popen([update_script], shell=True)
            
            self.finished.emit(True, "Update completed")
            
        except Exception as e:
            self.finished.emit(False, str(e))

class InstallThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str, str)
    info = Signal(str)

    def __init__(self, app_data, version, install_dir):
        super().__init__()
        self.app_data = app_data
        self.version = version
        self.install_dir = install_dir
        self.actual_version = version

    def run(self):
        try:
            app_name = self.app_data['name']
            app_dir = os.path.join(self.install_dir, app_name)
            
            Path(app_dir).mkdir(parents=True, exist_ok=True)
                        
            download_url = self.app_data['url']

            if self.version == "latest":
                releases = get_github_releases(self.app_data['url'])
                if releases and len(releases) > 0:
                    self.actual_version = releases[0].get('tag_name', 'latest')
                    self.info.emit(f"Latest version resolved to: {self.actual_version}")

            if self.version != "latest":
                filename = download_url.split('/')[-1]
                parts = download_url.split('/releases/latest/download/')
                if len(parts) == 2:
                    base_url = parts[0]
                    download_url = f"{base_url}/releases/download/{self.version}/{filename}"
            
            # Download the file
            file_extension = download_url.split('.')[-1].lower()
            download_filename = f"{app_name}_{self.actual_version}.{file_extension}"
            download_path = os.path.join(app_dir, download_filename)
            
            self.info.emit(f"Downloading {app_name} {self.actual_version}...")
            
            response = requests.get(download_url, stream=True)
            
            if response.status_code != 200:
                raise Exception(f"Download failed with status code: {response.status_code}")
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(download_path, 'wb') as f:
                downloaded = 0
                for data in response.iter_content(chunk_size=4096):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 50)
                        self.progress.emit(progress)
            
            if file_extension == 'zip':
                self.info.emit("Extracting files...")
                self.progress.emit(75)
                with zipfile.ZipFile(download_path, 'r') as zip_ref:
                    zip_ref.extractall(app_dir)
                os.remove(download_path)
            
            self.progress.emit(90)
            
            app_manifest_path = os.path.join(app_dir, "app_info.json")
            app_info = {
                'name': app_name,
                'version': self.actual_version,
                'installed_path': app_dir,
                'executable': self.app_data.get('filename', ''),
                'install_date': str(Path().resolve())
            }
            
            with open(app_manifest_path, 'w') as f:
                json.dump(app_info, f, indent=4)
            
            self.progress.emit(100)
            self.info.emit("Installation completed!")
            self.finished.emit(True, "", self.actual_version)
            
        except Exception as e:
            self.finished.emit(False, str(e), self.actual_version)

def get_github_releases(repo_url):
    try:
        if "github.com" in repo_url:
            parts = repo_url.split("github.com/")[1].split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    releases = response.json()
                    return releases
        return None
    except:
        return None

def is_version_newer(latest_version, current_version):
    """Compare versions to determine if an update is available"""
    if latest_version == "latest" or current_version == "latest":
        return False
    
    latest = latest_version.lstrip('v')
    current = current_version.lstrip('v')
    
    try:
        latest_parts = [int(x) for x in latest.split('.')]
        current_parts = [int(x) for x in current.split('.')]
        
        max_len = max(len(latest_parts), len(current_parts))
        latest_parts.extend([0] * (max_len - len(latest_parts)))
        current_parts.extend([0] * (max_len - len(current_parts)))
        
        return latest_parts > current_parts
    except:
        return latest != current

# Main application window
class QypherLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORGANIZATION, APP_NAME)
        self.install_dir = self.settings.value("install_dir", DEFAULT_INSTALL_DIR)
        
        self.manifest_repo_url = self.settings.value("manifest_repo", DEFAULT_REPO_URL)
        self.manifest_url = f"{self.manifest_repo_url}/raw/refs/heads/main/manifest.json"
        
        self.dark_mode = self.is_system_dark_theme()
        self.settings.setValue("dark_mode", self.dark_mode)
        
        self.manifest_data = None
        self.installed_apps = {}
        self.download_thread = None
        self.install_thread = None
        self.manifest_update_thread = None
        self.self_update_thread = None
        
        self.app_icon = self.create_icon()
        self.setWindowIcon(self.app_icon)
        
        self.setup_ui()
        self.load_manifest()
        self.scan_installed_apps()
        self.setup_tray_icon()
        
        # Apply theme
        self.apply_theme()
    
    def is_system_dark_theme(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        except:
            palette = QGuiApplication.palette()
            return palette.window().color().lightness() < 128
    
    def setup_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(800, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        
        self.refresh_btn = QPushButton("Check for Updates")
        self.refresh_btn.clicked.connect(self.check_manifest_updates)
        self.refresh_btn.setToolTip("Check for manifest and application updates")
        
        self.custom_repo_btn = QPushButton("Custom Repo")
        self.custom_repo_btn.clicked.connect(self.set_custom_repo)
        self.custom_repo_btn.setToolTip("Set custom manifest repository")
        
        self.self_update_btn = QPushButton("Update Launcher")
        self.self_update_btn.clicked.connect(self.check_self_update)
        self.self_update_btn.setToolTip("Check for launcher updates")
        
        self.theme_toggle = QPushButton("Toggle Theme")
        self.theme_toggle.clicked.connect(self.toggle_theme)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.refresh_btn)
        header.addWidget(self.custom_repo_btn)
        header.addWidget(self.self_update_btn)
        header.addWidget(self.theme_toggle)
        layout.addLayout(header)
        
        self.update_status_label = QLabel()
        self.update_status_label.setVisible(False)
        self.update_status_label.setStyleSheet("color: #2a82da; font-weight: bold;")
        layout.addWidget(self.update_status_label)
        
        content = QHBoxLayout()
        
        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(0, 0, 10, 0)
        
        available_label = QLabel("Available Applications")
        available_label.setStyleSheet("font-weight: bold;")
        left_panel.addWidget(available_label)
        
        self.available_list = QListWidget()
        self.available_list.currentRowChanged.connect(self.on_app_selected)
        self.available_list.itemDoubleClicked.connect(self.on_app_double_clicked)
        left_panel.addWidget(self.available_list)
        
        content.addLayout(left_panel, 2)
        
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(10, 0, 0, 0)
        
        details_label = QLabel("Application Details")
        details_label.setStyleSheet("font-weight: bold;")
        right_panel.addWidget(details_label)
        
        self.details_frame = QFrame()
        self.details_frame.setFrameStyle(QFrame.StyledPanel)
        self.details_frame.setVisible(False)
        details_layout = QVBoxLayout(self.details_frame)
        
        self.app_name = QLabel()
        self.app_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(self.app_name)
        
        self.app_desc = QLabel()
        self.app_desc.setWordWrap(True)
        details_layout.addWidget(self.app_desc)
        
        self.app_version = QLabel()
        details_layout.addWidget(self.app_version)
        
        details_layout.addSpacing(10)
        
        version_layout = QHBoxLayout()
        version_layout.addWidget(QLabel("Version:"))
        self.version_combo = QComboBox()
        version_layout.addWidget(self.version_combo)
        details_layout.addLayout(version_layout)
        
        button_layout = QHBoxLayout()
        self.install_btn = QPushButton("Install")
        self.install_btn.clicked.connect(self.install_app)
        button_layout.addWidget(self.install_btn)
        
        self.launch_btn = QPushButton("Launch")
        self.launch_btn.clicked.connect(self.launch_app)
        button_layout.addWidget(self.launch_btn)
        
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.clicked.connect(self.uninstall_app)
        button_layout.addWidget(self.uninstall_btn)
        
        details_layout.addLayout(button_layout)
        
        right_panel.addWidget(self.details_frame)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_panel.addWidget(self.progress_bar)
        
        self.status_label = QLabel()
        self.status_label.setVisible(False)
        right_panel.addWidget(self.status_label)
        
        right_panel.addStretch()
        content.addLayout(right_panel, 3)
        
        layout.addLayout(content)
        
        installed_label = QLabel("Installed Applications")
        installed_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(installed_label)
        
        self.installed_list = QListWidget()
        self.installed_list.currentRowChanged.connect(self.on_installed_app_selected)
        layout.addWidget(self.installed_list)
    
    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.app_icon)
        
        tray_menu = QMenu()
        
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: palette(window);
                border: 1px solid palette(mid);
            }
            QMenu::item {
                background-color: transparent;
                padding: 5px 20px 5px 10px;
                color: palette(window-text);
            }
            QMenu::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }
        """)
        
        show_action = QAction("Show Launcher", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("Hide Launcher", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        update_action = QAction("Check for Updates", self)
        update_action.triggered.connect(self.check_manifest_updates)
        tray_menu.addAction(update_action)
        
        self_update_action = QAction("Update Launcher", self)
        self_update_action.triggered.connect(self.check_self_update)
        tray_menu.addAction(self_update_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
    
    def create_icon(self): # I'm a programmer, not an artist
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setBrush(Qt.black)
        painter.drawEllipse(4, 4, 56, 56)
        
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 40, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "Q")
        
        painter.end()
        
        return QIcon(pixmap)
    
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
    
    def set_custom_repo(self):
        """Set custom manifest repository"""
        dialog = CustomRepoDialog(self, self.manifest_repo_url)
        if dialog.exec() == QDialog.Accepted:
            new_repo = dialog.get_repo_url()
            if new_repo:
                self.manifest_repo_url = new_repo
                self.manifest_url = f"{new_repo}/raw/refs/heads/main/manifest.json"
                self.settings.setValue("manifest_repo", new_repo)
                
                self.load_manifest()
                QMessageBox.information(self, "Repository Updated", f"Manifest repository updated to:\n{new_repo}")
    
    def check_self_update(self):
        """Check for launcher updates"""
        if self.self_update_thread and self.self_update_thread.isRunning():
            return

        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Checking for launcher updates...")

        current_version = "v1.0.0"
        self.self_update_thread = SelfUpdateThread(current_version=current_version)

        self.self_update_thread.progress.connect(self.progress_bar.setValue)
        self.self_update_thread.info.connect(self.status_label.setText)
        self.self_update_thread.finished.connect(self.self_update_finished)
        self.self_update_thread.update_available.connect(self.show_launcher_update_notification)

        self.self_update_thread.start()

    def show_launcher_update_notification(self, latest_version):
        """Show tray notification when a new launcher version is available"""
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                "Launcher Update Available",
                f"A new launcher version ({latest_version}) is available!",
                QSystemTrayIcon.Information,
                5000
            )

        
    def self_update_finished(self, success, message):
        """Handle completion of self-update"""
        self.set_buttons_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Update Complete", "Launcher will restart with the new version.")
            QApplication.quit()
        else:
            QMessageBox.critical(self, "Update Failed", f"Failed to update launcher: {message}")
    
    def check_manifest_updates(self):
        """Manually check for manifest updates"""
        if self.manifest_update_thread and self.manifest_update_thread.isRunning():
            return
        
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Checking...")
        self.update_status_label.setVisible(True)
        self.update_status_label.setText("Checking for updates...")
        
        self.manifest_update_thread = ManifestUpdateThread(self.manifest_url)
        self.manifest_update_thread.info.connect(self.update_status_label.setText)
        self.manifest_update_thread.finished.connect(self.manifest_update_finished)
        self.manifest_update_thread.start()
    
    def manifest_update_finished(self, success, error_message, new_manifest_data):
        """Handle completion of manifest update check"""
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Check for Updates")
        
        if success and new_manifest_data:
            manifest_changed = False
            if self.manifest_data != new_manifest_data:
                manifest_changed = True
                self.manifest_data = new_manifest_data
            
            self.populate_available_apps()
            current_row = self.available_list.currentRow()
            if current_row >= 0:
                self.on_app_selected(current_row)
            
            update_count = 0
            if self.manifest_data and 'applications' in self.manifest_data:
                for app in self.manifest_data['applications']:
                    app_name = app['name']
                    if app_name in self.installed_apps:
                        latest_version = self.get_latest_version(app)
                        installed_version = self.installed_apps[app_name]['version']
                        if latest_version and is_version_newer(latest_version, installed_version):
                            update_count += 1
            
            if update_count > 0:
                self.update_status_label.setText(f"{update_count} update(s) available!")
                self.update_status_label.setStyleSheet("color: #2a82da; font-weight: bold;")
                
                if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                    self.tray_icon.showMessage(
                        "Updates Available",
                        f"{update_count} application update(s) available",
                        QSystemTrayIcon.Information,
                        3000
                    )
            else:
                if manifest_changed:
                    self.update_status_label.setText("Manifest updated, no app updates available")
                else:
                    self.update_status_label.setText("Everything is up to date!")
                self.update_status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            
            self.hide_update_status_timer = self.startTimer(5000)
            
        else:
            self.update_status_label.setText(f"Update check failed: {error_message}")
            self.update_status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.hide_update_status_timer = self.startTimer(3000)
    
    def timerEvent(self, event):
        """Handle timer events"""
        if hasattr(self, 'hide_update_status_timer'):
            self.killTimer(self.hide_update_status_timer)
            self.update_status_label.setVisible(False)
            delattr(self, 'hide_update_status_timer')
    
    def load_manifest(self):
        try:
            response = requests.get(self.manifest_url, timeout=10)
            if response.status_code == 200:
                self.manifest_data = response.json()
                self.populate_available_apps()
            else:
                self.manifest_data = {
                    "applications": [
                        {
                            "name": "No application found",
                            "description": "It seems like you don't have an active internet connection or the manifest failed to load",
                            "url": "https://github.com/QKing-Official",
                            "filename": "-"
                        }
                    ]
                }
                self.populate_available_apps()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load manifest: {str(e)}")
            # Create a minimal manifest as fallback
            self.manifest_data = {
                "applications": [
                        {
                            "name": "No application found",
                            "description": "It seems like you don't have an active internet connection or the manifest failed to load",
                            "url": "https://github.com/QKing-Official",
                            "filename": "-"
                        }
                ]
            }
            self.populate_available_apps()
    
    def populate_available_apps(self):
        self.available_list.clear()
        if self.manifest_data and 'applications' in self.manifest_data:
            for app in self.manifest_data['applications']:
                item = QListWidgetItem()
                app_name = app['name']
                
                if app_name in self.installed_apps:
                    latest_version = self.get_latest_version(app)
                    installed_version = self.installed_apps[app_name]['version']
                    
                    if latest_version and is_version_newer(latest_version, installed_version):
                        display_text = f"{app_name} *"
                        item.setForeground(QColor(42, 130, 218))
                        item.setData(Qt.UserRole, "update_available")
                    else:
                        display_text = app_name
                        item.setData(Qt.UserRole, "up_to_date")
                else:
                    display_text = app_name
                    item.setData(Qt.UserRole, "not_installed")
                
                item.setText(display_text)
                self.available_list.addItem(item)
    
    def get_latest_version(self, app_data):
        try:
            releases = get_github_releases(app_data['url'])
            if releases and len(releases) > 0:
                return releases[0].get('tag_name', 'latest')
            return 'latest'
        except:
            return 'latest'
    
    def scan_installed_apps(self):
        self.installed_apps = {}
        self.installed_list.clear()
        
        install_path = Path(self.install_dir)
        if install_path.exists():
            for app_dir in install_path.iterdir():
                if app_dir.is_dir():
                    manifest_path = app_dir / "app_info.json"
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, 'r') as f:
                                app_info = json.load(f)
                                self.installed_apps[app_info['name']] = app_info
                                self.installed_list.addItem(f"{app_info['name']} (v{app_info['version']})")
                        except:
                            pass
    
    def on_app_selected(self, index):
        if index < 0 or not self.manifest_data:
            self.details_frame.setVisible(False)
            return
        
        item = self.available_list.item(index)
        app_name = item.text().rstrip(' *')
        app_data = None
        
        for app in self.manifest_data['applications']:
            if app['name'] == app_name:
                app_data = app
                break
        
        if app_data:
            self.details_frame.setVisible(True)
            self.app_name.setText(app_data['name'])
            self.app_desc.setText(app_data.get('description', 'No description available'))
            
            self.version_combo.clear()
            self.version_combo.addItem("latest")
            
            releases = get_github_releases(app_data['url'])
            if releases:
                for release in releases:
                    if release.get('tag_name'):
                        self.version_combo.addItem(release['tag_name'])
            
            if app_name in self.installed_apps:
                installed_version = self.installed_apps[app_name]['version']
                latest_version = self.get_latest_version(app_data)
                
                if latest_version and is_version_newer(latest_version, installed_version):
                    self.app_version.setText(f"Installed: v{installed_version} (Update available: v{latest_version})")
                    self.install_btn.setText("Update to Latest")
                    self.install_btn.setStyleSheet("background-color: #2a82da; color: white; font-weight: bold;")
                    self.version_combo.setCurrentText("latest")
                else:
                    self.app_version.setText(f"Installed: v{installed_version} (Up to date)")
                    self.install_btn.setText("Reinstall")
                    self.install_btn.setStyleSheet("")  # Reset style
            else:
                self.app_version.setText("Not installed")
                self.install_btn.setText("Install")
                self.install_btn.setStyleSheet("")  # Reset style
    
    def on_installed_app_selected(self, index):
        if index < 0:
            return
        
        item_text = self.installed_list.item(index).text()
        app_name = item_text.split(" (v")[0]
        
        for i in range(self.available_list.count()):
            item = self.available_list.item(i)
            if item.text().rstrip(' *') == app_name:
                self.available_list.setCurrentRow(i)
                break
    
    def on_app_double_clicked(self, item):
        """Handle double-clicking on an app item"""
        app_name = item.text().rstrip(' *')
        update_status = item.data(Qt.UserRole)
        
        if update_status == "update_available":
            # If update is available, start update
            self.version_combo.setCurrentText("latest")
            self.install_app()
        elif app_name in self.installed_apps:
            # If app is installed, launch it
            self.launch_app()
        else:
            # If not installed, install it
            self.install_app()
    
    def install_app(self):
        current_row = self.available_list.currentRow()
        if current_row < 0:
            return
        
        item = self.available_list.item(current_row)
        app_name = item.text().rstrip(' *')
        version = self.version_combo.currentText()
        
        app_data = None
        for app in self.manifest_data['applications']:
            if app['name'] == app_name:
                app_data = app
                break
        
        if not app_data:
            return
        
        self.set_buttons_enabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing installation...")
        
        self.install_thread = InstallThread(app_data, version, self.install_dir)
        self.install_thread.progress.connect(self.progress_bar.setValue)
        self.install_thread.info.connect(self.status_label.setText)
        self.install_thread.finished.connect(self.installation_finished)
        self.install_thread.start()
    
    def installation_finished(self, success, message, actual_version):
        self.set_buttons_enabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        
        if success:
            self.scan_installed_apps()
            self.populate_available_apps()
            current_row = self.available_list.currentRow()
            if current_row >= 0:
                self.on_app_selected(current_row)
            QMessageBox.information(self, "Success", f"Application installed successfully!\nVersion: {actual_version}")
        else:
            QMessageBox.critical(self, "Error", f"Installation failed: {message}")
    
    def launch_app(self):
        current_row = self.available_list.currentRow()
        if current_row < 0:
            return
        
        item = self.available_list.item(current_row)
        app_name = item.text().rstrip(' *')
        
        if app_name not in self.installed_apps:
            QMessageBox.warning(self, "Not Installed", "This application is not installed.")
            return
        
        app_info = self.installed_apps[app_name]
        executable_path = os.path.join(app_info['installed_path'], app_info.get('executable', ''))
        
        if not os.path.exists(executable_path):
            for file in os.listdir(app_info['installed_path']):
                if file.endswith('.exe'):
                    executable_path = os.path.join(app_info['installed_path'], file)
                    break
        
        if not os.path.exists(executable_path):
            QMessageBox.critical(self, "Error", "Executable not found.")
            return
        
        try:
            os.startfile(executable_path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch application: {str(e)}")
    
    def uninstall_app(self):
        current_row = self.available_list.currentRow()
        if current_row < 0:
            return
        
        item = self.available_list.item(current_row)
        app_name = item.text().rstrip(' *')
        
        if app_name not in self.installed_apps:
            QMessageBox.warning(self, "Not Installed", "This application is not installed.")
            return
        
        reply = QMessageBox.question(
            self, 
            "Confirm Uninstall", 
            f"Are you sure you want to uninstall {app_name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            app_info = self.installed_apps[app_name]
            app_dir = app_info['installed_path']
            
            try:
                shutil.rmtree(app_dir)
                self.scan_installed_apps()
                self.populate_available_apps()
                self.on_app_selected(-1)
                QMessageBox.information(self, "Success", "Application uninstalled successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Uninstall failed: {str(e)}")
    
    def set_buttons_enabled(self, enabled):
        self.install_btn.setEnabled(enabled)
        self.launch_btn.setEnabled(enabled)
        self.uninstall_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.custom_repo_btn.setEnabled(enabled)
        self.self_update_btn.setEnabled(enabled)
    
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.settings.setValue("dark_mode", self.dark_mode)
        self.apply_theme()
    
    def apply_theme(self):
        if self.dark_mode:
            # Dark theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.WindowText, Qt.white)
            palette.setColor(QPalette.Base, QColor(25, 25, 25))
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.white)
            palette.setColor(QPalette.Text, Qt.white)
            palette.setColor(QPalette.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ButtonText, Qt.white)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, Qt.black)
            QApplication.setPalette(palette)
        else:
            # Light theme (default)
            QApplication.setPalette(QApplication.style().standardPalette())
    
    def quit_application(self):
        self.tray_icon.hide()
        QApplication.quit()
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()

# Application entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    launcher = QypherLauncher()
    launcher.show()
    
    sys.exit(app.exec())
