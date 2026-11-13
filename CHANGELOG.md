# Changelog

## v0.4.0 - 2026-11-13

### Features

- **permissions:** a rule names a role that exists
- **permissions:** no role-name bypass in actions, workflow, menus and pages
- **permissions:** permissions instead of role names
- **permissions:** check new values on write, role permission matrix
- **workflow:** transition notifications through Notification rules
- **notification:** code events through standard Notification rules
- **notification:** recipient and channel tables, Jinja templates
- **notification:** channels and the NotificationDelivery log

### Fixes

- **permissions:** review of the matrix, reset to standard and report rights
- **permissions:** permissions in the sign-in payload; Role test without export
- **notification:** review of code events - savepoints, full docs, app hooks
- **notification:** skip inactive accounts, load DocType for links, refuse downgrades
- **db:** dialect-aware index drop and resumable column rename in rename_doctype

### Other

- **deps:** upgrade npm and Python packages
- **deps-dev:** bump @hono/node-server
- **notification:** rename NotificationRule → Notification, Notification → NotificationLog

### Database migrations

- `0022_notification_rename`
- `0023_notification_rows`
- `0024_workflow_notifications`
- `0025_role_permissions`

## v0.3.0 - 2026-11-11

### Breaking changes

- **permissions:** refuse the old permission flags (#141)
- **permissions:** permission rows grant a list of actions (#139)
- **imports:** auth services leave the User controller's re-exports (#134)
- **imports:** document HTTP methods move from Document to grunt.api.v1.document (#133)

### Features

- update permissions plan with validation results and refactor skill documentation
- update IMPORT_CYCLES_PLAN and add FRAPPE_GAP_PLAN for functionality gaps
- **permissions:** read-only fields per role (#142)
- **permissions:** enforce export, import, print, share and report (#140)
- **scheduler:** log only failures of jobs that fire more often than hourly (#115)
- **versions:** no_history fields and max_versions per document (#114)
- **website:** serve an app's www pages at the root of its own domain (#109)
- **sla:** the document's deadlines in its form sidebar (#112)
- **onboarding:** tours of a list, not only of a form (#111)
- **website:** page views in the core - view_count, beacon, Redis batches (#110)

### Fixes

- **permissions:** close every path to a field hidden from the user (#119)
- **permissions:** one predicate decides lists and single documents (#118)
- **dependencies:** update pypdfium2 to version 5.15.2 (#117)
- **deps:** sync package-lock.json with package.json, inline @unovis in vitest (#116)
- **query:** order_by takes "field asc|desc" and rejects unknown fields (#108)
- **permissions:** no cache for role checks - answers never outlive their rows (#104)

### Performance

- **db:** implicit indexes, SQLite tuning and nightly maintenance (#113)

### Other

- empty only the tables a test wrote to (#143)
- count parent-package imports, empty re-export __init__ files (step 10) (#138)
- untangle the remaining import cycles (step 8) (#137)
- **imports:** the core no longer imports the grunt facade at all (#136)
- **imports:** the core stops going through the grunt facade (#135)
- **imports:** the write pipeline reaches workflow, webhooks and the rest through extension points (#132)
- **imports:** services call the document API and grunt.local instead of the facade (#131)
- **imports:** document CRUD moves into the document layer; the event bus loses its subsystems (#130)
- **imports:** services under the document layer stop reaching the facade for low-level calls (#129)
- **imports:** document.base and its registry stop importing each other (#128)
- **imports:** the document layer stops reaching the facade for low-level calls (#127)
- **imports:** the data layer and permissions leave import cycles (#126)
- **imports:** permissions untangle their own cycle; query.run reads without permissions (#125)
- **imports:** the metadata layer leaves import cycles (#124)
- **imports:** the context layer leaves import cycles (#123)
- **permissions:** below the auth layer a user is their email (#122)
- **roles:** roles by email, User.has_role, grunt.get_user on the facade (#121)
- **imports:** import-cycle ratchet and the first small cycles (#120)
- Refactor code structure for improved readability and maintainability
- drop on-demand Claude workflow (#107)
- CodeQL scanning and on-demand Claude review (#106)
- check PR titles in CI, minimatch 11, DB layers plan done (#105)

### Database migrations

- `0020_version_history_limits`
- `0021_permission_actions`

## v0.2.0 - 2026-11-08

### Highlights

- **Database layers:** a query AST (`grunt.query`), SQLite / PostgreSQL / MySQL dialects, the `Store` protocol (`SqlStore`, `VirtualStore`), and `DocType.storage` (`"sql"` | `"virtual"`) in place of `is_virtual`.
- **After commit:** `on_commit`, `grunt.enqueue`, and the `grunt_core_outbox` outbox. Webhooks and push notifications are delivered by the worker, with retries.
- **Schema:** changes are planned (diff), checked and applied through the dialect. A SQLite table is rebuilt (column type change) only by `grunt migrate`. Stale indexes are dropped. `grunt migrate --dry-run` shows the plan and changes nothing.
- Global search (FTS, `in_global_search`), app extensions, Studio properties, onboarding, StorageRemote, web push.

**Breaking (pre-1.0):** `is_virtual` becomes `storage: "virtual"`. The old query and virtual document APIs are removed.

**Upgrade:** `grunt migrate --dry-run --site <site>`, then `grunt migrate` (Alembic `0011`–`0019`, the `grunt_core_outbox` table, stale indexes dropped). Then restart web **and** worker: the worker delivers the outbox.

### Features

- **schema:** plan schema changes with diff, apply them through the dialect
- implement outbox pattern for notifications and real-time updates after commit
- **outbox:** implement outbox pattern for webhook delivery and side effects
- **store:** enhance support for SQL capabilities across various modules
- **reports:** implement report source handling for linked fields and row-level permissions
- **dialects:** enhance integrity violation handling and index management for MySQL and PostgreSQL
- **dialects:** enhance connect_args for UTC sessions and add exact comparison method feat(tests): add performance test for wildcard matching and cursor sorting by name refactor(in_memory): replace regex with linear wildcard matching for LIKE filters
- **tests:** implement TestSchema for efficient test database management
- **postgresql:** enhance libpq parameter handling and improve integrity error reporting
- **errors:** enhance integrity error handling across database dialects
- **search:** implement in_global_search flag for document types and enhance search indexing logic
- **search:** Enhance global search functionality with improved term matching and FTS support
- **api:** enhance document handling in methods and add tests for controller serialization
- **api:** define common result shapes and enhance type annotations for whitelisted methods
- **api:** enhance module discovery for @whitelist methods and improve import handling
- introduce TypeScript type generation for grunt.call methods
- **executor:** refactor actions parameter to use noActions function for better clarity feat(jsconfig): update paths configuration for improved module resolution feat(types): enhance global types by importing from core scripting types and removing deprecated definitions
- **executor:** refactor createGruntProxy to use GruntProxy methods and simplify callback handling feat(formDashboard): enhance clear_section logic and streamline state management feat(types): add has_tours property and start_tour method to FormProxy interface
- **filters:** rename _expand_child_of_filters to expand_child_of_filters and update references
- **filterOps:** refactor filter operations and introduce new filter key utilities
- **doctype:** add icon_field to DocTypeMapView for lucide icon support
- **types:** add new type definitions for dashboard, document, field, list, notification, report, and user
- **global_form:** add shortcut for duplicate action in form
- **registry:** prefer ambient session in _load_lazy to avoid partial registry issues
- **preview:** implement draft preview functionality for unpublished pages
- **sidebar:** enhance sidebar functionality with properties and sections support
- **tree-select:** introduce TreeSelect and TreeSelectNode components with multi-select functionality
- **i18n:** refactor shared context handling and improve metadata translation logic
- **i18n:** enhance translation handling and add system health messages
- **FileExplorer:** add open state to navigation rows for better UI interaction
- **health:** update stray_venvs_row message to include pyproject.toml configuration feat(boilerplate): add uv tool configuration to prevent .venv creation in app directories
- **columns:** add system audit fields for user tracking in list components
- **workflow:** implement state field handling in document copy and lifecycle management
- **dependencies:** update @lucide/vue to version 1.66.0 and cn to version 0.5.2; update shiki to version 4.6.0 refactor(fields): remove unused NumberFieldDecrement and NumberFieldIncrement components from various fields refactor(tests): update Duration and NumberFields tests to reflect changes in input handling
- **references:** enhance file claiming logic to include user's unattached library files
- **dependencies:** update @lucide/vue to version 1.65.0 and cn to version 0.5.1
- **bulk-operations:** enhance bulk delete functionality to remove child rows and update related tests
- **date-handling:** introduce IsoDate type and update date handling in filters and metadata
- **rate-limit:** enhance path limit functionality with prefix support and add related tests
- **multilink:** implement MultiLink filter functionality and related tests
- **task-tracker:** enhance task reconciliation and add notification for finished tasks
- enhance responsive design and layout adjustments across multiple components
- **auth:** implement user API endpoints for registration, login, MFA, and user management
- Add new DocType controllers and enhance existing ones
- Enhance permissions handling in DocType and related components for improved synchronization and integrity
- Update status configuration in SKILL.md to use status_field and status_indicators for improved clarity and functionality
- Update @lucide/vue to version 1.63.0 and refactor EmptyDescription and SidebarProvider components for improved prop handling
- Implement properties and customization in Studio for DocTypes
- Enhance app extension functionality and uninstall process, ensuring proper removal of shipped records and dashboard integration
- Implement adoption of DocTypes from dependent apps, ensuring table and rows are retained
- Implement menu contribution system for apps extending other apps
- add default sort key and order to list and gallery components
- enhance db migration process with improved error handling and logging
- update Link component to synchronize input model with ComboboxInput
- add support for inline file streaming in get_content method
- add test to ensure same-named DocType from another module is not overwritten
- implement register_installed_app_doctypes for syncing app DocTypes from JSON
- enhance FormDashboard with graph series toggling and currency formatting
- implement bulk action dialogs for list management and update UI components
- **updates:** add OS update monitoring and reporting functionality
- refactor system health report to enhance functionality and performance
- **ListCell:** add ListCell component for file attachment display
- **rate_limit:** add per-IP rate limits for specific paths in hooks
- **pdf:** add PDF engine check and error handling for Playwright installation
- **dialogs:** add support for component dialogs with props
- enhance ListToolbarControls with dialog for column settings and add localization for new strings
- implement newDesignerField function for consistent field creation and set default in_filter to true
- add PropertySection components for various field types and update manifests
- update field manifests to include new properties and improve structure
- enhance field manifests with list_inline property and improve field type handling
- add quick_filter property to field manifests and update quick filter logic
- add HTML exporter for list view with grouping and filtering
- Revise sections and sidebar items in grunt_workspace.json for improved organization and clarity
- Enhance code splitting in Vite configuration for improved vendor chunk management
- Implement column width management in builder layout and update related components
- Add support for additional allowed file types in system settings and enhance file type validation
- Add byte formatting functionality and update File DocType to support byte size representation
- Implement file detachment for replaced documents and add tests for functionality
- Add sync property to grunt_home_page fixture for improved data consistency
- Enhance performance monitoring with client error handling and pipeline timing
- Add pagination support to useListRouteSync and useListSearch for improved navigation
- Implement Redis-based cache invalidation and shared state across workers
- implement ScheduledJobLog for tracking scheduled job executions and middleware integration
- add image compression feature for uploaded files
- add User DocType with client script and controller implementation
- implement background task progress tracking and cancellation functionality
- implement backup locking mechanism to prevent concurrent backups and add disk space checks
- add field shake animation and integrate FormViewInfo component for document view tracking
- add withAsOfDateFilter function to manage as-of date filters in quick filters; update tests and components for integration
- refactor FormRenderer to improve tab handling and field visibility; add support for async components
- enhance SystemHealthReport indicators and hide unnecessary fields
- add DialogTableField component and integrate it into GruntDialog
- refactor AppSidebar and Sidebar components for improved structure and readability; add SidebarUser component for user display
- remove ShortcutKbd component and replace with inline Kbd and KbdGroup for shortcut display
- rename _zstd_options to zstd_options and update references; add _archive_app function for app packaging
- update _run_python to use the interpreter's venv for ruff commands
- add translation for "no release found" and implement release age check in mise self-update
- update command instructions to include --upgrade-packages option for lock file updates
- enhance offline capabilities with new OfflineIndicator and AppToaster components
- add refresh button prop to FileExplorer and update related components
- update service worker caching strategy and versioning
- implement login redirect functionality with session storage handling
- add category grouping and tab navigation to Icon picker component
- pass document URL through notification service and workflow notifications
- add explorer view support and update dependencies
- add FormDashboard component and core scripting module for document views
- **FileExplorer:** enhance keyboard navigation and selection features
- Add sidebar style configuration and workspace sections
- enhance BlockHandle and FileExplorer components with improved UI elements and navigation
- implement NumberField component and refactor numeric input fields for improved functionality and localization support
- implement Drawer component and replace Sheet in MobileBottomNav for improved mobile navigation
- enhance CommandPalette with keyboard navigation and add unit tests
- implement native shadcn UI components and improve styling across the application
- enhance GruntDialog and ListTreePanel components with button variants and improved structure
- enhance Node.js tool runner and add registry style validation
- enhance Login component with improved field structure and alert handling
- integrate vue-input-otp for OTP input handling
- update favicon and manifest references, remove unused files
- add FormTour and FormTourStep doctypes for guided tours in forms
- **i18n:** enhance translation capabilities for onboarding modules
- add app removal functionality with archiving and dependency checks
- enhance user identification in push notifications by including email in subscription filters
- implement web push notification functionality and add corresponding tests
- add core action merging functionality and corresponding unit tests
- implement web push notification test action and enhance related functionality
- add file deletion restrictions and corresponding error messages in the File doctype
- implement account disablement handling in login process and add corresponding tests
- enhance BackgroundWorker functionality with current tasks tracking and improved task info retrieval
- update BackgroundWorker documentation and improve consumer status handling
- enhance backend and worker task execution with improved sync handling
- update Ukrainian translations and enhance process handling in updates
- add Ukrainian translations and implement old runtimes functionality in updates
- add tests for CLI command execution and path handling
- enhance connection testing with unique probe names and improved error handling
- update dependencies to latest versions for improved performance and compatibility
- enhance app dependency management with upgrade and outdated options
- add health report updates functionality and implement rclone installation
- remove sequence field from widget definitions in grunt_home_page fixture
- enhance dashboard widgets functionality and improve data handling
- implement masonry grid layout for widgets in AppHome and AppPage
- remove unused Dashboard-related DocTypes and endpoints, consolidate widget data handling
- **donut:** enhance legend labels to display value and percentage
- **dashboard:** enhance widget period functionality and add period switcher
- add ModuleOnboarding and related onboarding functionality
- **sidebar:** implement dynamic sidebar sections with permissions and hooks
- **reactions:** implement emoji reactions for comments with toggle functionality
- **profiler:** enable SQL profiler with role-based access and configuration
- **activity:** enhance activity entries with document titles and user names
- **dashboard:** implement dashboard switching and visibility based on user roles
- **audit:** implement Save button blocking on row errors in Table field
- **validation:** implement child table row validation and error reporting
- **tests:** enhance error message handling in StorageRemote tests with language support
- **validation:** add async validation for child table rows in document data
- **health:** add version comparison functions for database migration checks
- **ideas:** update versioning framework through git with detailed release process and migration tracking
- **migrations:** enhance migration handling and tracking, add version recording for installed apps
- **onboarding:** add comprehensive onboarding module with checklists, setup wizard, and guided tours
- **storage:** Implement StorageRemote for external storage connections
- **auth:** implement device ID management for user sessions and sign-in history
- **ideas:** add external cloud storage integration for backups and file management
- **redis:** add consumer pruning and unregistration logic for improved resource management
- **dependencies:** implement app dependency management and cloning logic

### Fixes

- **schema:** SQLite compares column types by how it stores them (#103)
- **migrate:** --dry-run changes nothing (#102)
- **dependencies:** update @lucide/vue to version 1.68.0
- **ui:** add --yes flag to _shadcn call in ui_update for automatic confirmation
- update doctypeLabel handling for improved placeholder text in Link and FilterInput components
- improve input focus handling and derive width consistently in SidebarMenuSkeleton
- update command references for package upgrades in documentation and translations
- standardize color label spelling and update loading messages
- update height classes to use h-dvh for better mobile compatibility
- replace window.confirm with useDialog for better user experience
- improve backend down logging during startup
- **write:** ensure child rows from lifecycle hooks are stored on insert feat(tests): add test for child rows storage during insert validation
- Remove sequence from sidebar_items in workspace fixtures and update tests for ordering
- Update modified_at to store datetime object instead of ISO string and add regression test for bulk_update
- Update repository URL in README for project setup instructions

### Other

- how we work - branches, pull requests, releases (#101)
- Refactor user-related imports and enhance transaction handling
- refactor status checks for refused operations in virtual documents
- replace is_virtual flag with storage attribute in DocType
- Refactor Virtual DocTypes to use VirtualStore
- Refactor document querying and storage
- Refactor database filtering and permissions handling
- **permissions:** unify query predicates and streamline permission checks across modules
- Refactor query handling: Introduce AST for filters and unify SQL and in-memory evaluations
- **permissions:** streamline user permissions handling by removing redundant conditions
- Refactor in-memory document filtering and sorting
- **deps:** bump actions/checkout from 4 to 7
- **deps:** bump astral-sh/setup-uv from 6 to 7
- **deps:** bump actions/setup-node from 4 to 7
- **tests:** remove continue-on-error for PostgreSQL and tune settings for CI
- format query parameters for better readability in backup_remotes function
- standardize boolean values across database filters and conditions
- isolate test databases per xdist worker and bind the test site to them
- **backups:** database dump and restore move into the dialect layer
- **search:** move full-text engines and upsert into the dialect layer
- Refactor database dialect handling and improve SQL compatibility
- Refactor code structure for improved readability and maintainability
- Refactor authentication and session management
- update dependencies in package.json and pyproject.toml
- Refactor i18n handling in PO files and improve translation merging
- Enhance PO file merging and testing functionality
- Refactor code structure for improved readability and maintainability
- Refactor code structure for improved readability and maintainability
- add eslint configuration and update dependencies in package.json
- Refactor code structure for improved readability and maintainability
- Replace structlog with grunt log in hooks, install, and tasks templates
- replace utility import path for 'cn' in multiple components
- Refactor CLI commands and improve linting process
- add tests for donut and chart widgets to validate aggregation functionality
- remove allSelected state from selection management
- Implement code changes to enhance functionality and improve performance
- Refactor app manifest handling: migrate from app.json to pyproject.toml
- Refactor AppMenu and related components for improved color handling and metadata management
- update type change descriptions and improve localization messages
- simplify StorageClass and FieldTrait types in fieldRegistry
- replace DialogFieldType with FieldType in useDialog and useDocActions
- add table_inline property to field manifests and update field registry
- Refactor field types from "Text" to "Data" across multiple test files
- enhance notification handling with sound preferences and localization updates
- integrate audio notifications and remove unused components
- replace date-fns with @internationalized/date for calendar handling and improve date-related functions
- remove Playwright dependencies and update package versions
- remove unused Geist font dependency and update RichText editor styles
- update dependencies and remove unused packages
- Refactor code structure for improved readability and maintainability
- Refactor user role handling, enhance WebSocket connection management, and improve app scaffolding
- update @lucide/vue to v1.60.0 and add new dependencies (cn@0.5.0, shiki@4.5.0)
- Update package versions in package-lock.json and uv.lock for dependency management
- Clean up User DocType and improve import statements in code generation utilities
- Remove obsolete User and WebsiteMenuItem Doctypes and their associated scripts
- Update scaffold.py to improve DocType file structure handling and streamline directory management
- Update @intlify packages to version 11.4.16 for improved stability
- Update package-lock.json to reflect dependency version upgrades
- Enhance site-specific caching for milestones, notification rules, and SLAs
- remove unnecessary future annotations from widget and field files
- Refactor test files to remove unnecessary future annotations and improve readability
- replace AlertDialogAction with Button component for better dialog handling feat: add error handling for lazy route chunk loading in router
- update type hints for better clarity and consistency in backup functions
- replace fieldtype checks with trait-based methods
- Add Ukrainian translations for time units and update BackgroundJob JSON structure
- Update dependencies: fastapi to 0.143.3, pluggy to 1.7.0, py-vapid to 1.9.6, ruff to 0.17.1, and sqlalchemy to 2.1.5
- remove ListTreePanel component and related functionality
- redesign metric widget layout and improve icon resolution handling
- downgrade typescript dependency version in package.json
- update dependencies for improved performance and security
- **FormDashboard:** remove unused imports to clean up code
- Refactor Table component to use Card layout for mobile view and extract row actions into a separate component
- update dependencies and remove chart.js integration
- Refactor code structure for improved readability and maintainability
- update form sections to use Field components for better structure and accessibility
- standardize import statements and improve class handling in UI components
- update dependencies and remove unused radix-icons from Vite config
- Implement code changes to enhance functionality and improve performance
- Refactor code structure for improved readability and maintainability
- Refactor code structure for improved readability and maintainability
- Enhance linting and type checking, improve test coverage, and refactor code
- improve code formatting and ensure datetime imports in code generation
- clean up code formatting and remove unused update command
- Refactor code structure for improved readability and maintainability

### Database migrations

- `0011_drop_dashboard_doctypes`
- `0012_page_widget_row_order`
- `0013_drop_list_tree_field`
- `0014_release_replaced_files`
- `0015_merge_text_htmleditor_fieldtypes`
- `0016_allowed_file_types_setting`
- `0017_drop_system_health_child_doctypes`
- `0018_website_menu_item_link_type`
- `0019_doctype_storage`

## v0.1.0 - 2026-10-12

### Other

- Initial release
