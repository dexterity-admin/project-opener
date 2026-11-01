"""Project Opener - Dexterity Design Services internal workspace launcher.

The package is split into four layers that never reach across each other:

* ``core``   - data model, persistent store, path variables, launcher, search.
* ``lan``    - the Team Hub on a shared folder and LAN presence beacons.
* ``update`` - in-app update checking and installation.
* ``ui``     - everything Qt. Only this layer imports PySide6 widgets.

``__version__`` is the single source of truth for the application version.
The CI workflow reads it to decide whether a push produces a new release.
"""

__version__ = "3.1.0"
__app_name__ = "Project Opener"
__company__ = "Dexterity Design Services Pvt. Ltd."
