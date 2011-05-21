#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
@author: Pierre Thibault (pierre.thibault1 -at- gmail.com)
@license: MIT
@since: 2011-05-21

neo-importer is custom Python importer tracking changes of Python source files
".py" and reloading them at the next import statement. This enables the 
developer to make changes to its files and see the result of these changes the 
next time these modules are imported. This a useful tool for Python development
and debugging.

The module contains two methods: is_tracking_changes to know if changes are
tracked. And track_changes: To start/stop the tracking.
'''

__docformat__ = "epytext en"

import __builtin__
import os
import sys
import threading

def is_tracking_changes():
    """
    @return: True: neo_importer is tracking changes made to Python source
    files. False: neo_import does not reload Python modules.
    """

    global _is_tracking_changes
    return _is_tracking_changes

def track_changes(track=True):
    """
    Tell neo_importer to start/stop tracking changes made to Python modules.
    @param track: True: Start tracking changes. False: Stop tracking changes.
    """

    global _date_tracker_importer
    global _is_tracking_changes
    global _STANDARD_PYTHON_IMPORTER
    assert track is True or track is False, "Boolean expected."
    if track == _is_tracking_changes:
        return
    if track:
        if not _date_tracker_importer:
            _date_tracker_importer = _DateTrackerImporter()
        __builtin__.__import__ = _date_tracker_importer
    else:
        __builtin__.__import__ = _STANDARD_PYTHON_IMPORTER
    _is_tracking_changes = track

_STANDARD_PYTHON_IMPORTER = __builtin__.__import__ # Keep standard importer
_date_tracker_importer = None # To hold _DateTrackerImporter
_is_tracking_changes = False # The tracking mode

class _BaseImporter(object):
    """
    The base importer. Dispatch the import the call to the standard Python
    importer.
    """

    def begin(self):
        """
        Many imports can be made for a single import statement. This method
        help the management of this aspect.
        """

    def __call__(self, name, globals={}, locals={}, fromlist=[], level=-1):
        """
        The import method itself.
        """

        return _STANDARD_PYTHON_IMPORTER(name, globals, locals, fromlist, 
                                         level)

    def end(self):
        """
        Needed for clean up.
        """


class _DateTrackerImporter(_BaseImporter):
    """
    An importer tracking the date of the module files and reloading them when
    they have changed.
    """

    _PACKAGE_PATH_SUFFIX = os.path.sep+"__init__.py"

    def __init__(self):
        super(_DateTrackerImporter, self).__init__()
        self._import_dates = {} # Import dates of the files of the modules
        # Avoid reloading cause by file modifications of reload:
        self._tl = threading.local()
        self._tl._modules_loaded = None

    def begin(self):
        self._tl._modules_loaded = set()

    def __call__(self, name, globals={}, locals={}, fromlist=[], level=-1):
        """
        The import method itself.
        """

        call_begin_end = self._tl._modules_loaded == None
        if call_begin_end:
            self.begin()

        try:
            self._tl.globals = globals
            self._tl.locals = locals
            self._tl.level = level

            # Check the date and reload if needed:
            self._update_dates(name, fromlist)

            # Try to load the module and update the dates if it works:
            result = super(_DateTrackerImporter, self) \
              .__call__(name, globals, locals, fromlist, level)
            # Module maybe loaded for the 1st time so we need to set the date
            self._update_dates(name, fromlist)
            return result
        except Exception, e:
            raise e  # Don't hide something that went wrong
        finally:
            if call_begin_end:
                self.end()

    def _update_dates(self, name, fromlist):
        """
        Update all the dates associated to the statement import. A single
        import statement may import many modules.
        """

        self._reload_check(name)
        if fromlist:
            for fromlist_name in fromlist:
                self._reload_check("%s.%s" % (name, fromlist_name))

    def _reload_check(self, name):
        """
        Update the date associated to the module and reload the module if
        the file has changed.
        """

        module = sys.modules.get(name)
        file = self._get_module_file(module)
        if file:
            date = self._import_dates.get(file)
            new_date = None
            reload_mod = False
            mod_to_pack = False # Module turning into a package? (special case)
            try:
                new_date = os.stat(file).st_mtime
            except:
                self._import_dates.pop(file, None)  # Clean up
                # Handle module changing in package and
                #package changing in module:
                if file.endswith(".py"):
                    # Get path without file ext:
                    file = os.path.splitext(file)[0]
                    reload_mod = os.path.isdir(file) \
                      and os.path.isfile(file+self._PACKAGE_PATH_SUFFIX)
                    mod_to_pack = reload_mod
                else: # Package turning into module?
                    file += ".py"
                    reload_mod = os.path.isfile(file)
                if reload_mod:
                    new_date = os.stat(file).st_mtime # Refresh file date
            if reload_mod or not date or new_date > date:
                self._import_dates[file] = new_date
            if reload_mod or (date and new_date > date):
                if module not in self._tl._modules_loaded:
                    if mod_to_pack:
                        # Module turning into a package:
                        mod_name = module.__name__
                        del sys.modules[mod_name] # Delete the module
                        # Reload the module:
                        super(_DateTrackerImporter, self).__call__ \
                          (mod_name, self._tl.globals, self._tl.locals, [],
                           self._tl.level)
                    else:
                        reload(module)
                        self._tl._modules_loaded.add(module)

    def end(self):
        self._tl._modules_loaded = None

    @classmethod
    def _get_module_file(cls, module):
        """
        Get the absolute path file associated to the module or None.
        """

        file = getattr(module, "__file__", None)
        if file:
            # Make path absolute if not:
            #file = os.path.join(cls.web2py_path, file)

            file = os.path.splitext(file)[0]+".py" # Change .pyc for .py
            if file.endswith(cls._PACKAGE_PATH_SUFFIX):
                file = os.path.dirname(file)  # Track dir for packages
        return file
