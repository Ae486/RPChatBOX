import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:chatboxapp/models/conversation.dart';
import 'package:chatboxapp/models/message.dart';
import 'package:chatboxapp/models/attached_file.dart';
import 'package:chatboxapp/services/hive_conversation_service.dart';
import 'dart:io';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import '../../helpers/test_data.dart';

/// HiveConversationService 单元测试
/// 
/// 测试核心数据持久化功能，确保会话和消息的保存、加载、删除等操作正确无误。
/// 这是方案B（最小保护网）的关键测试之一，保护数据安全。
class FakePathProvider extends PathProviderPlatform {
  @override
  Future<String?> getApplicationDocumentsPath() async {
    final directory = await Directory.systemTemp.createTemp('chatbox_hive_test_');
    return directory.path;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  PathProviderPlatform.instance = FakePathProvider();

  // 测试组：HiveConversationService
  group('HiveConversationService', () {
    late HiveConversationService service;
    late Directory tempDirectory;

    // 在每个测试前初始化
    setUp(() async {
      // 使用临时测试目录
      tempDirectory = await Directory.systemTemp.createTemp('chatbox_hive_test_');
      
      // 初始化 Hive 测试环境
      Hive.init(tempDirectory.path);
      
      // 注册适配器（如果未注册）
      if (!Hive.isAdapterRegistered(0)) {
        Hive.registerAdapter(ConversationAdapter());
      }
      if (!Hive.isAdapterRegistered(1)) {
        Hive.registerAdapter(MessageAdapter());
      }
      if (!Hive.isAdapterRegistered(2)) {
        Hive.registerAdapter(FileTypeAdapter());
      }
      if (!Hive.isAdapterRegistered(3)) {
        Hive.registerAdapter(AttachedFileSnapshotAdapter());
      }
      
      // 创建服务实例
      service = HiveConversationService();
    });

    // 在每个测试后清理
    tearDown(() async {
      // 关闭所有打开的box
      await service.close();
      await Hive.close();
      
      // 删除测试数据
      await tempDirectory.delete(recursive: true);
    });

    // 测试组：initialize
    group('initialize', () {
      test('should initialize Hive and open boxes', () async {
        // Act
        await service.initialize();

        // Assert
        expect(Hive.isBoxOpen('conversations'), isTrue);
        expect(Hive.isBoxOpen('settings'), isTrue);
      });

      test('should not throw when called multiple times', () async {
        // Act & Assert
        await service.initialize();
        await expectLater(
          service.initialize(),
          completes,
        );
      });
    });

    // 测试组：saveConversations
    group('saveConversations', () {
      test('should save conversations to Hive', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1', title: 'Conv 1'),
          TestData.createTestConversation(id: 'conv-2', title: 'Conv 2'),
        ];

        // Act
        await service.saveConversations(conversations);

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.length, equals(2));
        expect(loaded.any((c) => c.id == 'conv-1'), isTrue);
        expect(loaded.any((c) => c.id == 'conv-2'), isTrue);
      });

      test('should clear existing conversations before saving', () async {
        // Arrange
        await service.initialize();
        final oldConversations = [
          TestData.createTestConversation(id: 'old-1'),
        ];
        await service.saveConversations(oldConversations);

        final newConversations = [
          TestData.createTestConversation(id: 'new-1'),
          TestData.createTestConversation(id: 'new-2'),
        ];

        // Act
        await service.saveConversations(newConversations);

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.length, equals(2));
        expect(loaded.any((c) => c.id == 'old-1'), isFalse);
        expect(loaded.any((c) => c.id == 'new-1'), isTrue);
      });

      test('should throw exception when Hive not initialized', () async {
        // Arrange
        final conversations = [TestData.createTestConversation()];

        // Act & Assert
        expect(
          () => service.saveConversations(conversations),
          throwsA(isA<Exception>()),
        );
      });

      test('should save empty list', () async {
        // Arrange
        await service.initialize();
        final conversations = <Conversation>[];

        // Act
        await service.saveConversations(conversations);

        // Assert - 应该返回默认会话
        final loaded = await service.loadConversations();
        expect(loaded.length, equals(1));
        expect(loaded.first.title, equals('新对话'));
      });

      test('should preserve messages in conversations', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createConversationWithMessages(
            id: 'conv-with-msgs',
            messageCount: 5,
          ),
        ];

        // Act
        await service.saveConversations(conversations);

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.first.messages.length, equals(5));
      });
    });

    // 测试组：loadConversations
    group('loadConversations', () {
      test('should load all conversations', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1'),
          TestData.createTestConversation(id: 'conv-2'),
          TestData.createTestConversation(id: 'conv-3'),
        ];
        await service.saveConversations(conversations);

        // Act
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded.length, equals(3));
      });

      test('should return conversations sorted by updatedAt descending', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(
            id: 'conv-1',
            updatedAt: DateTime(2024, 1, 1),
          ),
          TestData.createTestConversation(
            id: 'conv-2',
            updatedAt: DateTime(2024, 1, 3),
          ),
          TestData.createTestConversation(
            id: 'conv-3',
            updatedAt: DateTime(2024, 1, 2),
          ),
        ];
        await service.saveConversations(conversations);

        // Act
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded[0].id, equals('conv-2')); // 最新的在前
        expect(loaded[1].id, equals('conv-3'));
        expect(loaded[2].id, equals('conv-1'));
      });

      test('should return default conversation when box is empty', () async {
        // Arrange
        await service.initialize();

        // Act
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded.length, equals(1));
        expect(loaded.first.title, equals('新对话'));
        expect(loaded.first.messages, isEmpty);
      });

      test('should throw exception when Hive not initialized', () async {
        // Act & Assert
        expect(
          () => service.loadConversations(),
          throwsA(isA<Exception>()),
        );
      });
    });

    // 测试组：saveCurrentConversationId & loadCurrentConversationId
    group('current conversation ID', () {
      test('should save and load current conversation ID', () async {
        // Arrange
        await service.initialize();
        const testId = 'test-conv-id';

        // Act
        await service.saveCurrentConversationId(testId);
        final loadedId = await service.loadCurrentConversationId();

        // Assert
        expect(loadedId, equals(testId));
      });

      test('should return null when no current conversation ID set', () async {
        // Arrange
        await service.initialize();

        // Act
        final loadedId = await service.loadCurrentConversationId();

        // Assert
        expect(loadedId, isNull);
      });

      test('should update current conversation ID', () async {
        // Arrange
        await service.initialize();
        await service.saveCurrentConversationId('old-id');

        // Act
        await service.saveCurrentConversationId('new-id');
        final loadedId = await service.loadCurrentConversationId();

        // Assert
        expect(loadedId, equals('new-id'));
      });
    });

    // 测试组：createConversation
    group('createConversation', () {
      test('should create conversation with default title', () {
        // Act
        final conversation = service.createConversation();

        // Assert
        expect(conversation.id, isNotEmpty);
        expect(conversation.title, contains('新对话'));
        expect(conversation.messages, isEmpty);
      });

      test('should create conversation with custom title', () {
        // Act
        final conversation = service.createConversation(
          title: 'Custom Title',
        );

        // Assert
        expect(conversation.title, equals('Custom Title'));
      });

      test('should create conversation with system prompt', () {
        // Act
        final conversation = service.createConversation(
          systemPrompt: 'You are a helpful assistant',
        );

        // Assert
        expect(conversation.systemPrompt, equals('You are a helpful assistant'));
      });

      test('should create conversation with role', () {
        // Act
        final conversation = service.createConversation(
          roleId: 'role-123',
          roleType: 'custom',
        );

        // Assert
        expect(conversation.roleId, equals('role-123'));
        expect(conversation.roleType, equals('custom'));
      });

      test('should create unique IDs for each conversation', () async {
        // Act
        final conv1 = service.createConversation();
        // 模拟时间流逝，确保 ID 不重复
        await Future.delayed(const Duration(milliseconds: 1));
        final conv2 = service.createConversation();

        // Assert
        expect(conv1.id, isNot(equals(conv2.id)));
      });
    });

    // 测试组：deleteConversation
    group('deleteConversation', () {
      test('should delete conversation by ID', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1'),
          TestData.createTestConversation(id: 'conv-2'),
          TestData.createTestConversation(id: 'conv-3'),
        ];
        await service.saveConversations(conversations);

        // Act
        await service.deleteConversation(conversations, 'conv-2');

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.length, equals(2));
        expect(loaded.any((c) => c.id == 'conv-2'), isFalse);
        expect(loaded.any((c) => c.id == 'conv-1'), isTrue);
        expect(loaded.any((c) => c.id == 'conv-3'), isTrue);
      });

      test('should do nothing when conversation ID not found', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1'),
        ];
        await service.saveConversations(conversations);

        // Act
        await service.deleteConversation(conversations, 'non-existent');

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.length, equals(1));
      });
    });

    // 测试组：updateConversationTitle
    group('updateConversationTitle', () {
      test('should update conversation title', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1', title: 'Old Title'),
        ];
        await service.saveConversations(conversations);

        // Act
        await service.updateConversationTitle(conversations, 'conv-1', 'New Title');

        // Assert
        final loaded = await service.loadConversations();
        expect(loaded.first.title, equals('New Title'));
      });
    });

    // 测试组：clearAllConversations
    group('clearAllConversations', () {
      test('should clear all conversations and current ID', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createTestConversation(id: 'conv-1'),
          TestData.createTestConversation(id: 'conv-2'),
        ];
        await service.saveConversations(conversations);
        await service.saveCurrentConversationId('conv-1');

        // Act
        await service.clearAllConversations();

        // Assert
        final loadedConversations = await service.loadConversations();
        final loadedId = await service.loadCurrentConversationId();
        
        // 应该返回默认会话（因为box为空）
        expect(loadedConversations.length, equals(1));
        expect(loadedConversations.first.title, equals('新对话'));
        expect(loadedId, isNull);
      });
    });

    // 测试组：edge cases (边界条件)
    group('edge cases', () {
      test('should handle conversation with many messages', () async {
        // Arrange
        await service.initialize();
        final conversations = [
          TestData.createConversationWithMessages(
            id: 'large-conv',
            messageCount: 100,
          ),
        ];

        // Act
        await service.saveConversations(conversations);
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded.first.messages.length, equals(100));
      });

      test('should handle conversation with long message content', () async {
        // Arrange
        await service.initialize();
        final longContent = 'A' * 10000; // 10000 个字符
        final conversation = TestData.createTestConversation(
          id: 'long-msg-conv',
          messages: [
            TestData.createTestMessage(content: longContent),
          ],
        );

        // Act
        await service.saveConversations([conversation]);
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded.first.messages.first.content, equals(longContent));
        expect(loaded.first.messages.first.content.length, equals(10000));
      });

      test('should handle special characters in title', () async {
        // Arrange
        await service.initialize();
        const specialTitle = '测试 😀 #@!%^&*()_+-=[]{}|;:\'",.<>?/\\';
        final conversation = TestData.createTestConversation(
          id: 'special-conv',
          title: specialTitle,
        );

        // Act
        await service.saveConversations([conversation]);
        final loaded = await service.loadConversations();

        // Assert
        expect(loaded.first.title, equals(specialTitle));
      });
    });
  });
}
