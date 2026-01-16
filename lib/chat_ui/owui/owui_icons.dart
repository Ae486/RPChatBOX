/// INPUT: lucide_icons（IconData 源）
/// OUTPUT: OwuiIcons - 项目内统一 Icon 入口（避免散落依赖与命名漂移）
/// POS: UI 层 / Design System / Owui - Icon 适配层

import 'package:flutter/widgets.dart';
import 'package:lucide_icons/lucide_icons.dart';

/// Indirection layer for icons used by OWUI.
///
/// Pages/components should prefer `OwuiIcons.*` over directly referencing a
/// third-party icon pack to keep future swaps cheap.
class OwuiIcons {
  OwuiIcons._();

  // ============ 导航与操作 ============

  static const IconData add = LucideIcons.plus;
  static const IconData addCircle = LucideIcons.plusCircle;
  static const IconData remove = LucideIcons.minus;
  static const IconData removeCircle = LucideIcons.minusCircle;
  static const IconData close = LucideIcons.x;
  static const IconData closeCircle = LucideIcons.xCircle;
  static const IconData menu = LucideIcons.menu;
  static const IconData moreVert = LucideIcons.moreVertical;
  static const IconData moreHoriz = LucideIcons.moreHorizontal;
  static const IconData more = LucideIcons.moreVertical;
  static const IconData settings = LucideIcons.settings;
  static const IconData search = LucideIcons.search;
  static const IconData searchOff = LucideIcons.searchX;
  static const IconData filter = LucideIcons.filter;
  static const IconData sort = LucideIcons.arrowUpDown;
  static const IconData back = LucideIcons.arrowLeft;
  static const IconData forward = LucideIcons.arrowRight;

  // ============ 编辑与输入 ============

  static const IconData edit = LucideIcons.pencil;
  static const IconData delete = LucideIcons.trash2;
  static const IconData trash = LucideIcons.trash2;
  static const IconData copy = LucideIcons.copy;
  static const IconData paste = LucideIcons.clipboard;
  static const IconData cut = LucideIcons.scissors;
  static const IconData selectAll = LucideIcons.checkSquare;
  static const IconData undo = LucideIcons.undo;
  static const IconData redo = LucideIcons.redo;
  static const IconData check = LucideIcons.check;
  static const IconData checkCircle = LucideIcons.checkCircle;

  // ============ 文件与文档 ============

  static const IconData file = LucideIcons.file;
  static const IconData fileText = LucideIcons.fileText;
  static const IconData fileAudio = LucideIcons.fileAudio;
  static const IconData fileVideo = LucideIcons.fileVideo;
  static const IconData fileImage = LucideIcons.fileImage;
  static const IconData folder = LucideIcons.folder;
  static const IconData folderOpen = LucideIcons.folderOpen;
  static const IconData upload = LucideIcons.upload;
  static const IconData download = LucideIcons.download;
  static const IconData save = LucideIcons.save;
  static const IconData share = LucideIcons.share2;
  static const IconData exportIcon = LucideIcons.externalLink;
  static const IconData attachment = LucideIcons.paperclip;
  static const IconData document = LucideIcons.fileText;
  static const IconData externalLink = LucideIcons.externalLink;
  static const IconData openInNew = LucideIcons.externalLink;

  // ============ 通信与消息 ============

  static const IconData send = LucideIcons.send;
  static const IconData message = LucideIcons.messageSquare;
  static const IconData messageBubbleOutline = LucideIcons.messageCircle;
  static const IconData chatBubble = LucideIcons.messageCircle;
  static const IconData conversation = LucideIcons.messagesSquare;
  static const IconData forum = LucideIcons.messagesSquare;
  static const IconData notification = LucideIcons.bell;
  static const IconData email = LucideIcons.mail;
  static const IconData phone = LucideIcons.phone;

  // ============ 媒体与内容 ============

  static const IconData image = LucideIcons.image;
  static const IconData imageOff = LucideIcons.imageOff;
  static const IconData brokenImage = LucideIcons.imageOff;
  static const IconData camera = LucideIcons.camera;
  static const IconData video = LucideIcons.video;
  static const IconData audio = LucideIcons.fileAudio;
  static const IconData mic = LucideIcons.mic;
  static const IconData play = LucideIcons.play;
  static const IconData pause = LucideIcons.pause;
  static const IconData stop = LucideIcons.square;
  static const IconData music = LucideIcons.music;

  // ============ 用户与账户 ============

  static const IconData user = LucideIcons.user;
  static const IconData userPlus = LucideIcons.userPlus;
  static const IconData person = LucideIcons.user;
  static const IconData personAdd = LucideIcons.userPlus;
  static const IconData group = LucideIcons.users;
  static const IconData account = LucideIcons.userCircle;
  static const IconData login = LucideIcons.logIn;
  static const IconData logout = LucideIcons.logOut;

  // ============ 状态与指示 ============

  static const IconData error = LucideIcons.xCircle;
  static const IconData warning = LucideIcons.alertTriangle;
  static const IconData info = LucideIcons.info;
  static const IconData help = LucideIcons.helpCircle;
  static const IconData favorite = LucideIcons.heart;
  static const IconData favoriteFilled = LucideIcons.heart;
  static const IconData star = LucideIcons.star;
  static const IconData starFilled = LucideIcons.star;

  // ============ 导航箭头 ============

  static const IconData arrowUp = LucideIcons.arrowUp;
  static const IconData arrowDown = LucideIcons.arrowDown;
  static const IconData arrowLeft = LucideIcons.arrowLeft;
  static const IconData arrowRight = LucideIcons.arrowRight;
  static const IconData chevronUp = LucideIcons.chevronUp;
  static const IconData chevronDown = LucideIcons.chevronDown;
  static const IconData chevronLeft = LucideIcons.chevronLeft;
  static const IconData chevronRight = LucideIcons.chevronRight;
  static const IconData expandMore = LucideIcons.chevronDown;
  static const IconData expandLess = LucideIcons.chevronUp;
  static const IconData unfoldMore = LucideIcons.chevronsUpDown;
  static const IconData unfoldLess = LucideIcons.chevronsDownUp;

  // ============ AI与智能 ============

  static const IconData bot = LucideIcons.bot;
  static const IconData chatbot = LucideIcons.bot;
  static const IconData ai = LucideIcons.brain;
  static const IconData psychology = LucideIcons.brain;
  static const IconData auto = LucideIcons.sparkles;
  static const IconData autoAwesome = LucideIcons.sparkles;
  static const IconData magic = LucideIcons.wand2;
  static const IconData thinking = LucideIcons.lightbulb;
  static const IconData lightbulb = LucideIcons.lightbulb;
  static const IconData code = LucideIcons.code;
  static const IconData terminal = LucideIcons.terminal;
  static const IconData workflow = LucideIcons.gitBranch;
  static const IconData accountTree = LucideIcons.gitBranch;

  // ============ 视图与显示 ============

  static const IconData eye = LucideIcons.eye;
  static const IconData eyeOff = LucideIcons.eyeOff;
  static const IconData visibility = LucideIcons.eye;
  static const IconData visibilityOff = LucideIcons.eyeOff;
  static const IconData fullscreen = LucideIcons.maximize;
  static const IconData fullscreenExit = LucideIcons.minimize;
  static const IconData zoomIn = LucideIcons.zoomIn;
  static const IconData zoomOut = LucideIcons.zoomOut;
  static const IconData refresh = LucideIcons.refreshCw;
  static const IconData sync = LucideIcons.refreshCw;
  static const IconData display = LucideIcons.monitor;

  // ============ 时间与日期 ============

  static const IconData time = LucideIcons.clock;
  static const IconData calendar = LucideIcons.calendar;
  static const IconData history = LucideIcons.history;
  static const IconData timer = LucideIcons.timer;
  static const IconData alarm = LucideIcons.alarmClock;

  // ============ 位置与地图 ============

  static const IconData location = LucideIcons.mapPin;
  static const IconData locationPin = LucideIcons.mapPin;
  static const IconData map = LucideIcons.map;
  static const IconData navigation = LucideIcons.navigation;
  static const IconData explore = LucideIcons.compass;

  // ============ 工具与系统 ============

  static const IconData tools = LucideIcons.wrench;
  static const IconData tool = LucideIcons.wrench;
  static const IconData wrench = LucideIcons.wrench;
  static const IconData palette = LucideIcons.palette;
  static const IconData theme = LucideIcons.paintbrush;
  static const IconData brightness = LucideIcons.sun;
  static const IconData darkMode = LucideIcons.moon;
  static const IconData lightMode = LucideIcons.sun;
  static const IconData battery = LucideIcons.battery;
  static const IconData wifi = LucideIcons.wifi;
  static const IconData bluetooth = LucideIcons.bluetooth;
  static const IconData sliders = LucideIcons.slidersHorizontal;
  static const IconData tune = LucideIcons.slidersHorizontal;
  static const IconData cleaning = LucideIcons.sparkles;

  // ============ 电商与支付 ============

  static const IconData cart = LucideIcons.shoppingCart;
  static const IconData bag = LucideIcons.shoppingBag;
  static const IconData payment = LucideIcons.creditCard;
  static const IconData card = LucideIcons.creditCard;
  static const IconData wallet = LucideIcons.wallet;

  // ============ 安全与隐私 ============

  static const IconData lock = LucideIcons.lock;
  static const IconData unlock = LucideIcons.unlock;
  static const IconData security = LucideIcons.shield;
  static const IconData shield = LucideIcons.shield;
  static const IconData key = LucideIcons.key;
  static const IconData fingerprint = LucideIcons.fingerprint;

  // ============ 网络与连接 ============

  static const IconData link = LucideIcons.link;
  static const IconData linkOff = LucideIcons.unlink;
  static const IconData cloud = LucideIcons.cloud;
  static const IconData cloudOff = LucideIcons.cloudOff;
  static const IconData cloudUpload = LucideIcons.uploadCloud;
  static const IconData cloudDownload = LucideIcons.downloadCloud;
  static const IconData signal = LucideIcons.signal;
  static const IconData globe = LucideIcons.globe;
  static const IconData language = LucideIcons.globe;
  static const IconData publicIcon = LucideIcons.globe;

  // ============ 数据与统计 ============

  static const IconData chart = LucideIcons.barChart;
  static const IconData analytics = LucideIcons.barChart2;
  static const IconData pieChart = LucideIcons.pieChart;
  static const IconData trendingUp = LucideIcons.trendingUp;
  static const IconData trendingDown = LucideIcons.trendingDown;
  static const IconData data = LucideIcons.database;
  static const IconData database = LucideIcons.database;
  static const IconData dashboard = LucideIcons.layoutDashboard;

  // ============ 特殊功能 ============

  static const IconData tag = LucideIcons.tag;
  static const IconData bookmark = LucideIcons.bookmark;
  static const IconData bookmarkFilled = LucideIcons.bookmark;
  static const IconData flag = LucideIcons.flag;
  static const IconData pin = LucideIcons.pin;
  static const IconData drag = LucideIcons.gripVertical;
  static const IconData hamburger = LucideIcons.menu;
  static const IconData gridView = LucideIcons.layoutGrid;
  static const IconData listView = LucideIcons.list;
  static const IconData cardView = LucideIcons.layoutGrid;
  static const IconData type = LucideIcons.type;
  static const IconData text = LucideIcons.type;
}
