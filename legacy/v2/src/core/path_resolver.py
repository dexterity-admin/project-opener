import os

class PathResolver:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    def resolve(self, path_str):
        """
        Replaces variables in the path string with values from config.
        Example: "{CAD_ROOT}/ProjectA" -> "Z:/CAD/ProjectA"
        """
        if not path_str or not isinstance(path_str, str):
            return path_str

        # Get current variables
        variables = self.config_manager.variables

        resolved_path = path_str
        for key, value in variables.items():
            # Variables are stored as "{KEY}" in config
            if key in resolved_path:
                resolved_path = resolved_path.replace(key, value)
        
        # Normalize separators
        return os.path.normpath(resolved_path)

    def validate(self, path_str):
        """Checks if the resolved path actually exists."""
        resolved = self.resolve(path_str)
        return os.path.exists(resolved), resolved
