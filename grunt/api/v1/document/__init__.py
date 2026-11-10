"""HTTP methods about one document or one DocType - comments, history, export,
print, trees, link search, workflow transitions, the sidebar.

They used to be static methods of ``Document`` (``grunt.document.base.Document.*``);
living here, the document class carries no API and the document layer imports
none of the services these methods use.
"""
