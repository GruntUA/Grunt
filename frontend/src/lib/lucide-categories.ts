/**
 * Curated Lucide icon categories.
 *
 * Each entry maps a human-readable category label to an array of PascalCase
 * Lucide icon names.  Icons that don't match any category fall into "Other".
 *
 * Source reference: https://lucide.dev/icons/
 */

export interface IconCategory {
  label: string
  icon: string
  icons: string[]
}

export const ICON_CATEGORIES: IconCategory[] = [
  {
    label: 'Arrows',
    icon: 'ArrowRight',
    icons: [
      'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
      'ArrowUpLeft', 'ArrowUpRight', 'ArrowDownLeft', 'ArrowDownRight',
      'ArrowUpFromLine', 'ArrowDownFromLine', 'ArrowLeftFromLine', 'ArrowRightFromLine',
      'ArrowUpToLine', 'ArrowDownToLine', 'ArrowLeftToLine', 'ArrowRightToLine',
      'ArrowBigUp', 'ArrowBigDown', 'ArrowBigLeft', 'ArrowBigRight',
      'ArrowBigUpDash', 'ArrowBigDownDash', 'ArrowBigLeftDash', 'ArrowBigRightDash',
      'ArrowUpCircle', 'ArrowDownCircle', 'ArrowLeftCircle', 'ArrowRightCircle',
      'ChevronUp', 'ChevronDown', 'ChevronLeft', 'ChevronRight',
      'ChevronsUp', 'ChevronsDown', 'ChevronsLeft', 'ChevronsRight',
      'ChevronUpCircle', 'ChevronDownCircle', 'ChevronLeftCircle', 'ChevronRightCircle',
      'ChevronFirst', 'ChevronLast',
      'MoveUp', 'MoveDown', 'MoveLeft', 'MoveRight',
      'MoveUpLeft', 'MoveUpRight', 'MoveDownLeft', 'MoveDownRight',
      'MoveHorizontal', 'MoveVertical', 'MoveDiagonal', 'MoveDiagonal2',
      'CornerUpLeft', 'CornerUpRight', 'CornerDownLeft', 'CornerDownRight',
      'CornerLeftUp', 'CornerLeftDown', 'CornerRightUp', 'CornerRightDown',
      'Redo', 'Undo', 'Redo2', 'Undo2',
      'RefreshCw', 'RefreshCcw', 'RefreshCwOff',
      'RotateCw', 'RotateCcw',
      'Repeat', 'Repeat1', 'Repeat2',
      'Shuffle', 'SortAsc', 'SortDesc',
      'TrendingUp', 'TrendingDown',
      'ChevronsUpDown', 'ChevronsLeftRight',
    ],
  },
  {
    label: 'Finance',
    icon: 'DollarSign',
    icons: [
      'DollarSign', 'Euro', 'PoundSterling', 'IndianRupee', 'JapaneseYen',
      'RussianRuble', 'SwissFranc', 'Bitcoin', 'Banknote', 'Coins',
      'CreditCard', 'Wallet', 'Wallet2', 'WalletCards', 'WalletMinimal',
      'Receipt', 'ReceiptText', 'ReceiptCent', 'ReceiptEuro', 'ReceiptIndianRupee',
      'ReceiptJapaneseYen', 'ReceiptPoundSterling', 'ReceiptRussianRuble', 'ReceiptSwissFranc',
      'BadgeDollarSign', 'BadgeEuro', 'BadgePoundSterling', 'BadgeIndianRupee',
      'BadgeJapaneseYen', 'BadgeRussianRuble', 'BadgeSwissFranc', 'BadgeCent',
      'PiggyBank', 'Landmark', 'Store', 'ShoppingBag', 'ShoppingBasket', 'ShoppingCart',
      'Package', 'PackageOpen', 'Package2', 'Truck', 'Handshake',
      'TrendingUp', 'TrendingDown', 'BarChart', 'BarChart2',
      'CircleDollarSign', 'CirclePercent', 'Percent', 'Tag', 'Tags', 'Ticket', 'TicketPercent',
    ],
  },
  {
    label: 'Charts & Analytics',
    icon: 'BarChart2',
    icons: [
      'BarChart', 'BarChart2', 'BarChart3', 'BarChart4',
      'BarChartBig', 'BarChartHorizontal', 'BarChartHorizontalBig',
      'LineChart', 'AreaChart', 'PieChart', 'DonutChart',
      'RadarChart', 'ScatterChart', 'CandlestickChart',
      'Activity', 'Gauge', 'GaugeCircle',
      'TrendingUp', 'TrendingDown', 'TrendingUpDown',
      'ChartBar', 'ChartBarBig', 'ChartBarDecreasing', 'ChartBarIncreasing',
      'ChartBarStacked', 'ChartCandlestick', 'ChartColumn',
      'ChartColumnBig', 'ChartColumnDecreasing', 'ChartColumnIncreasing', 'ChartColumnStacked',
      'ChartGantt', 'ChartLine', 'ChartNetwork', 'ChartNoAxesColumn',
      'ChartNoAxesColumnDecreasing', 'ChartNoAxesColumnIncreasing',
      'ChartNoAxesCombined', 'ChartNoAxesGantt', 'ChartPie', 'ChartPieLabelList',
      'ChartScatter', 'ChartSpline',
      'Hash', 'Sigma', 'Equal', 'Plus', 'Minus', 'X', 'Divide',
    ],
  },
  {
    label: 'Communication',
    icon: 'MessageSquare',
    icons: [
      'Mail', 'MailOpen', 'MailCheck', 'MailX', 'MailWarning', 'MailSearch', 'MailPlus', 'MailMinus',
      'Inbox', 'SendHorizonal', 'Send', 'Reply', 'ReplyAll', 'Forward',
      'MessageCircle', 'MessageCircleCode', 'MessageCircleDashed', 'MessageCircleHeart',
      'MessageCircleMore', 'MessageCircleOff', 'MessageCirclePlus', 'MessageCircleQuestion',
      'MessageCircleReply', 'MessageCircleWarning', 'MessageCircleX',
      'MessageSquare', 'MessageSquareCode', 'MessageSquareDashed', 'MessageSquareDiff',
      'MessageSquareDot', 'MessageSquareHeart', 'MessageSquareLock', 'MessageSquareMore',
      'MessageSquareOff', 'MessageSquagePlus', 'MessageSquareQuote', 'MessageSquareReply',
      'MessageSquareShare', 'MessageSquareText', 'MessageSquareWarning', 'MessageSquareX',
      'MessagesSquare', 'Phone', 'PhoneCall', 'PhoneMissed', 'PhoneOff', 'PhoneIncoming', 'PhoneForwarded', 'PhoneOutgoing',
      'Video', 'VideoOff', 'Voicemail', 'Volume', 'Volume1', 'Volume2', 'VolumeX', 'VolumeOff',
      'Bell', 'BellDot', 'BellMinus', 'BellOff', 'BellPlus', 'BellRing',
      'AtSign', 'Megaphone', 'Mic', 'MicOff', 'Radio', 'Rss',
    ],
  },
  {
    label: 'Accounts & Access',
    icon: 'User',
    icons: [
      'User', 'UserRound', 'Users', 'UsersRound', 'UserCheck', 'UserPlus', 'UserMinus', 'UserX',
      'UserCog', 'UserRoundCheck', 'UserRoundMinus', 'UserRoundPlus', 'UserRoundSearch', 'UserRoundX',
      'UserCircle', 'UserCircle2',
      'Contact', 'Contact2', 'ContactRound',
      'Lock', 'LockOpen', 'LockKeyhole', 'LockKeyholeOpen',
      'Key', 'KeyRound', 'KeySquare',
      'Shield', 'ShieldAlert', 'ShieldBan', 'ShieldCheck', 'ShieldEllipsis', 'ShieldHalf',
      'ShieldMinus', 'ShieldOff', 'ShieldPlus', 'ShieldQuestion', 'ShieldX',
      'Fingerprint', 'ScanFace', 'Scan',
      'LogIn', 'LogOut', 'UserRoundCog',
    ],
  },
  {
    label: 'Devices',
    icon: 'Laptop',
    icons: [
      'Laptop', 'Laptop2', 'LaptopMinimal', 'LaptopMinimalCheck',
      'Monitor', 'MonitorCheck', 'MonitorDot', 'MonitorDown', 'MonitorOff', 'MonitorPause',
      'MonitorPlay', 'MonitorSmartphone', 'MonitorStop', 'MonitorUp', 'MonitorX',
      'Smartphone', 'SmartphoneCharging', 'SmartphoneNfc',
      'Tablet', 'TabletSmartphone',
      'Tv', 'Tv2', 'TvMinimal', 'TvMinimalPlay',
      'Printer', 'PrinterCheck',
      'Keyboard', 'KeyboardMusic', 'KeyboardOff',
      'Mouse', 'MousePointer', 'MousePointer2', 'MousePointerBan', 'MousePointerClick',
      'Cpu', 'HardDrive', 'HardDriveDownload', 'HardDriveUpload', 'Server', 'Database',
      'Router', 'WifiHigh', 'Wifi', 'WifiOff', 'Bluetooth', 'BluetoothConnected', 'BluetoothOff', 'BluetoothSearching',
      'Usb', 'BatteryFull', 'Battery', 'BatteryCharging', 'BatteryLow', 'BatteryMedium', 'BatteryWarning',
      'Camera', 'Headphones', 'Headset', 'Speaker',
    ],
  },
  {
    label: 'Files & Documents',
    icon: 'File',
    icons: [
      'File', 'FileText', 'FileImage', 'FileVideo', 'FileVideo2', 'FileAudio', 'FileAudio2',
      'FileCode', 'FileCode2', 'FileJson', 'FileJson2',
      'FileCheck', 'FileCheck2', 'FileClock', 'FileCog', 'FileDiff',
      'FileDown', 'FileInput', 'FileLock', 'FileLock2', 'FileMinus', 'FileMinus2',
      'FileOutput', 'FilePen', 'FilePlus', 'FilePlus2', 'FileQuestion',
      'FileSearch', 'FileSearch2', 'FileSliders', 'FileSpreadsheet',
      'FileStack', 'FileSymlink', 'FileTerminal', 'FileType', 'FileType2',
      'FileUp', 'FileWarning', 'FileX', 'FileX2',
      'Files', 'FilesIcon',
      'Folder', 'FolderClosed', 'FolderCode', 'FolderCog', 'FolderDot', 'FolderDown',
      'FolderGit', 'FolderGit2', 'FolderHeart', 'FolderInput', 'FolderKanban',
      'FolderLock', 'FolderMinus', 'FolderOpen', 'FolderOpenDot', 'FolderOutput',
      'FolderPen', 'FolderPlus', 'FolderRoot', 'FolderSearch', 'FolderSearch2',
      'FolderSymlink', 'FolderSync', 'FolderTree', 'FolderUp', 'FolderX', 'Folders',
      'Archive', 'ArchiveRestore', 'ArchiveX',
      'Paperclip', 'Clipboard', 'ClipboardCheck', 'ClipboardCopy', 'ClipboardList',
      'ClipboardMinus', 'ClipboardPaste', 'ClipboardPen', 'ClipboardType', 'ClipboardX',
    ],
  },
  {
    label: 'Layout & Design',
    icon: 'LayoutDashboard',
    icons: [
      'Layout', 'LayoutDashboard', 'LayoutGrid', 'LayoutList', 'LayoutPanelLeft',
      'LayoutPanelTop', 'LayoutTemplate',
      'Grid2x2', 'Grid2x2Check', 'Grid2x2Plus', 'Grid2x2X', 'Grid3x3',
      'Columns2', 'Columns3', 'Columns4',
      'Rows2', 'Rows3', 'Rows4',
      'Sidebar', 'SidebarClose', 'SidebarOpen', 'PanelLeft', 'PanelRight', 'PanelTop', 'PanelBottom',
      'PanelLeftClose', 'PanelLeftOpen', 'PanelRightClose', 'PanelRightOpen',
      'PanelTopClose', 'PanelTopOpen', 'PanelBottomClose', 'PanelBottomOpen',
      'AppWindow', 'AppWindowMac',
      'Maximize', 'Maximize2', 'Minimize', 'Minimize2',
      'Square', 'SquareDashedBottom', 'SquareDashedBottomCode',
      'RectangleHorizontal', 'RectangleVertical', 'Circle', 'Ellipsis', 'EllipsisVertical',
      'Dot', 'Asterisk',
    ],
  },
  {
    label: 'Navigation',
    icon: 'Compass',
    icons: [
      'Home', 'HomeModern',
      'Map', 'MapPin', 'MapPinHouse', 'MapPinOff', 'MapPinPlus', 'MapPinX', 'MapPinCheck', 'MapPinCheckInside', 'MapPinMinus',
      'Navigation', 'Navigation2', 'NavigationOff',
      'Globe', 'Globe2',
      'Compass', 'Locate', 'LocateFixed', 'LocateOff',
      'Route', 'RouteOff',
      'Milestone', 'Crosshair',
      'SquareChevronUp', 'SquareChevronDown', 'SquareChevronLeft', 'SquareChevronRight',
      'Menu', 'AlignLeft', 'AlignRight', 'AlignCenter', 'AlignJustify',
      'ExternalLink', 'Link', 'Link2', 'Link2Off', 'Unlink', 'Unlink2',
      'Bookmark', 'BookmarkCheck', 'BookmarkMinus', 'BookmarkPlus', 'BookmarkX', 'Bookmarks',
    ],
  },
  {
    label: 'Tools & Settings',
    icon: 'Settings2',
    icons: [
      'Settings', 'Settings2', 'Sliders', 'SlidersHorizontal', 'SlidersVertical',
      'Wrench', 'Hammer', 'Drill', 'Screwdriver', 'Scissors', 'Ruler',
      'Cog', 'Cpu', 'Bolt',
      'Paintbrush', 'Paintbrush2', 'PaintBucket', 'Palette',
      'Pipette', 'Eraser', 'Pencil', 'PencilLine', 'PencilOff', 'PencilRuler', 'Pen', 'PenLine', 'PenOff', 'PenTool',
      'Crop', 'Scaling', 'Fullscreen', 'Focus',
      'Filter', 'FilterX', 'Funnel', 'FunnelPlus', 'FunnelX',
      'Search', 'SearchCheck', 'SearchCode', 'SearchSlash', 'SearchX',
      'ZoomIn', 'ZoomOut',
      'Move', 'Trash', 'Trash2', 'RotateCw', 'RotateCcw',
      'Copy', 'Cut', 'Clipboard', 'Download', 'Upload',
    ],
  },
  {
    label: 'Status & Alerts',
    icon: 'AlertCircle',
    icons: [
      'Check', 'CheckCheck', 'CheckCircle', 'CheckCircle2', 'CheckSquare',
      'X', 'XCircle', 'XSquare', 'XOctagon',
      'AlertCircle', 'AlertOctagon', 'AlertTriangle',
      'Info', 'HelpCircle', 'ShieldAlert',
      'Ban', 'Slash',
      'Bell', 'BellDot', 'BellRing', 'BellOff',
      'Flag', 'FlagOff', 'FlagTriangleLeft', 'FlagTriangleRight',
      'CircleAlert', 'CircleArrowDown', 'CircleArrowLeft', 'CircleArrowOutDownLeft',
      'CircleArrowOutDownRight', 'CircleArrowOutUpLeft', 'CircleArrowOutUpRight',
      'CircleArrowRight', 'CircleArrowUp',
      'CircleCheck', 'CircleCheckBig', 'CircleDashed', 'CircleDivide',
      'CircleDot', 'CircleDotDashed', 'CircleEllipsis', 'CircleEqual', 'CircleFadingArrowUp',
      'CircleFadingPlus', 'CircleGauge', 'CircleHelp', 'CircleMinus', 'CircleOff',
      'CircleParkingOff', 'CirclePause', 'CirclePlay', 'CirclePlus',
      'CirclePower', 'CircleSlash', 'CircleSlash2', 'CircleStop', 'CircleUser', 'CircleUserRound',
      'CircleX',
      'OctagonAlert', 'OctagonMinus', 'OctagonPause', 'OctagonX',
      'TriangleAlert', 'TriangleRight',
    ],
  },
  {
    label: 'Connectivity & Cloud',
    icon: 'Cloud',
    icons: [
      'Wifi', 'WifiHigh', 'WifiLow', 'WifiOff', 'WifiZero',
      'Bluetooth', 'BluetoothConnected', 'BluetoothOff', 'BluetoothSearching',
      'Cloud', 'CloudAlert', 'CloudCog', 'CloudDownload', 'CloudDrizzle',
      'CloudFog', 'CloudHail', 'CloudLightning', 'CloudLightningRain',
      'CloudMoon', 'CloudMoonRain', 'CloudOff', 'CloudRain', 'CloudRainWind',
      'CloudSnow', 'CloudSun', 'CloudSunRain', 'CloudUpload',
      'Server', 'ServerCog', 'ServerCrash', 'ServerOff',
      'Database', 'DatabaseBackup', 'DatabaseZap',
      'HardDrive', 'Network', 'Router',
      'Globe', 'Globe2', 'Satellite', 'SatelliteDish',
      'Signal', 'SignalHigh', 'SignalLow', 'SignalMedium', 'SignalZero',
      'Rss', 'Radio', 'NfcIcon', 'Nfc',
    ],
  },
  {
    label: 'Time & Calendar',
    icon: 'Calendar',
    icons: [
      'Calendar', 'CalendarArrowDown', 'CalendarArrowUp', 'CalendarCheck', 'CalendarCheck2',
      'CalendarClock', 'CalendarCog', 'CalendarDays', 'CalendarFold', 'CalendarHeart',
      'CalendarMinus', 'CalendarMinus2', 'CalendarOff', 'CalendarPlus', 'CalendarPlus2',
      'CalendarRange', 'CalendarSearch', 'CalendarSync', 'CalendarX', 'CalendarX2',
      'Clock', 'Clock1', 'Clock2', 'Clock3', 'Clock4', 'Clock5', 'Clock6', 'Clock7',
      'Clock8', 'Clock9', 'Clock10', 'Clock11', 'Clock12',
      'ClockAlert', 'ClockArrowDown', 'ClockArrowUp',
      'Timer', 'TimerOff', 'TimerReset',
      'Watch', 'Alarm', 'AlarmCheck', 'AlarmClock', 'AlarmClockCheck', 'AlarmClockMinus', 'AlarmClockOff', 'AlarmClockPlus', 'AlarmMinus', 'AlarmPlus', 'AlarmSmoke',
      'Hourglass',
    ],
  },
  {
    label: 'Media & Multimedia',
    icon: 'Play',
    icons: [
      'Play', 'Pause', 'Stop', 'SkipBack', 'SkipForward', 'FastForward', 'Rewind',
      'Volume', 'Volume1', 'Volume2', 'VolumeX', 'VolumeOff',
      'Music', 'Music2', 'Music3', 'Music4',
      'Mic', 'MicOff', 'MicVocal',
      'Headphones', 'Headset', 'Speaker', 'Radio',
      'Film', 'Clapperboard', 'Video', 'VideoOff',
      'Camera', 'CameraOff',
      'Image', 'Images', 'ImageOff', 'ImagePlus',
      'Aperture', 'ScanLine',
      'PlayCircle', 'PauseCircle', 'StopCircle',
      'PlaySquare',
      'Tv', 'Tv2', 'TvMinimal', 'TvMinimalPlay',
    ],
  },
  {
    label: 'Health & People',
    icon: 'Heart',
    icons: [
      'Heart', 'HeartCrack', 'HeartHandshake', 'HeartOff', 'HeartPlus', 'HeartPulse',
      'Activity', 'Stethoscope', 'Pill', 'Pill2',
      'Baby', 'PersonStanding', 'Footprints',
      'Smile', 'SmilePlus', 'Laugh', 'Frown', 'Annoyed', 'Angry', 'Meh', 'Grimace',
      'ThumbsUp', 'ThumbsDown',
      'Star', 'StarHalf', 'StarOff',
      'Trophy', 'Medal', 'Award', 'Crown',
      'Accessibility', 'Wheelchair',
    ],
  },
  {
    label: 'Buildings & Places',
    icon: 'Building2',
    icons: [
      'Building', 'Building2', 'BuildingIcon',
      'Home', 'HomeModern',
      'Store', 'Hotel', 'Hospital', 'Warehouse', 'Factory', 'School', 'Church', 'Landmark',
      'Bridge', 'Fence',
      'Tent', 'TentTree',
      'Castle', 'CastleIcon',
      'TreeDeciduous', 'TreePine', 'Trees', 'Flower', 'Flower2', 'Leaf', 'Clover',
      'Mountain', 'MountainSnow', 'Sun', 'Sunset', 'Sunrise', 'Moon', 'Waves',
    ],
  },
  {
    label: 'Text Formatting',
    icon: 'Bold',
    icons: [
      'Bold', 'Italic', 'Underline', 'Strikethrough', 'Superscript', 'Subscript',
      'AlignLeft', 'AlignCenter', 'AlignRight', 'AlignJustify',
      'Heading', 'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6',
      'List', 'ListOrdered', 'ListChecks', 'ListCollapse', 'ListEnd', 'ListFilter',
      'ListMinus', 'ListMusic', 'ListPlus', 'ListRestart', 'ListStart', 'ListTodo', 'ListTree', 'ListVideo', 'ListX',
      'Pilcrow', 'RemoveFormatting', 'TextCursor', 'TextCursorInput',
      'Type', 'TypeOutline', 'CaseLower', 'CaseSensitive', 'CaseUpper',
      'Indent', 'Outdent',
      'Link', 'Link2', 'Unlink',
      'Quote', 'Code', 'Code2', 'CodeXml', 'Braces', 'Brackets',
      'Table', 'Table2',
    ],
  },
  {
    label: 'Coding & Development',
    icon: 'Code2',
    icons: [
      'Code', 'Code2', 'CodeXml', 'Terminal', 'SquareTerminal',
      'Braces', 'Brackets', 'Hash', 'AtSign', 'Regex',
      'Bug', 'BugOff', 'BugPlay',
      'GitBranch', 'GitBranchPlus', 'GitCommitHorizontal', 'GitCommitVertical',
      'GitCompare', 'GitCompareArrows', 'GitFork', 'GitGraph', 'GitMerge', 'GitMergeQueue',
      'GitPullRequest', 'GitPullRequestArrow', 'GitPullRequestClosed', 'GitPullRequestCreate',
      'GitPullRequestCreateArrow', 'GitPullRequestDraft',
      'Package', 'Package2', 'PackageCheck', 'PackageMinus', 'PackageOpen', 'PackagePlus', 'PackageSearch', 'PackageX',
      'Blocks', 'Box', 'Boxes',
      'Webhook', 'Workflow', 'Cpu', 'CircuitBoard',
    ],
  },
]

/**
 * Representative PascalCase Lucide icon name for each category.
 * Used for tab bar icons or quick visual identification.
 */
export const CATEGORY_TAB_ICONS: Record<string, string> = {
  ...Object.fromEntries(ICON_CATEGORIES.map(c => [c.label, c.icon])),
  'Other':              'MoreHorizontal',
}

/** Returns the category label for a given PascalCase icon name, or undefined if uncategorised. */
export function getCategoryForIcon(pascalName: string): string | undefined {
  for (const cat of ICON_CATEGORIES) {
    if (cat.icons.includes(pascalName)) return cat.label
  }
  return undefined
}

/**
 * Groups a flat list of PascalCase icon names into { category, icons[] } buckets.
 * Icons not found in any category are placed under the given `otherLabel`.
 */
export function groupIconsByCategory(
  names: string[],
  otherLabel = 'Other',
): { label: string; icon: string; icons: string[] }[] {
  // Build category order map for fast lookup
  const catIndexMap = new Map<string, number>()
  ICON_CATEGORIES.forEach((c, i) => catIndexMap.set(c.label, i))

  const nameSet = new Set(names)

  // Keep the declaration order of ICON_CATEGORIES
  const result: { label: string; icon: string; icons: string[] }[] = ICON_CATEGORIES.map(c => ({
    label: c.label,
    icon: c.icon,
    icons: c.icons.filter(n => nameSet.has(n)),
  })).filter(c => c.icons.length > 0)

  // Collect names not placed in any category
  const placed = new Set(result.flatMap(c => c.icons))
  const other = names.filter(n => !placed.has(n))
  if (other.length) {
    result.push({ label: otherLabel, icon: 'MoreHorizontal', icons: other })
  }

  return result
}
