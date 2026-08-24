"""Built-in field validators (EmailValidator, PhoneValidator, EdrpouValidator, ...).

Nothing in this package imports these classes directly — they're picked up
by reflection at startup: ``grunt.startup.validators.load_validators()``
scans this directory (and each app's own ``validators/`` dir) and registers
every ``Validator`` subclass it finds via ``document/validators.py``. So a
class defined here with no visible caller is not dead code — check
``load_validators()`` before assuming otherwise.
"""
