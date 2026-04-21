import 'package:flutter/foundation.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../models/role_preset.dart';
import '../models/custom_role.dart';
import '../models/chat_settings.dart';
import '../services/hive_conversation_service.dart';
import '../services/storage_service.dart';
import '../services/custom_role_service.dart';
import '../services/backend_conversation_service.dart';
import '../services/backend_custom_role_service.dart';
import '../services/backend_conversation_source_service.dart';
import '../utils/token_counter.dart';
import '../adapters/ai_provider.dart';

class ChatSessionProvider extends ChangeNotifier {
  final HiveConversationService _conversationService;
  final StorageService _storageService = StorageService();
  final CustomRoleService _customRoleService = CustomRoleService();
  final BackendConversationService _backendConversationService =
      BackendConversationService();
  final BackendCustomRoleService _backendCustomRoleService =
      BackendCustomRoleService();
  final BackendConversationSourceService _backendConversationSourceService =
      BackendConversationSourceService();

  // State
  List<Conversation> _conversations = [];
  Conversation? _currentConversation;
  bool _isLoading = true;
  ChatSettings _settings = ChatSettings();
  TokenUsage _tokenUsage = TokenUsage();
  List<CustomRole> _customRoles = [];

  // Getters
  List<Conversation> get conversations => _conversations;
  Conversation? get currentConversation => _currentConversation;
  bool get isLoading => _isLoading;
  ChatSettings get settings => _settings;
  TokenUsage get tokenUsage => _tokenUsage;
  List<CustomRole> get customRoles => _customRoles;

  /// 通过 ID 获取单条消息（用于加载非活动分支消息）
  Message? getMessageById(String id) {
    if (ProviderFactory.pythonBackendEnabled) {
      return null;
    }
    return _conversationService.getMessageById(id);
  }

  ChatSessionProvider(this._conversationService) {
    _init();
  }

  Future<void> _init() async {
    _isLoading = true;
    notifyListeners();

    try {
      await _conversationService.initialize();

      final loadConversationsFuture = ProviderFactory.pythonBackendEnabled
          ? _loadBackendConversations()
          : _conversationService.loadConversations();

      final results = await Future.wait([
        loadConversationsFuture,
        _storageService.loadSettings(),
        _storageService.loadTokenUsage(),
        _loadCustomRoles(),
        _conversationService.loadCurrentConversationId(),
      ]);

      _conversations = results[0] as List<Conversation>;
      _settings = results[1] as ChatSettings;
      _tokenUsage = results[2] as TokenUsage;
      _customRoles = results[3] as List<CustomRole>;
      final currentId = results[4] as String?;

      if (_conversations.isNotEmpty) {
        if (currentId != null) {
          final index = _conversations.indexWhere((c) => c.id == currentId);
          if (index >= 0) {
            await _selectConversation(_conversations[index]);
          } else {
            await _selectConversation(_conversations.first);
          }
        } else {
          await _selectConversation(_conversations.first);
        }
      } else {
        await createNewConversation();
      }
    } catch (e) {
      debugPrint('ChatSessionProvider init failed: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _selectConversation(Conversation conversation) async {
    // If we are already on this conversation, do nothing
    if (_currentConversation?.id == conversation.id) {
      return;
    }

    _currentConversation = conversation;
    await _conversationService.saveCurrentConversationId(conversation.id);
    notifyListeners();
  }

  Future<List<Conversation>> _loadBackendConversations() async {
    final conversations = await _backendConversationService.listConversations();
    return conversations.map((item) => item.toConversation()).toList();
  }

  Future<List<CustomRole>> _loadCustomRoles() async {
    if (!ProviderFactory.pythonBackendEnabled) {
      return _customRoleService.loadCustomRoles();
    }

    final localRoles = await _customRoleService.loadCustomRoles();
    await _backendCustomRoleService.importMissingLocalRoles(localRoles);
    final backendRoles = await _backendCustomRoleService.listRoles();
    await _customRoleService.saveCustomRoles(backendRoles);
    return backendRoles;
  }

  Future<void> switchConversation(String id) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index >= 0) {
      await _selectConversation(_conversations[index]);
    }
  }

  Future<void> createNewConversation({
    RolePreset? rolePreset,
    CustomRole? customRole,
  }) async {
    String? title;
    String? systemPrompt;
    String? roleId;
    String? roleType;

    if (rolePreset != null) {
      title = rolePreset.name;
      systemPrompt = rolePreset.systemPrompt;
      roleId = rolePreset.id;
      roleType = 'preset';
    } else if (customRole != null) {
      title = customRole.name;
      systemPrompt = customRole.systemPrompt;
      roleId = customRole.id;
      roleType = 'custom';
    }

    final newConv = ProviderFactory.pythonBackendEnabled
        ? (await _backendConversationService.createConversation(
            title: title,
            systemPrompt: systemPrompt,
            roleId: roleId,
            roleType: roleType,
          )).toConversation()
        : _conversationService.createConversation(
            title: title,
            systemPrompt: systemPrompt,
            roleId: roleId,
            roleType: roleType,
          );

    _conversations.add(newConv);
    if (!ProviderFactory.pythonBackendEnabled) {
      await _conversationService.saveConversations(_conversations);
    }
    await _selectConversation(newConv);
  }

  Future<void> deleteConversation(String id) async {
    if (_conversations.length <= 1) return; // Prevent deleting last one

    final index = _conversations.indexWhere((c) => c.id == id);
    if (index < 0) return;

    final wasCurrent = _currentConversation?.id == id;

    _conversations.removeAt(index);
    if (ProviderFactory.pythonBackendEnabled) {
      await _backendConversationService.deleteConversation(id);
    } else {
      await _conversationService.saveConversations(_conversations);
    }

    if (wasCurrent) {
      final nextIndex = index >= _conversations.length
          ? _conversations.length - 1
          : index;
      await _selectConversation(_conversations[nextIndex]);
    } else {
      notifyListeners();
    }
  }

  Future<void> renameConversation(String id, String newTitle) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index >= 0) {
      if (ProviderFactory.pythonBackendEnabled) {
        final existing = _conversations[index];
        final updated = await _backendConversationService.updateConversation(
          conversationId: id,
          title: newTitle,
        );
        _conversations[index] = updated.toConversation()
          ..messages.addAll(existing.messages);
      } else {
        _conversations[index].title = newTitle;
        await _conversationService.saveConversations(_conversations);
      }
      notifyListeners();
    }
  }

  Future<void> clearCurrentMessages() async {
    if (_currentConversation == null) return;

    if (ProviderFactory.pythonBackendEnabled) {
      await _backendConversationSourceService.clearSource(
        _currentConversation!.id,
      );
      await _backendConversationService.clearCompactSummary(
        _currentConversation!.id,
      );
      _currentConversation!.clearMessages();
    } else {
      _currentConversation!.clearMessages();
      await _conversationService.saveConversations(_conversations);
    }
    notifyListeners();
  }

  // Token Usage
  Future<void> updateTokenUsage(int input, int output) async {
    final cost =
        TokenCounter.estimateCost(input, _settings.model, isOutput: false) +
        TokenCounter.estimateCost(output, _settings.model, isOutput: true);

    _tokenUsage.addUsage(input, output, cost);
    await _storageService.saveTokenUsage(_tokenUsage);
    notifyListeners();
  }

  Future<void> resetTokenStats() async {
    _tokenUsage.reset();
    await _storageService.saveTokenUsage(_tokenUsage);
    notifyListeners();
  }

  // Settings
  Future<void> updateSettings(ChatSettings newSettings) async {
    _settings = newSettings;
    await _storageService.saveSettings(newSettings);
    notifyListeners();
  }

  // Custom Roles
  Future<void> reloadCustomRoles() async {
    _customRoles = await _loadCustomRoles();
    notifyListeners();
  }

  /// Trigger a save of the current state
  Future<void> saveCurrentConversation() async {
    if (ProviderFactory.pythonBackendEnabled) {
      final current = _currentConversation;
      if (current == null) return;
      await _backendConversationService.updateConversation(
        conversationId: current.id,
        title: current.title,
        systemPrompt: current.systemPrompt,
        roleId: current.roleId,
        roleType: current.roleType,
      );
      if ((current.summary ?? '').trim().isEmpty &&
          current.summaryRangeStartId == null &&
          current.summaryRangeEndId == null) {
        await _backendConversationService.clearCompactSummary(current.id);
      } else {
        await _backendConversationService.updateCompactSummary(
          conversationId: current.id,
          summary: current.summary,
          rangeStartMessageId: current.summaryRangeStartId,
          rangeEndMessageId: current.summaryRangeEndId,
        );
      }
      return;
    }
    await _conversationService.saveConversations(_conversations);
  }
}
