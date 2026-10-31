from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from src.ui.widgets.sidebar import Sidebar
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.projects_view import ProjectsView
from src.ui.views.activity_view import ActivityView
from src.ui.views.settings_view import SettingsView
from src.ui.views.global_activities_view import GlobalActivitiesView
from src.utils.styles import get_base_qss

from src.ui.widgets.about_dialog import AboutDialog

class MainWindow(QMainWindow):
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        
        self.setWindowTitle("Project Opener")
        self.resize(1200, 800)
        self.setStyleSheet(get_base_qss())
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self.switch_page)
        self.sidebar.show_about_requested.connect(self.show_about)
        main_layout.addWidget(self.sidebar)
        
        # Page Container
        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages)
        
        self._init_pages()

    def _init_pages(self):

        # 0: Dashboard
        self.pages.addWidget(DashboardView(self.config_manager))
        
        # 1: My Projects (Local)
        self.view_local = ProjectsView(self.config_manager, mode="local")
        self.view_local.project_selected.connect(self.open_activity_view)
        self.pages.addWidget(self.view_local)
        
        # 2: Explore Shared
        self.view_net = ProjectsView(self.config_manager, mode="shared")
        self.view_net.project_selected.connect(self.open_activity_view)
        self.pages.addWidget(self.view_net)

        # 3: Global Activities (Sidebar "Activities" Link)
        self.pages.addWidget(GlobalActivitiesView(self.config_manager))
        
        # 4: Settings
        self.pages.addWidget(SettingsView(self.config_manager))

        # 5: Activity Details View (Hidden, accessed via Projects)
        self.activity_view = ActivityView(self.config_manager)
        self.activity_view.back_requested.connect(self.go_back)
        self.pages.addWidget(self.activity_view)

    def switch_page(self, index):
        # Allow default switching for sidebar items 0-4
        if index < 5:
            # Refresh if it's the Global Activities view
            widget = self.pages.widget(index)
            if hasattr(widget, "refresh"):
                widget.refresh()
                
            self.last_page_index = index # Remember where we came from
            self.pages.setCurrentIndex(index)
        
    def open_activity_view(self, project_name):
        self.activity_view.load_project(project_name)
        self.pages.setCurrentIndex(5) # Switch to Activity Details View
        
    def go_back(self):
        self.pages.setCurrentIndex(self.last_page_index)

    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

