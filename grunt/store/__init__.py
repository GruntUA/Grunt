"""Where a DocType's rows live - see ``DB_LAYERS_PLAN.md``, step 4.

``store_for(meta)`` - the :class:`Store` of a DocType: what its controller
names in ``store_class``, else :class:`SqlStore` (its table) - or, for a
virtual DocType, the empty :class:`Store`. Reads with permissions go through
:mod:`grunt.permissions.reads`, writes through the document pipeline - not a
store directly.
"""
