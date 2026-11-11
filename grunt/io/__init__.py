"""grunt.io - pluggable export / import registry.

Built-in exporters and importers are registered in grunt/apps/loader.py.
External apps add their own via hooks.py:

    # myapp/mymodule/hooks.py
    from myapp.exporters import MyExporter
    io_exporters = [MyExporter()]

Registries: :mod:`grunt.io.exporters.registry`, :mod:`grunt.io.importers.registry`.
"""
