# Page views

Any DocType with an `Int` field named `view_count` counts views of its
public pages - no other setup. The page sends a beacon after it loads:

```html
<script>
  navigator.sendBeacon(
    "/api/v1/method/grunt.website.views.record_view?doctype=BlogPost&name={{ doc.name | urlencode }}"
  );
</script>
```

- Bots without JavaScript never send it; known bots by User-Agent are dropped
  too, and so is a repeat view of the same page from the same address within
  30 minutes (with Redis).
- The HTML stays the same for every reader, so the page can be cached.
- **System Settings → General → Website → Count page views** turns counting
  off for the whole site.

With Redis, views pile up in a hash per site (`grunt:views:<site>`) and the
core job `grunt.website.views.flush` moves them to the DB every minute - one
`UPDATE … SET view_count = view_count + n` per page. Without Redis every view
is written right away.

From Python: `await grunt.website.views.record(doctype, name, ip, user_agent)`
(returns whether the view counted) and `await views.counted(doctype)`.
