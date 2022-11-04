"""
A customized version of mixins.py inside django-health-checks package.

The custom variant reuses the worker threads instead of re-creating them for
 each health check run. This allows us to remove the closing of all connections
  after health checks complete.

diff between our custom mixins.py and the original (3.17.0):
    https://github.com/Jyrno42/django-health-check/compare/master...reuse-threads
"""

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

        for plugin in get_executor(len(self.plugins) or 1).map(_run, self.plugins):
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
