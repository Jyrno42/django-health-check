import copy
from concurrent.futures import ThreadPoolExecutor

from health_check.conf import HEALTH_CHECK
from health_check.exceptions import ServiceWarning
from health_check.plugins import plugin_dir


executor = None

def get_executor(inital_max_workers):
    global executor
    if not executor:
        executor = ThreadPoolExecutor(max_workers=inital_max_workers)
    return executor


class CheckMixin:
    _errors = None
    _plugins = None

    @property
    def errors(self):
        if not self._errors:
            self._errors = self.run_check()
        return self._errors

    @property
    def plugins(self):
        if not self._plugins:
            self._plugins = sorted(
                (
                    plugin_class(**copy.deepcopy(options))
                    for plugin_class, options in plugin_dir._registry
                ),
                key=lambda plugin: plugin.identifier(),
            )
        return self._plugins

    def run_check(self):
        errors = []

        def _run(plugin):
            plugin.run_check()
            try:
                return plugin
            finally:
                from django.db import connections

                for alias in connections:
                    try:
                        connection = connections[alias]
                    except AttributeError:
                        continue

                    connection.close_if_unusable_or_obsolete()
        
        executor = get_executor(len(self.plugins) or 1)
        
        for plugin in executor.map(_run, self.plugins):
            if plugin.critical_service:
                if not HEALTH_CHECK["WARNINGS_AS_ERRORS"]:
                    errors.extend(
                        e
                        for e in plugin.errors
                        if not isinstance(e, ServiceWarning)
                    )
                else:
                    errors.extend(plugin.errors)

        return errors
