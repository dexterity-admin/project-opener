import os
import json
import shutil
import getpass
from pathlib import Path

# Constants
APP_NAME = "ProjectOpenerEngine"
DEFAULT_LOCAL_PATH = os.getcwd() 
LOCAL_SETTINGS_FILE = "settings.json"

class ConfigManager:
    def __init__(self):
        self.app_dir = DEFAULT_LOCAL_PATH
        self.username = getpass.getuser()
        self.settings = {}
        self.local_projects = {"projects": {}}
        self.variables = {} 
        
        self._ensure_app_dir()
        self.load_all()

    def _ensure_app_dir(self):
        if not os.path.exists(self.app_dir):
            os.makedirs(self.app_dir)

    def load_all(self):
        # 1. Load basic settings (Paths & Variables)
        self.settings = self._load_json(LOCAL_SETTINGS_FILE, default={
            "server_path": os.path.join(self.app_dir, "shared_hub"),
            "variables": {
                "{SERVER_ROOT}": os.path.join(self.app_dir, "shared_hub")
            }
        })
        self.variables = self.settings.get("variables", {})
        
        # Ensure server directory exists
        server_path = self.settings.get("server_path")
        if server_path and not os.path.exists(server_path):
            try: os.makedirs(server_path)
            except: pass

        # 2. Load CURRENT USER'S projects from the server hub
        user_file = f"{self.username}.json"
        user_path = os.path.join(server_path, user_file)
        
        if os.path.exists(user_path):
            self.local_projects = self._load_json_path(user_path)
        else:
            # First time user or first time on server
            self.local_projects = {"projects": {}}
            self.save_local_projects() # Create it

    def _load_json(self, filename, default=None):
        path = os.path.join(self.app_dir, filename)
        return self._load_json_path(path, default)

    def _load_json_path(self, path, default=None):
        if not os.path.exists(path):
            return default or {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return default or {}

    def save_local_projects(self):
        server_path = self.settings.get("server_path")
        if not server_path: return
        
        user_path = os.path.join(server_path, f"{self.username}.json")
        self._save_json_path(user_path, self.local_projects)

    def save_settings(self):
        self.settings["variables"] = self.variables
        self._save_json_path(os.path.join(self.app_dir, LOCAL_SETTINGS_FILE), self.settings)

    def _save_json_path(self, path, data):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving {path}: {e}")

    def get_all_projects(self):
        """Returns current user's projects."""
        projs = []
        for name, data in self.local_projects.get("projects", {}).items():
            projs.append({
                "name": name,
                "data": data,
                "source": "local",
                "locked": False,
                "author": self.username
            })
        return projs

    def get_shared_projects(self):
        """Scans the server path for OTHER users' projects."""
        shared = []
        server_path = self.settings.get("server_path")
        if not server_path or not os.path.exists(server_path):
            return shared

        for filename in os.listdir(server_path):
            if filename.endswith(".json") and filename != f"{self.username}.json":
                author = filename.replace(".json", "")
                data = self._load_json_path(os.path.join(server_path, filename))
                
                projs = data.get("projects", {})
                for p_name, p_data in projs.items():
                    shared.append({
                        "name": p_name,
                        "data": p_data,
                        "source": "shared",
                        "locked": True, # Shared ones are read-only until cloned
                        "author": author
                    })
        return shared

    def clone_project(self, project_data):
        """Copies a shared project to local list."""
        name = project_data["name"]
        # Avoid overwriting directly if name exists
        if name in self.local_projects["projects"]:
            name = f"{name} (Copy)"
            
        new_data = json.loads(json.dumps(project_data["data"])) # Deep copy
        self.local_projects["projects"][name] = new_data
        self.save_local_projects()
        return name

    def set_variable(self, key, value):
        key = key.upper()
        if not key.startswith("{"): key = "{" + key
        if not key.endswith("}"): key = key + "}"
        self.variables[key] = value
        self.save_settings()

    def set_server_path(self, path):
        self.settings["server_path"] = path
        self.save_settings()
        self.load_all() # Reload from new server path
