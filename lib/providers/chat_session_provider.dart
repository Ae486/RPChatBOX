import 'package:flutter/foundation.dart';
import '../models/conversation.dart';
import '../models/role_preset.dart';
import '../models/custom_role.dart';
import '../models/chat_settings.dart';
import '../services/hive_conversation_service.dart';
import '../services/storage_service.dart';
import '../services/custom_role_service.dart';
import '../utils/token_counter.dart';

class ChatSessionProvider extends ChangeNotifier {
  final HiveConversationService _conversationService;
  final StorageService _storageService = StorageService();
  final CustomRoleService _customRoleService = CustomRoleService();

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

  ChatSessionProvider(this._conversationService) {
    _init();
  }

  Future<void> _init() async {
    _isLoading = true;
    notifyListeners();

    await _conversationService.initialize();
    
    // Load settings & other data parallel
    final results = await Future.wait([
      _conversationService.loadConversations(), // Currently loads all messages (safe for search)
      _storageService.loadSettings(),
      _storageService.loadTokenUsage(),
      _customRoleService.loadCustomRoles(),
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
      // Create default if none
      await createNewConversation();
    }

    _isLoading = false;
    notifyListeners();
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

  Future<void> switchConversation(String id) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index >= 0) {
      await _selectConversation(_conversations[index]);
    }
  }

  Future<void> createNewConversation({RolePreset? rolePreset, CustomRole? customRole}) async {
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

    final newConv = _conversationService.createConversation(
      title: title,
      systemPrompt: systemPrompt,
      roleId: roleId,
      roleType: roleType,
    );

    _conversations.add(newConv);
    await _conversationService.saveConversations(_conversations); 
    await _selectConversation(newConv);
  }

  Future<void> deleteConversation(String id) async {
    if (_conversations.length <= 1) return; // Prevent deleting last one

    final index = _conversations.indexWhere((c) => c.id == id);
    if (index < 0) return;

    final wasCurrent = _currentConversation?.id == id;
    
    _conversations.removeAt(index);
    await _conversationService.saveConversations(_conversations); 
    
    if (wasCurrent) {
      final nextIndex = index >= _conversations.length ? _conversations.length - 1 : index;
      await _selectConversation(_conversations[nextIndex]);
    } else {
      notifyListeners();
    }
  }

  Future<void> renameConversation(String id, String newTitle) async {
    final index = _conversations.indexWhere((c) => c.id == id);
    if (index >= 0) {
      _conversations[index].title = newTitle;
      await _conversationService.saveConversations(_conversations);
      notifyListeners();
    }
  }

  Future<void> clearCurrentMessages() async {
    if (_currentConversation == null) return;
    
    _currentConversation!.clearMessages();
    await _conversationService.saveConversations(_conversations);
    notifyListeners();
  }

  // Token Usage
  Future<void> updateTokenUsage(int input, int output) async {
    final cost = TokenCounter.estimateCost(input, _settings.model, isOutput: false) +
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
    _customRoles = await _customRoleService.loadCustomRoles();
    notifyListeners();
  }

  /// Trigger a save of the current state
  Future<void> saveCurrentConversation() async {
    await _conversationService.saveConversations(_conversations);
    notifyListeners();
  }
}